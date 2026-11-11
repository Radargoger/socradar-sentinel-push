"""Run one script in a fresh process and reject zero executed checks."""
import ast
from pathlib import Path
import runpy
import sys
import unittest

path = Path(sys.argv[1]).resolve()
assert_lines = {node.lineno for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, ast.Assert)}
checks = 0

def trace(frame, event, arg):
    global checks
    own = frame.f_code.co_filename == str(path)
    if event == "line" and own and frame.f_lineno in assert_lines:
        checks += 1
    if event == "call":
        if own and frame.f_code.co_name in ("check", "require"):
            checks += 1
        elif (frame.f_code.co_name.startswith("assert")
              and isinstance(frame.f_locals.get("self"), unittest.TestCase)
              and frame.f_back is not None
              and frame.f_back.f_code.co_filename == str(path)):
            checks += 1
    return trace

sys.argv = [str(path)]
sys.settrace(trace)
try:
    runpy.run_path(str(path), run_name="__main__")
except SystemExit as error:
    if error.code not in (None, 0):
        if checks == 0:
            raise SystemExit("NO_CHECKS: %s executed no assertions or checks" % path.name)
        raise
finally:
    sys.settrace(None)
if checks == 0:
    raise SystemExit("NO_CHECKS: %s executed no assertions or checks" % path.name)
print("CHECKS_PASSED %d" % checks)
