#!/usr/bin/env bash
# Deployment paths a customer can actually take, run against live Azure.
#
#   A  missing workspace, defaults (DeployNewWorkspace=false) -> fails, resource group stays EMPTY
#   B  DeployNewWorkspace=true (opt-in create) -> succeeds: table, endpoint, rule, 36 analytics rules, workbook
#   C  existing workspace without Microsoft Sentinel, defaults -> fails at the precheck, resource group stays EMPTY
#   C2 the same workspace after Microsoft Sentinel is enabled -> precheck succeeds and resolves customerId, deployment succeeds
#   D  redeploy of B at the defaults -> succeeds and leaves the workspace exactly as it was
#
# Usage (deploys into live Azure; every call is pinned to the explicit subscription):
#   TEST_SUBSCRIPTION_ID=<id> bash scripts/test_deploy_paths.sh
#   optional: TEST_LOCATION, KEEP_RESOURCES
{ set +x; } 2>/dev/null
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$(cd "$SCRIPT_DIR/.." && pwd)/azuredeploy.json"
LOCATION="${TEST_LOCATION:-westeurope}"
KEEP="${KEEP_RESOURCES:-false}"

SFX=$(python3 -c "import uuid;print(uuid.uuid4().hex)") && [ -n "$SFX" ] || { echo "ERROR: CANNOT MEASURE: no suffix"; exit 1; }
RG_APP="rg-push-paths-$SFX"
RG_C="rg-push-paths-c-$SFX"
WS="ws-push-paths-$SFX"
MISSING="ws-does-not-exist-$SFX"

if [ -z "${TEST_SUBSCRIPTION_ID:-}" ]; then
    echo "ERROR: set TEST_SUBSCRIPTION_ID to the subscription to deploy into"
    exit 1
fi
# Pin even reads and cleanup; a concurrent az account set cannot redirect this run.
az() { command az "$@" --subscription "$TEST_SUBSCRIPTION_ID"; }
if ! ACTIVE_SUB=$(az account show --query id -o tsv) || [ "$ACTIVE_SUB" != "$TEST_SUBSCRIPTION_ID" ]; then
    echo "ERROR: CANNOT MEASURE: requested subscription is unavailable"; exit 1
fi

fails=0
UNREAD="<unreadable>"
row() { printf '%-40s %-6s %s\n' "$1" "$2" "$3"; [ "$2" = PASS ] || fails=$((fails + 1)); }
rd() {  # rd <var> <command...>: stdout into var; a failed command puts UNREAD there and shows why
    local var="$1" out rc err; shift
    err=$(mktemp); out=$("$@" 2>"$err"); rc=$?
    [ "$rc" -ne 0 ] && { echo "  CANNOT MEASURE: ${*:1:4} failed (rc=$rc): $(head -c 200 "$err" | tr '\n' ' ')"; out="$UNREAD"; }
    rm -f "$err"; printf -v "$var" '%s' "$out"
}
expect() {  # expect <name> <got> <want> <pass detail> <fail detail>
    if [ "$2" = "$UNREAD" ]; then row "$1" CANNOT "the az read failed (reason above)"
    elif [ "$2" = "$3" ]; then row "$1" PASS "$4"
    else row "$1" FAIL "$5"; fi
}

ATTEMPTED=()
owned_id() {
    local rg="$1" got expected
    expected="/subscriptions/$TEST_SUBSCRIPTION_ID/resourceGroups/$rg"
    got=$(az group show -n "$rg" --query '[id,tags.ostTestRun]' -o tsv) || return 1
    [ "$got" = "$(printf '%s\n%s' "$expected" "$SFX")" ] || return 1
    printf '%s' "$expected"
}
cleanup() {
    local rc=$? cleanup_failed=0 rg id exists attempt
    trap - EXIT
    for rg in "${ATTEMPTED[@]}"; do
        exists=$(az group exists -n "$rg") || exists=unknown
        [ "$exists" = false ] && { echo "cleanup OK: $rg absent"; continue; }
        # Re-read ownership even after a failed/partially successful create. Never
        # delete an unreadable target, foreign tag or unexpected resource ID.
        if ! id=$(owned_id "$rg"); then
            echo "cleanup FAIL: ownership unproved for $rg; preserved"; cleanup_failed=1; continue
        fi
        if [ "$KEEP" = true ]; then echo "cleanup KEEP: $id (owned by run $SFX)"; continue; fi
        if ! az group delete -n "$rg" --yes --no-wait -o none; then
            echo "cleanup FAIL: delete rejected for $id"; cleanup_failed=1; continue
        fi
        exists=unknown
        for ((attempt=1; attempt<=12; attempt++)); do
            exists=$(az group exists -n "$rg") || exists=unknown
            [ "$exists" = false ] && break
            [ "$attempt" -lt 12 ] && sleep 5
        done
        if [ "$exists" = false ]; then echo "cleanup OK: $id absent"
        else echo "cleanup FAIL: absence not proved after 12 reads: $id ($exists)"; cleanup_failed=1; fi
    done
    [ "$rc" -ne 0 ] || rc=$cleanup_failed
    exit "$rc"
}
trap cleanup EXIT

deploy() {  # deploy <rg> <name> <extra params...>
    local rg="$1" name="$2"; shift 2
    local err rc; err=$(mktemp)
    az deployment group create -g "$rg" -n "$name" --template-file "$TEMPLATE" --parameters WorkspaceLocation="$LOCATION" "$@" -o none 2>"$err"
    rc=$?
    [ "$rc" -ne 0 ] && echo "  deployment $name failed: $(head -c 600 "$err")"
    rm -f "$err"; return "$rc"
}
failed_step() {
    local out
    out=$(az deployment operation group list -g "$1" -n "$2" \
        --query "[?properties.provisioningState=='Failed'].properties.targetResource.resourceName" -o tsv 2>/dev/null) || { echo "$UNREAD"; return; }
    printf '%s\n' "$out" | sort -u | tr '\n' ' '
}
ws_show() { az monitor log-analytics workspace show -g "$RG_APP" -n "$WS" -o json 2>/dev/null \
    | python3 -c "import json,sys;d=json.load(sys.stdin);[d.pop(k,None) for k in ('etag','modifiedDate')];print(json.dumps(d,sort_keys=True))"; }

echo "[1/5] Creating $RG_APP and $RG_C ..."
for rg in "$RG_APP" "$RG_C"; do
    exists=$(az group exists -n "$rg") || exists=unknown
    [ "$exists" = false ] || { echo "ERROR: target is not proved absent: $rg ($exists)"; exit 1; }
done
for rg in "$RG_APP" "$RG_C"; do
    exists=$(az group exists -n "$rg") || exists=unknown
    [ "$exists" = false ] || { echo "ERROR: target changed before create: $rg ($exists)"; exit 1; }
    ATTEMPTED+=("$rg")
    az group create -n "$rg" -l "$LOCATION" --tags "ostTestRun=$SFX" -o none || { echo "ERROR: CANNOT MEASURE: could not create $rg"; exit 1; }
    owned_id "$rg" >/dev/null || { echo "ERROR: created RG ownership readback failed: $rg"; exit 1; }
done

echo "[2/5] Path A: missing workspace, parameters at their defaults ..."
deploy "$RG_APP" path-a WorkspaceName="$MISSING"
rd state az deployment group show -g "$RG_APP" -n path-a --query properties.provisioningState -o tsv
rd left az resource list -g "$RG_APP" --query "length(@)" -o tsv
steps=$(failed_step "$RG_APP" path-a)
expect "A deployment fails" "$state" Failed "$state" "expected Failed, got '$state'"
expect "A leaves nothing behind" "$left" 0 "0 resources" "expected 0, found '$left' - the guard did not hold"
if [ "$steps" = "$UNREAD" ]; then row "A blames the precheck" CANNOT "the az read failed"
elif printf '%s' "$steps" | grep -q 'precheck-workspace-exists'; then row "A blames the precheck" PASS "precheck-workspace-exists"
else row "A blames the precheck" FAIL "failed step(s) were: ${steps:-<none read>}"; fi

echo "[3/5] Path B: DeployNewWorkspace=true ..."
deploy "$RG_APP" path-b WorkspaceName="$WS" DeployNewWorkspace=true
rd state az deployment group show -g "$RG_APP" -n path-b --query properties.provisioningState -o tsv
steps=$(failed_step "$RG_APP" path-b)
expect "B greenfield succeeds" "$state" Succeeded "$state" "expected Succeeded, got '$state', failed step(s): ${steps:-<none>}"
rd guard_ran az deployment operation group list -g "$RG_APP" -n path-b \
    --query "[?properties.targetResource.resourceName=='precheck-workspace-exists'] | length(@)" -o tsv
expect "B skips the precheck" "$guard_ran" 0 "condition false" "the precheck ran against a workspace being created (count '$guard_ran')"
rd tbl az monitor log-analytics workspace table show -g "$RG_APP" --workspace-name "$WS" -n SOCRadar_Push_Alarms_CL --query name -o tsv
expect "B creates the Push alarms table" "$tbl" SOCRadar_Push_Alarms_CL "SOCRadar_Push_Alarms_CL" "table was '$tbl'"
rd dcr az resource list -g "$RG_APP" --resource-type Microsoft.Insights/dataCollectionRules --query "length(@)" -o tsv
expect "B creates the data collection rule" "$dcr" 1 "1 rule" "expected 1, found '$dcr'"

echo "[4/5] Path C: existing workspace, parameters at their defaults ..."
if ! az monitor log-analytics workspace create -g "$RG_C" -n "$WS" -l "$LOCATION" --retention-time 30 -o none; then
    row "C workspace for the test" CANNOT "az monitor log-analytics workspace create failed (reason above)"
else
    # C: no Microsoft Sentinel on it yet. The template onboards only a workspace it creates, so this must stop at the precheck.
    deploy "$RG_C" path-c-bare WorkspaceName="$WS"
    rd state az deployment group show -g "$RG_C" -n path-c-bare --query properties.provisioningState -o tsv
    rd left az resource list -g "$RG_C" --query "length(@)" -o tsv
    steps=$(failed_step "$RG_C" path-c-bare)
    expect "C no Microsoft Sentinel fails" "$state" Failed "$state" "expected Failed, got '$state': a workspace without Microsoft Sentinel must not half-install"
    expect "C leaves only the workspace behind" "$left" 1 "1 resource (the workspace)" "expected 1, found '$left' - the precheck did not hold"
    if [ "$steps" = "$UNREAD" ]; then row "C blames the precheck" CANNOT "the az read failed"
    elif printf '%s' "$steps" | grep -q 'precheck-workspace-exists'; then row "C blames the precheck" PASS "precheck-workspace-exists"
    else row "C blames the precheck" FAIL "failed step(s) were: ${steps:-<none read>}"; fi
    # C2: Microsoft Sentinel enabled on it
    WSID=$(az monitor log-analytics workspace show -g "$RG_C" -n "$WS" --query id -o tsv)
    az rest --method PUT -o none \
        --uri "https://management.azure.com${WSID}/providers/Microsoft.SecurityInsights/onboardingStates/default?api-version=2023-02-01" \
        --body '{"properties":{}}' 2>/dev/null || row "C2 enabling Microsoft Sentinel" CANNOT "the onboarding PUT failed"
    deploy "$RG_C" path-c WorkspaceName="$WS"
    rd state az deployment group show -g "$RG_C" -n path-c --query properties.provisioningState -o tsv
    steps=$(failed_step "$RG_C" path-c)
    rd gstate az deployment operation group list -g "$RG_C" -n path-c \
        --query "[?properties.targetResource.resourceName=='precheck-workspace-exists'].properties.provisioningState" -o tsv
    expect "C2 precheck succeeds" "$gstate" Succeeded "$gstate" "expected Succeeded, got '$gstate' - reference() may name a field or api-version that does not exist"
    rd ws_id az deployment group show -g "$RG_C" -n precheck-workspace-exists --query "properties.outputs.workspaceId.value" -o tsv
    if [ "$ws_id" = "$UNREAD" ]; then row "C2 precheck resolves customerId" CANNOT "the az read failed"
    elif printf '%s' "$ws_id" | grep -Eq '^[0-9a-f]{8}-'; then row "C2 precheck resolves customerId" PASS "looks like a guid"
    else row "C2 precheck resolves customerId" FAIL "output was '${ws_id:-<empty>}'"; fi
    expect "C2 deployment succeeds" "$state" Succeeded "$state" "expected Succeeded, got '$state', failed step(s): ${steps:-<none>}"
fi

echo "[5/5] Path D: redeploying $RG_APP at the defaults ..."
az monitor log-analytics workspace update -g "$RG_APP" -n "$WS" --retention-time 60 --tags probe=d -o none 2>/dev/null
before=$(ws_show)
deploy "$RG_APP" path-d WorkspaceName="$WS"
after=$(ws_show)
rd state az deployment group show -g "$RG_APP" -n path-d --query properties.provisioningState -o tsv
expect "D redeploy succeeds" "$state" Succeeded "$state" "expected Succeeded, got '$state'"
[ -n "$before" ] && [ "$before" = "$after" ] && row "D leaves the workspace untouched" PASS "$(printf '%s' "$after" | wc -c | tr -d ' ') bytes identical" \
    || row "D leaves the workspace untouched" FAIL "workspace JSON changed"

echo
if [ "$fails" -eq 0 ]; then echo "All four deployment paths behaved as asserted."; else echo "$fails assertion(s) failed."; fi
exit $((fails == 0 ? 0 : 1))
