"""Offline safety checks for mutation scripts.  No Azure command is invoked."""

from hashlib import sha256
from pathlib import Path
import os
import select
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MUTATORS = ("mutate.py", "mutate_limits.py", "mutate_description.py")
MUTABLE_SOURCE = (ROOT / "azuredeploy.json", ROOT / "scripts" / "test_deploy_paths.sh")


def source_hashes():
    return {path: sha256(path.read_bytes()).hexdigest() for path in MUTABLE_SOURCE}


class MutatorIsolationTests(unittest.TestCase):
    def test_all_mutators_leave_source_unchanged(self):
        before = source_hashes()
        for name in MUTATORS:
            with self.subTest(mutator=name):
                result = subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=180,
                                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(source_hashes(), before, "ISOLATION:source-hash")

    def test_sigkill_after_copy_write_leaves_source_unchanged(self):
        before = source_hashes()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", MUTATOR_TEST_SIGSTOP_AFTER_WRITE="1")
        process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mutate_limits.py")], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        scratch = None
        try:
            ready, _, _ = select.select([process.stdout], [], [], 20)
            self.assertTrue(ready, "ISOLATION:mutant-write-not-reached")
            line = process.stdout.readline().strip()
            prefix = "MUTATOR_TEST: disposable-root="
            self.assertTrue(line.startswith(prefix), "ISOLATION:owned-scratch-not-reported")
            scratch = Path(line.removeprefix(prefix)).resolve()
            self.assertEqual(scratch.parent, Path(tempfile.gettempdir()).resolve(), "ISOLATION:scratch-parent")
            self.assertTrue(scratch.name.startswith("socradar-push-mutator-"), "ISOLATION:scratch-prefix")
            ready, _, _ = select.select([process.stdout], [], [], 20)
            self.assertTrue(ready, "ISOLATION:mutant-write-not-reached")
            self.assertEqual(process.stdout.readline().strip(), "MUTATOR_TEST: copy-write-complete")
            process.kill()
            process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0, "ISOLATION:sigkill-expected")
            self.assertEqual(source_hashes(), before, "ISOLATION:sigkill-source-hash")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
            if scratch is not None and scratch.is_dir():
                shutil.rmtree(scratch)
            if scratch is not None:
                self.assertFalse(scratch.exists(), "ISOLATION:owned-scratch-cleanup")


if __name__ == "__main__":
    unittest.main()
