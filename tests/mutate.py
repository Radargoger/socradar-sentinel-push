#!/usr/bin/env python3
"""Break the template on purpose and prove the test notices.

Each entry breaks one invariant, runs the test that should catch it, and restores the file.
A mutation that survives is BLIND and the run exits non-zero.

    python3 tests/mutate.py
"""

import json
import os
import subprocess
import sys
from assertion_result import caught
from mutation_isolation import disposable_repo, write_mutant

SOURCE_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = "azuredeploy.json"
P = "tests/test_workspace_precheck.py"
MUTATIONS = [
    ("push table isolation is removed", T,
     '''"tableName": "SOCRadar_Push_Alarms_CL"''',
     '''"tableName": "SOCRadar_Alarms_CL"''', "tests/test_table_isolation.py"),
    ("deploy harness reads the shared table", "scripts/test_deploy_paths.sh",
     '''-n SOCRadar_Push_Alarms_CL''',
     '''-n SOCRadar_Alarms_CL''', "tests/test_table_isolation.py"),
    ("workspace toggle defaults to true again", T,
     '''"DeployNewWorkspace": {
      "type": "bool",
      "defaultValue": false,''',
     '''"DeployNewWorkspace": {
      "type": "bool",
      "defaultValue": true,''', P),
    ("precheck evaluates in the parent scope", T,
     '''"expressionEvaluationOptions": {
          "scope": "inner"''',
     '''"expressionEvaluationOptions": {
          "scope": "outer"''', P),
    ("precheck no longer looks at the workspace", T,
     '''"value": "[reference(parameters('WorkspaceResourceId'), '2025-07-01', 'Full').properties.customerId]"''',
     '''"value": "none"''', P),
    ("precheck runs when the workspace is being created", T,
     '''"condition": "[not(parameters('DeployNewWorkspace'))]",
      "type": "Microsoft.Resources/deployments"''',
     '''"condition": "[true()]",
      "type": "Microsoft.Resources/deployments"''', P),
    ("the endpoint does not wait for the precheck", T,
     '''"networkAcls": {
          "publicNetworkAccess": "Enabled"
        }
      },
      "dependsOn": [
        "[resourceId('Microsoft.Resources/deployments', 'precheck-workspace-exists')]"
      ]''',
     '''"networkAcls": {
          "publicNetworkAccess": "Enabled"
        }
      },
      "dependsOn": []''', P),
    ("precheck stops asserting Microsoft Sentinel", T,
     '''"value": "[reference(extensionResourceId(parameters('WorkspaceResourceId'), 'Microsoft.SecurityInsights/onboardingStates', 'default'), '2025-09-01', 'Full').id]"''',
     '''"value": "none"''', P),
    ("precheck runs only when the workspace is being created", T,
     '''"condition": "[not(parameters('DeployNewWorkspace'))]",
      "type": "Microsoft.Resources/deployments"''',
     '''"condition": "[parameters('DeployNewWorkspace')]",
      "type": "Microsoft.Resources/deployments"''', P),
    ("precheck reference drops its api-version and Full", T,
     ''''2025-09-01', 'Full').id]"''',
     ''''1999-01-01').id]"''', P),
]
EXPECTED = [
    "TABLE: table-name", "TABLE: harness-table", "PRECHECK:workspace-default",
    "PRECHECK:inner-scope", "PRECHECK:workspace-reference",
    "PRECHECK:condition", "PRECHECK:dependencies",
    "PRECHECK:sentinel-reference", "PRECHECK:condition", "PRECHECK:reference-api",
]
if len(EXPECTED) != len(MUTATIONS):
    raise RuntimeError("Missing expected mutation assertion")


def syntax_error(path, text):
    if path.endswith(".json"):
        try:
            json.loads(text)
        except ValueError as e:
            return str(e)
    return None


with disposable_repo(SOURCE_REPO) as REPO:
    blind = []
    for test in sorted({mutation[4] for mutation in MUTATIONS}):
        baseline = subprocess.run([sys.executable, test], cwd=REPO, capture_output=True, text=True,
                                  timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if baseline.returncode:
            raise SystemExit("BASELINE_FAILED: " + test)
    for (name, path, old, new, test), expected in zip(MUTATIONS, EXPECTED):
        full = os.path.join(REPO, path)
        orig = open(full, encoding="utf-8").read()
        if orig.count(old) != 1:
            print("SKIP  %-48s anchor found %d time(s) in %s" % (name, orig.count(old), path)); blind.append(name); continue
        mutant = orig.replace(old, new, 1)
        err = syntax_error(path, mutant)
        if err:
            print("FAKE  %-48s mutant does not parse: %s" % (name, err)); blind.append(name); continue
        try:
            write_mutant(full, mutant)
            r = subprocess.run([sys.executable, test], cwd=REPO, capture_output=True, text=True, timeout=120,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = None
        finally:
            open(full, "w", encoding="utf-8").write(orig)
        if rc is None:
            print("ERROR %-48s timed out, not a catch" % name); blind.append(name)
        elif rc == 0:
            print("BLIND %-48s still passed" % name); blind.append(name)
        elif caught(r, expected):
            print("caught %-47s" % name)
        else:
            print("ERROR %-48s failed without its expected assertion" % name); blind.append(name)
    print("\nblind:", len(blind), "of", len(MUTATIONS))
    sys.exit(1 if blind else 0)
