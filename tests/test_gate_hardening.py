"""Exercise the real gates in disposable /tmp copies, including their failure paths."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from assertion_result import caught

ROOT = Path(__file__).resolve().parents[1]

class GateHardeningTests(unittest.TestCase):
    def run_empty_suite(self, content=None, adapter=False):
        with tempfile.TemporaryDirectory(prefix="gate-empty-", dir="/tmp") as directory:
            tests = Path(directory) / "tests"
            tests.mkdir()
            for name in ("run_all.py", "run_one.py"):
                shutil.copyfile(ROOT / "tests" / name, tests / name)
            if content is not None:
                (tests / "test_probe.py").write_text(content)
            command = [sys.executable, str(tests / "run_all.py")]
            if adapter:
                command = [sys.executable, str(tests / "run_one.py"), str(tests / "test_probe.py")]
            return subprocess.run(command,
                                  capture_output=True, text=True, timeout=20)

    def test_empty_discovery_is_failure(self):
        result = self.run_empty_suite()
        self.assertEqual(result.returncode, 1, "HARDEN:empty-suite")
        self.assertIn("NO_TESTS", result.stderr)

    def test_empty_test_and_empty_unittest_are_failures(self):
        for content in ("", "print('a successful process is not a check')\n",
                        "import unittest\nunittest.main()\n", "import os\nos._exit(0)\n"):
            with self.subTest(content_kind=len(content)):
                result = self.run_empty_suite(content)
                self.assertEqual(result.returncode, 1, "HARDEN:zero-checks")
                self.assertIn("NO_CHECKS", result.stdout + result.stderr)

    def test_real_assertion_passes(self):
        for content in ("assert 1 == 1\n", "import unittest\nclass T(unittest.TestCase):\n"
                        "    def test_ok(self): self.assertEqual(1, 1)\nunittest.main()\n"):
            with self.subTest(content_kind=len(content)):
                result = self.run_empty_suite(content)
                self.assertEqual(result.returncode, 0)
                self.assertIn("CHECKS_PASSED", result.stdout)

    def test_adapter_rejects_zero_checks(self):
        result = self.run_empty_suite("", adapter=True)
        self.assertEqual(result.returncode, 1, "HARDEN:zero-checks")
        self.assertIn("NO_CHECKS", result.stdout + result.stderr)

    def test_documented_trusted_test_code_limits(self):
        probes = {
            "forged receipt": "import os\nprint('CHECKS_PASSED 1', flush=True)\nos._exit(0)\n",
            "empty check helper": "def check(condition): pass\ncheck(False)\n",
        }
        for name, content in probes.items():
            with self.subTest(documented_limit=name):
                result = self.run_empty_suite(content)
                self.assertEqual(result.returncode, 0, "Documented trusted-code limit changed; review tests/README.md")
        notes = (ROOT / "tests/README.md").read_text()
        self.assertIn("forged receipt", notes)
        self.assertIn("empty check/require", notes)

    def test_only_expected_assertion_is_a_catch(self):
        cases = [
            ("raise AssertionError('TABLE: table-name')", "TABLE: table-name", True),
            ("raise AssertionError('unrelated assertion')", "TABLE: table-name", False),
            ("raise RuntimeError('TABLE: table-name')", "TABLE: table-name", False),
            ("raise KeyError('TABLE: table-name')", "TABLE: table-name", False),
            ("raise ValueError('TABLE: table-name')", "TABLE: table-name", False),
            ("assert ???", "TABLE: table-name", False),
            ("import sys;sys.exit(1)", "TABLE: table-name", False),
            ("import sys;print('AssertionError: TABLE: table-name', file=sys.stderr);sys.exit(1)", "TABLE: table-name", False),
            ("raise SystemExit(0)", "TABLE: table-name", False),
        ]
        unit = ("import unittest\nclass T(unittest.TestCase):\n"
                "    def test_bad(self): self.assertIn('expected', 'actual', 'DESCRIPTION:lexer')\n")
        cases.extend([
            (unit + "unittest.main()\n", "DESCRIPTION:lexer", True),
            (unit + "    def test_crash(self): raise KeyError('DESCRIPTION:lexer')\nunittest.main()\n", "DESCRIPTION:lexer", False),
            (unit + "    def test_other(self): self.fail('other')\nunittest.main()\n", "DESCRIPTION:lexer", False),
        ])
        for code, expected, accepted in cases:
            with self.subTest(expected=expected, accepted=accepted, code_kind=cases.index((code, expected, accepted))):
                result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(caught(result, expected), accepted, "HARDEN:assertion-cause")

    def run_secret_gate(self, with_probe=False, scanner_error=False):
        workflow = (ROOT / ".github/workflows/checks.yml").read_text()
        body = workflow.split("- name: No secrets in tracked files\n        run: |\n", 1)[1]
        lines = []
        for line in body.splitlines():
            if line.strip() and not line.startswith("          "):
                break
            lines.append(line)
        script = textwrap.dedent("\n".join(lines))
        with tempfile.TemporaryDirectory(prefix="gate-scan-", dir="/tmp") as directory:
            root = Path(directory)
            # Generated noncredential; never copied from a capture or real key.
            probe = "sk-" + "0" * 24
            (root / "input.txt").write_text(probe if with_probe else "public documentation")
            env = dict(os.environ)
            if scanner_error:
                tools = root / "bin"
                tools.mkdir()
                executable = tools / "grep"
                if scanner_error == "after-calibration":
                    executable.write_text("#!/bin/sh\nif [ -f .scan-ready ]; then exit 2; fi\n"
                                          ": > .scan-ready\nexec /usr/bin/grep \"$@\"\n")
                elif scanner_error == "blind-calibration":
                    executable.write_text("#!/bin/sh\nif [ ! -f .scan-ready ]; then\n"
                                          "  : > .scan-ready\n  exit 1\nfi\nexec /usr/bin/grep \"$@\"\n")
                else:
                    executable.write_text("#!/bin/sh\nexit 2\n")
                executable.chmod(0o755)
                env["PATH"] = str(tools) + os.pathsep + env["PATH"]
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=20)
            self.assertTrue(probe not in result.stdout + result.stderr, "HARDEN:no-secret-output")
            self.assertFalse((root / ".calibration-probe").exists())
            return result

    def test_secret_gate_is_quiet_and_fail_closed(self):
        self.assertEqual(self.run_secret_gate().returncode, 0, "HARDEN:scan-clean")
        result = self.run_secret_gate(with_probe=True)
        self.assertEqual(result.returncode, 1, "HARDEN:secret-block")
        self.assertIn("secret pattern found", result.stdout)
        self.assertEqual(self.run_secret_gate(scanner_error=True).returncode, 1, "HARDEN:scan-error")
        error = self.run_secret_gate(scanner_error="after-calibration")
        self.assertEqual(error.returncode, 1, "HARDEN:scan-error")
        self.assertIn("secret scan failed", error.stdout)

    def test_blind_calibration_is_failure(self):
        result = self.run_secret_gate(scanner_error="blind-calibration")
        self.assertEqual(result.returncode, 1, "HARDEN:calibration-blind")
        self.assertIn("scan is blind", result.stdout)

if __name__ == "__main__":
    unittest.main()
