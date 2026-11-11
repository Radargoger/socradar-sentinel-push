"""Disposable worktree support for mutation scripts.

Mutation scripts must never write into the caller's checkout.  A forced process
termination can bypass ``finally``, so the mutable target is always a copied
repository under the system temporary directory.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import tempfile


def _ignore_copy(_, names):
    return {name for name in names if name == ".git" or name == "__pycache__" or name.endswith(".pyc")}


@contextmanager
def disposable_repo(source_root):
    """Yield an independent copy of ``source_root`` and remove it on normal exit."""
    source = Path(source_root).resolve()
    if not source.is_dir():
        raise RuntimeError("Mutation source root is not a directory: " + str(source))
    with tempfile.TemporaryDirectory(prefix="socradar-push-mutator-") as temporary:
        copy = Path(temporary) / source.name
        shutil.copytree(source, copy, ignore=_ignore_copy)
        if os.environ.get("MUTATOR_TEST_SIGSTOP_AFTER_WRITE") == "1":
            print("MUTATOR_TEST: disposable-root=" + temporary, flush=True)
        yield copy


def write_mutant(path, content):
    """Write only inside a disposable repo; test hook stops after the first write."""
    Path(path).write_text(content, encoding="utf-8")
    if os.environ.get("MUTATOR_TEST_SIGSTOP_AFTER_WRITE") == "1":
        print("MUTATOR_TEST: copy-write-complete", flush=True)
        os.kill(os.getpid(), signal.SIGSTOP)
