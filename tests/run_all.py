#!/usr/bin/env python3
"""Run every test in this directory and report a single verdict."""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = sorted(f for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
if not TESTS:
    raise SystemExit("NO_TESTS: no test files discovered")

# Never leave .pyc files behind. A cached module is keyed on the source's
# mtime in whole seconds and its size, so a mutation check that swaps a byte
# and restores it inside the same second leaves a stale cache that silently
# feeds the mutated code to every later run.
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

failed = []
for name in TESTS:
    result = subprocess.run([sys.executable, os.path.join(HERE, "run_one.py"), os.path.join(HERE, name)],
                            capture_output=True, text=True, env=env, timeout=120)
    sys.stdout.write(result.stdout)
    receipts = re.findall(r"^CHECKS_PASSED [1-9][0-9]*$", result.stdout, re.M)
    last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    receipt_ok = len(receipts) == 1 and last_line == receipts[0]
    if result.returncode or not receipt_ok:
        sys.stdout.write(result.stderr)
        if result.returncode == 0 and not receipt_ok:
            print("NO_CHECKS_RECEIPT: %s" % name)
        failed.append(name)

print()
if failed:
    print("FAILED: %s" % ", ".join(failed))
    sys.exit(1)
print("%d test file(s) passed" % len(TESTS))
