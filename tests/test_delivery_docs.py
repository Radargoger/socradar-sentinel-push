#!/usr/bin/env python3
"""Check the delivery, rollback, and CI promises exposed to operators."""

from pathlib import Path
import json
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
SETUP = (ROOT / "docs/setup-guide.md").read_text(encoding="utf-8")
STABLE_SHA = "d887b39123f95171f54adb2b9965b69c6b4c9314"


def require(text, description):
    if text not in README:
        raise AssertionError("README missing: %s" % description)


require("`key: value`", "plain description format")
require("If your installation currently uses `SOCRadar_Alarms_CL`, use this migration path", "actionable migration path")
require("input stream and SOCRadar form fields are unchanged", "migration input compatibility")
require("new workbook starts empty", "migration workbook history limitation")
require("Update your own KQL queries to `SOCRadar_Push_Alarms_CL`", "migration query step")
require("When the first real alarm arrives, verify one row in the new table, one incident, and no duplicate incident", "migration verification step")
require("CCF pull in the same workspace", "CCF shared-workspace warning")
require("They share GUID seeds", "CCF GUID collision reason")
require("Do not combine these installations during an upgrade or rollback", "CCF migration safety boundary")
require(STABLE_SHA, "fixed rollback revision")
require("raw.githubusercontent.com%2Forcunsami%2FSOCRadar-Sentinel-Push", "fixed rollback deployment URL")
require("Do not delete `SOCRadar_Alarms_CL`", "shared legacy table preservation")
require("dedicated to this Push installation", "reused app-registration warning")
require("very long alarm URL is omitted with an explicit marker", "long-URL omission behavior")
require("mixed UTF-8 tail", "mixed-tail content limitation")
require("Check the description and source link in your incident", "customer visual-rendering and destination check")
limits = README.split("## Things to know\n", 1)[1].split("\n## ", 1)[0]
for phrase in ("A closed incident is not reopened; a new one opens.",
               "sees rows from 12 minutes to 1 day old", "does not get one later",
               "within 7 days", "every 10 minutes"):
    if phrase not in limits:
        raise AssertionError("LIMIT:documentation")

template = json.loads((ROOT / "azuredeploy.json").read_text())
upgrade = README.split("### Updating an existing Push installation\n", 1)[1].split("\n## ", 1)[0]
for phrase in ("two analytic rules can fail with `One of the tables does not exist`",
               "Only for that error, wait until `SOCRadar_Push_Alarms_CL | take 0` succeeds in Logs",
               "redeploy the same template once more with the same values",
               "For any other error, or if this retry fails, stop"):
    if phrase not in upgrade:
        raise AssertionError("LIMIT:upgrade-retry")
rules = [r for r in template["resources"] if r.get("kind") in ("Scheduled", "NRT")]
if len(rules) != 2 or {r["kind"] for r in rules} != {"Scheduled", "NRT"}:
    raise AssertionError("LIMIT:rule-kinds")
for rule in rules:
    properties = rule["properties"]
    if rule["kind"] == "Scheduled":
        for field, expected in (("queryPeriod", "P1D"), ("queryFrequency", "PT10M")):
            if properties.get(field) != expected:
                raise AssertionError("LIMIT:" + field)
    elif any(field in properties for field in ("queryPeriod", "queryFrequency")):
        raise AssertionError("LIMIT:nrt-cadence")
    grouping = properties["incidentConfiguration"]["groupingConfiguration"]
    if grouping.get("reopenClosedIncident") is not False:
        raise AssertionError("LIMIT:reopenClosedIncident")
    if grouping.get("lookbackDuration") != "P7D":
        raise AssertionError("LIMIT:lookbackDuration")

for name, document, heading in (
    ("README", README, "## 1. Register an application"),
    ("setup guide", SETUP, "## 1.0 App registrations"),
):
    section = document.split(heading, 1)[1].split("\n## ", 1)[0]
    for text in ("**All applications**", "filter by name", "SOCRadar Push/DCR",
                 "Reuse a suitable registration in your tenant", "Application (client) ID",
                 "Directory (tenant) ID", "service principal's Object ID",
                 "stored", "unexpired", "**same app registration**",
                 "Only if no suitable registration exists", "**New registration**"):
        if text not in section:
            raise AssertionError("%s missing reuse-first instruction: %s" % (name, text))
    if section.index("**All applications**") > section.index("**New registration**"):
        raise AssertionError("%s offers new registration before reuse search" % name)

if "Field | Value table" in README or "AlertBacked" in README:
    raise AssertionError("README retains superseded description or internal-table wording")
if "candidate" in README.lower() or "21861" in README:
    raise AssertionError("README retains internal candidate wording")
for output in ("DceUri", "DcrImmutableId", "StreamName", "TenantId", "LogIngestionUrl"):
    if output not in template["outputs"]:
        raise AssertionError("Unknown deployment output " + output)
    for name, document in (("README", README), ("setup guide", SETUP)):
        if not re.search(r"\b" + re.escape(output) + r"\b", document):
            raise AssertionError(name + " missing canonical output " + output)
for parameter in ("WorkspaceName", "DeployNewWorkspace", "WorkspaceLocation",
                  "ServicePrincipalObjectId", "TableRetentionDays"):
    if parameter not in template["parameters"]:
        raise AssertionError("Unknown deployment parameter " + parameter)
    for name, document in (("README", README), ("setup guide", SETUP)):
        if "`%s`" % parameter not in document:
            raise AssertionError(name + " missing canonical parameter " + parameter)

for document in (README, SETUP):
    assert not re.search(r"video|recording|preprod|Postman|off camera|demo workspace|we looked|synthetic|greenfield|task_azure|E2E", document, re.I), "Customer docs retain internal process language"
    assert not re.search(r"[ğşıİöüç—]", document), "Customer docs must use English without em dash"
    for phrase in ("4000 UTF-16", "connection.test", "Monitoring Metrics Publisher"):
        assert phrase in document, "Missing customer safety instruction: " + phrase
    for phrase in ("7 test runs", "6 completed with an incident", "under 4 seconds to about 7 minutes", "2 to 6 seconds", "2 to 4 minutes",
                   "not a guarantee", "30 minutes after sending", "incident missing",
                   "tag filters can hide a new incident", "`[SOCRadar]` title prefix",
                   "2 seconds to 2 minutes", "8 to 10 minutes", "observed range: about 7 to 11 minutes",
                   "20 seconds to 10 minutes", "20 seconds to 20 minutes", "client credentials", "Microsoft XDR",
                   "workspace was not connected to the Defender portal",
                   "Timings can differ in tenants without Defender"):
        normalized = " ".join(document.split())
        assert phrase in normalized, "Missing measured timing boundary: " + phrase
    assert "typically takes a few minutes" not in document, "Unmeasured delivery promise retained"
    normalized = " ".join(document.split())
    for phrase in ("The remaining test run produced a row and alert, but observation stopped after 15 minutes without an incident; later arrival was not measured.",
                   "These are periodic observations, not exact availability or tag-added times",
                   "Five completed runs used the application's own identity (client credentials).",
                   "The incomplete outcome did not recur in the subsequent runs; its cause was not determined.",
                   "Measurements used test submissions to new workspaces in one region, North Europe."):
        assert phrase in normalized, "Missing observation condition: " + phrase
    for obsolete in ("4 test runs", "3 completed", "Measured in 3 test runs:", "Measured in 2 completed test runs:",
                     "One completed run used", "its first API read was about 3 to 20 minutes"):
        assert obsolete not in normalized, "Superseded measurement population: " + obsolete
incomplete_paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", SETUP)
                         if "The remaining test run" in paragraph]
assert len(incomplete_paragraphs) == 1, "Incomplete run must have one unambiguous context"
assert "In 7 test runs, 6 completed with an incident." in " ".join(incomplete_paragraphs[0].split()), "Incomplete-run population must be explicit in the same paragraph"
readme_checks = README.split("## 5. Check\n", 1)[1].split("\n## ", 1)[0]
readme_things = README.split("## Things to know\n", 1)[1].split("\n## ", 1)[0]
for scope in (readme_checks, readme_things):
    normalized_scope = " ".join(scope.split())
    assert "7 test runs" in normalized_scope, "README timing sections must each retain seven runs"
    assert "6 completed with an incident" in normalized_scope, "README timing sections must each retain six completions"
    assert "20 seconds to 20 minutes after creation" in normalized_scope, "README tag timing sections must agree"
require("otherwise empty workspace", "NRT capacity accounts for existing rules")
require("Existing NRT rules reduce", "NRT capacity is not an unconditional remaining quota")
require("HTTP 204 alone is not end-to-end ingestion proof", "HTTP acknowledgement boundary")
require("A separate incident per alarm is not guaranteed", "URL grouping boundary")
deploy_pattern = r"\[!\[Deploy to Azure\].*?\]\((https://portal.azure.com/[^)]+)\)"
deploy = re.search(deploy_pattern, README)
assert deploy, "Customer Deploy button missing"
assert unquote(deploy.group(1)).endswith("/Radargoger/socradar-sentinel-push/main/azuredeploy.json"), "Customer Deploy button must use main"
deploy_buttons = re.findall(deploy_pattern, README)
assert len(deploy_buttons) == 2, "README must retain the top and section 2 Deploy buttons"
assert deploy_buttons[0] == deploy_buttons[1], "Both Deploy buttons must have the same target"
assert unquote(deploy_buttons[0]).split("/uri/", 1)[1] == "https://raw.githubusercontent.com/Radargoger/socradar-sentinel-push/main/azuredeploy.json", "Deploy target must be the public main template"
readme_lines = README.splitlines()
guide_line = readme_lines.index("For illustrated instructions, follow the [setup guide](docs/setup-guide.md).")
top_deploy = re.search(deploy_pattern, "\n".join(readme_lines[guide_line + 1:guide_line + 6]))
assert top_deploy and top_deploy.group(1) == deploy_buttons[0], "Deploy button must appear within five lines after the setup guide"
deploy_section = README.split("## 2. Deploy\n", 1)[1].split("\n## ", 1)[0]
section_deploy = re.search(deploy_pattern, deploy_section)
assert section_deploy and section_deploy.group(1) == deploy_buttons[0], "Section 2 must keep its Deploy button"
registration = README.split("## 1. Register an application\n", 1)[1].split("\n## ", 1)[0]
steps = dict(re.findall(r"(?m)^([1-4])\. (.+)$", registration))
assert set(steps) == {"1", "2", "3", "4"}, "Application registration steps missing"
assert "Application (client) ID" in steps["2"] and "Directory (tenant) ID" in steps["2"], "step 1.2 must provide identity values"
assert "secret" in steps["3"] and "Value" in steps["3"], "step 1.3 must provide secret Value"
assert "Object ID" in steps["4"] and "service principal" in steps["4"], "step 1.4 must provide service principal Object ID"
assert "## 9.0 Verify the row in Log Analytics" in SETUP
assert "## 10.0 Verify the alert and Defender incident" in SETUP
assert "### 10.1 Connect your workspace to Defender" in SETUP
assert "### 10.2 Inspect the alert and related incident" in SETUP
assert "using section 9.0" in SETUP and "Follow section 10.0" in SETUP
assert "docs/setup-guide.md#101-connect-your-workspace-to-defender" in README
outputs_section = SETUP.split("## 5.1 Outputs\n", 1)[1].split("\n## ", 1)[0]
assert "If the outputs are visible, continue at 6.0; if they are missing or you want to verify the role, use 5.2." in outputs_section, "Outputs must explain the next step"
resource_routes = SETUP.split("## 5.2 No outputs? Read them from the resources\n", 1)[1].split("\n## ", 1)[0]
for phrase in ("deployment's Outputs page", "**Resource groups**", "**Resources** list",
               "**SOCRadar-Push-DCE**", "**Overview**", "**Logs Ingestion**",
               "**SOCRadar-Alarms-Push-DCR**", "**JSON View**", "`immutableId`",
               "**Access control (IAM)**", "**Role assignments**", "**Monitoring Metrics Publisher**",
               "**your application**", "**This resource**", "**optional**", "**403**"):
    assert phrase in resource_routes, "Missing illustrated resource navigation: " + phrase
assert "A 403 response alone does not prove a role-assignment problem." in resource_routes
assert "Main setup steps 1 to 33 are unchanged." in resource_routes
assert "**Optional verification steps 34 to 37**" in resource_routes
for number, label in ((34, "**Access control (IAM)**"), (35, "**Role assignments**"),
                      (36, "**Monitoring Metrics Publisher**"), (37, "**Scope**")):
    step = re.search(r"(?m)^" + str(number) + r"\. (.+)$", resource_routes)
    assert step and label in step.group(1), "Role-check badge and instruction must agree"
assert "![Optional DCR send-role verification](images/5-2-role-assignment.jpg)" in resource_routes
role_image = ROOT / "docs/images/5-2-role-assignment.jpg"
assert role_image.is_file() and role_image.read_bytes().startswith(b"\xff\xd8\xff"), "Redacted role-check image must be a JPEG"
assert len(list((ROOT / "docs/images").glob("*.jpg"))) == 16, "Setup guide must ship sixteen JPG images"
if 'branches: [master, main, "e2e-*", "armttk0-0116"]' not in WORKFLOW:
    raise AssertionError("checks workflow does not include the permanent e2e branch policy")
if 'ARM-TTK must have zero failures' not in WORKFLOW or 'tests/check_arm_ttk.ps1' not in WORKFLOW:
    raise AssertionError("checks workflow does not enforce ARM-TTK")
if "python3 tests/mutate_description.py" not in WORKFLOW:
    raise AssertionError("checks workflow does not run description mutations")
if "python3 tests/mutate_limits.py" not in WORKFLOW:
    raise AssertionError("checks workflow does not run documented-limit mutations")

print("delivery documentation and checks workflow contract passed")
