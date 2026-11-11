#!/usr/bin/env python3
"""Push must not create or alter the AlertBacked alarm table."""
import json
from pathlib import Path

root = Path(__file__).parents[1]
template = json.loads((root / "azuredeploy.json").read_text(encoding="utf-8"))
table_name = "SOCRadar_Push_Alarms_CL"

assert template["variables"]["tableName"] == table_name, "TABLE: table-name"
table = next(r for r in template["resources"]
             if r["type"] == "Microsoft.OperationalInsights/workspaces/tables")
assert table["properties"]["schema"]["name"] == "[variables('tableName')]"
dcr = next(r for r in template["resources"]
           if r["type"] == "Microsoft.Insights/dataCollectionRules")
assert dcr["properties"]["dataFlows"][0]["outputStream"] == "Custom-" + table_name
serialized = json.dumps(template)
assert table_name in serialized
assert "SOCRadar_Alarms_CL" not in serialized
deploy_paths = (root / "scripts" / "test_deploy_paths.sh").read_text(encoding="utf-8")
assert table_name in deploy_paths, "TABLE: harness-table"
assert "SOCRadar_Alarms_CL" not in deploy_paths, "TABLE: harness-table"
print("push table isolation: pass")
