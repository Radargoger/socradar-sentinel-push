# SOCRadar Alarms → Microsoft Sentinel (Push)

Send SOCRadar alarms straight into Microsoft Sentinel through the Azure Monitor Logs Ingestion API.

**No Logic App. No Function App. No virtual machine.** The only things this creates in your
subscription are a Data Collection Endpoint, a Data Collection Rule, a custom table and one role
assignment — configuration objects with nothing to run, maintain or restart. You pay Microsoft's
standard Sentinel ingestion for the data that arrives, and nothing else.

```
SOCRadar platform (alarm created)
   │  1. Entra token  (client credentials, scope https://monitor.azure.com/.default)
   │  2. POST {DCE}/dataCollectionRules/{DCR}/streams/Custom-SOCRadarAlarmsPush?api-version=2023-01-01
   ▼
Data Collection Endpoint ──► Data Collection Rule ──► SOCRadar_Alarms_CL ──► your analytics
```

## Setup

You need: a Log Analytics workspace with Microsoft Sentinel, permission to register an application
in Microsoft Entra ID, and Owner or User Access Administrator on the resource group (the template
creates a role assignment).

### 1. Register an application

Azure portal → **Microsoft Entra ID** → **App registrations** → **New registration**.
Name it (for example `SOCRadar Alarms Push`), leave the redirect URI empty, **Register**.

From the app's **Overview** page copy:
- **Application (client) ID**
- **Directory (tenant) ID**

Then **Certificates & secrets** → **New client secret** → copy the **Value** immediately; it is shown
only once. Note the expiry date you pick — when the secret expires, alarms stop until you create a
new one and update it in SOCRadar.

Finally, **Microsoft Entra ID** → **Enterprise applications** → open the same app → copy its
**Object ID**. This is the value the template needs (it is *not* the same as the Application ID).

### 2. Deploy

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FRadargoger%2Fsocradar-sentinel-push%2Fmain%2Fazuredeploy.json)

Fill in:

| Field | Value |
|---|---|
| Resource group | the one that holds your Sentinel workspace |
| Workspace name | your Log Analytics workspace name |
| Location | leave as is — it must match the workspace region |
| Service principal object id | the **Object ID** from step 1 |

When the deployment finishes, open it and go to **Outputs**. Copy:
- `dataCollectionEndpoint`
- `dataCollectionRuleImmutableId`

### 3. Enter the values in SOCRadar

SOCRadar platform → **Settings → Integrations → Microsoft Sentinel (Push)**:

| SOCRadar field | Where it came from |
|---|---|
| Tenant ID | step 1, Directory (tenant) ID |
| Application (client) ID | step 1, Application (client) ID |
| Application secret | step 1, the secret value |
| Data Collection Endpoint URI | step 2, `dataCollectionEndpoint` |
| Data Collection Rule immutable ID | step 2, `dataCollectionRuleImmutableId` |

Select **Test connection**, then **Save**.

### 4. Confirm the data

In Microsoft Sentinel → **Logs**:

```kusto
SOCRadar_Alarms_CL
| sort by TimeGenerated desc
| take 20
```

Allow **5–10 minutes** for the first rows: a newly created table and a fresh role assignment both
take a few minutes to become usable. The test connection writes one row with
`EventType == "connection.test"`.

## What gets created

| Resource | Purpose |
|---|---|
| `SOCRadar_Alarms_CL` table | where alarms land |
| Data Collection Endpoint | the HTTPS endpoint SOCRadar posts to |
| Data Collection Rule | validates each record and routes it to the table |
| `Monitoring Metrics Publisher` on that rule | lets the application write to that one rule, and nothing else |

The application has no other permission in your tenant, and SOCRadar never receives any credential of
yours beyond the secret you create for this app.

## The table

| Column | Type | Notes |
|---|---|---|
| `TimeGenerated` | datetime | the alarm's own time, not the ingestion time |
| `AlarmId` | string | |
| `CompanyId` | string | |
| `AlarmMainType` / `AlarmSubType` | string | |
| `Severity` | string | `Critical`, `High`, `Medium`, `Low`, `Info` |
| `Status` | string | upper case, as in SOCRadar |
| `Title` | string | |
| `AlarmText` | string | plain text |
| `AlarmDate` | string | ISO-8601 UTC |
| `AlarmPayload` | dynamic | the full original alarm |
| `EventType` | string | `alarm.created` or `connection.test` |
| `CompanyName`, `AlarmAsset`, `AlarmUrl`, `Tags`, `AlarmUpdatedAt`, `ConnectorVersion` | | |

`AlarmUrl` links back to the alarm in SOCRadar, so an incident can be opened from Sentinel in one
click.

### Example: detect High and Critical alarms

```kusto
SOCRadar_Alarms_CL
| where Severity in ("High", "Critical")
| where Status == "OPEN"
| project TimeGenerated, AlarmId, Title, AlarmMainType, AlarmSubType, Severity, Status, AlarmUrl
```

## Scope

Alarms flow one way, SOCRadar → Sentinel. Incidents you close in Sentinel are not written back.
Only alarms created after the integration is enabled are sent; history is not backfilled.

## Removing it

Delete the Data Collection Rule, the Data Collection Endpoint and the `SOCRadar_Alarms_CL` table from
the resource group, and delete the app registration in Microsoft Entra ID. Disable the integration in
SOCRadar first so it stops sending.
