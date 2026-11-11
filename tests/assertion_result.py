"""A mutant is caught only by its intended assertion, never by a crash."""
import re

def caught(result, expected):
    if result.returncode != 1:
        return False
    if "Traceback (most recent call last):" not in result.stderr:
        return False
    lines = result.stderr.splitlines()
    exceptions = [line for line in lines
                  if re.match(r"^[A-Za-z_][\w.]*(?:Error|Exception)(?::|$)", line)]
    if len(exceptions) != 1 or not exceptions[0].startswith("AssertionError:"):
        return False
    if any(line.startswith("ERROR:") for line in lines):
        return False
    if expected.startswith("DESCRIPTION:"):
        return (exceptions[0].endswith(" : " + expected)
                and re.search(r"^FAILED \(failures=1\)$", result.stderr, re.M) is not None)
    return exceptions[0] == "AssertionError: " + expected
