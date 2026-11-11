# SOCRadar Alarms for Microsoft Sentinel (push)

This Incidents NRT integration receives SOCRadar alarms through the Azure Monitor Logs Ingestion API.
It deploys no Logic App, Function App or storage account.

The template creates the `SOCRadar_Push_Alarms_CL` table, a data collection endpoint and rule,
two analytic rules per alarm type (18 NRT rules and 18 scheduled backstop rules), an automation
rule that labels incidents `SOCRadar`, and the `SOCRadar Alarms` workbook. The Push table is separate from the pull template's `SOCRadar_Alarms_CL` table, so this deployment does not update it.
The scheduled rules only pick up what the NRT rules missed.

For illustrated instructions, follow the [setup guide](docs/setup-guide.md).

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FRadargoger%2Fsocradar-sentinel-push%2Fmain%2Fazuredeploy.json)

The deploy form needs the Service Principal Object ID; complete section 1 first.

Reuse or register an app, deploy to your Microsoft Sentinel workspace, configure SOCRadar,
then verify Test Connection and the next real alarm.

| Value | Goes to | Where |
|-------|---------|-------|
| Tenant ID, Application (client) ID | SOCRadar | App Overview page, step 1.2 |
| Application secret | SOCRadar | Certificates & secrets, step 1.3 |
| Service Principal Object ID | Deploy form | Enterprise application, step 1.4 |
| Data Collection Endpoint URI, Data Collection Rule immutable ID | SOCRadar | Deployment outputs, step 3 |

## 1. Register an application

First, open Azure portal > Microsoft Entra ID > App registrations. Use **Owned applications** for an app you own, or **All applications** for an app owned by someone else, and filter by name for an existing SOCRadar Push/DCR app registration. Reuse a suitable registration in your tenant: use its Application (client) ID, Directory (tenant) ID and its service principal's Object ID (step 1.4). Use its securely stored, unexpired client secret; if no usable secret is stored, create a new client secret on the **same app registration** (step 1.3). Do not delete or replace a secret used by another integration.

1. Only if no suitable registration exists, select **New registration**. Any name, no redirect URI, Register. Otherwise open the existing registration and continue with step 2.
2. On the Overview page copy the Application (client) ID and the Directory (tenant) ID.
3. If you already have a usable stored secret, use it. Otherwise, on the selected app: Certificates & secrets > New client secret. Copy the Value right away, it is shown once. Note the expiry date: when it expires, alarms stop until you enter a new secret in SOCRadar.
4. Get the Object ID of the app's service principal. This is the value for `ServicePrincipalObjectId` in the deployment form in section 2. It is not the Application (client) ID and not the Object ID shown on the App registrations page.
   1. Still on the app's Overview page under App registrations, find **Managed application in local directory** and click the app name next to it.
   2. The Enterprise application page opens. On its Overview (or Properties) page copy **Object ID**.

   Or with Azure CLI: `az ad sp show --id <Application (client) ID> --query id -o tsv`

This sender needs no additional Microsoft Graph API permissions and no admin consent. Its Azure
right is Monitoring Metrics Publisher on the data collection rule, which the template gives it when
you pass the service principal's Object ID. Leave permissions used by other integrations unchanged.

## 2. Deploy

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FRadargoger%2Fsocradar-sentinel-push%2Fmain%2Fazuredeploy.json)

The NRT rules use API version `2025-07-01-preview`.

Deployment needs permission to create resources and assign the DCR role: Owner, or Contributor
plus User Access Administrator, at the intended scope. The sender app itself only needs the DCR role.
To create a workspace, choose a resource group and set `DeployNewWorkspace=true`.
Use an unused `WorkspaceName` and the intended `WorkspaceLocation`; the default is `false`.

| Parameter | Description |
|-----------|-------------|
| `WorkspaceName` | Microsoft Sentinel workspace name (not the GUID) |
| `DeployNewWorkspace` | `false` uses an existing Microsoft Sentinel workspace in the same resource group; a name that does not exist fails before anything is created. `true` creates the workspace and enables Microsoft Sentinel on it. Default `false` |
| `WorkspaceLocation` | Region of the workspace. Defaults to the resource group region |
| `ServicePrincipalObjectId` | The Object ID from step 1.4. Empty: no role is assigned, and you give the app the Monitoring Metrics Publisher role on the data collection rule yourself |
| `TableRetentionDays` | Retention of `SOCRadar_Push_Alarms_CL`. Default 90 |

**Note:** with the default, the workspace in `WorkspaceName` must already exist in the resource group, unless you set `DeployNewWorkspace` to `true`.

For a new installation, follow the Deploy steps above. To update an existing installation already using `SOCRadar_Push_Alarms_CL`, redeploy into the same resource group with the same values.

### Updating an existing Push installation

If your installation currently uses `SOCRadar_Alarms_CL`, use this migration path:

1. Keep `SOCRadar_Alarms_CL` for its history and record any of your own KQL queries that read it.
2. Redeploy this template to the same resource group with the same values. The input stream and SOCRadar form fields are unchanged; the DCR, rules and workbook switch to `SOCRadar_Push_Alarms_CL`.
3. Update your own KQL queries to `SOCRadar_Push_Alarms_CL`. The new workbook starts empty, so it does not show history from the old table. Queries that still use `SOCRadar_Alarms_CL` do not receive new rows. Use a `union` query only when you need both histories together.
4. When the first real alarm arrives, verify one row in the new table, one incident, and no duplicate incident. Existing rows are not copied.

On the first upgrade deployment, two analytic rules can fail with `One of the tables does not exist` while the new table is not yet queryable. Only for that error, wait until `SOCRadar_Push_Alarms_CL | take 0` succeeds in Logs, then redeploy the same template once more with the same values. For any other error, or if this retry fails, stop and inspect the deployment errors.

Template rollback changes the declared routing and queries; it does not copy data between tables.
Verify the destination of a newly sent row before treating data routing as restored.

For a rollback, redeploy the frozen [last stable template](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Forcunsami%2FSOCRadar-Sentinel-Push%2Fd887b39123f95171f54adb2b9965b69c6b4c9314%2Fazuredeploy.json) with the previous values. This is a migration rollback only: it does not move rows between `SOCRadar_Push_Alarms_CL` and `SOCRadar_Alarms_CL`.

## 3. Copy the outputs

Open the deployment > Outputs. The source names are `DceUri`, `DcrImmutableId`, `StreamName`,
`TenantId` and `LogIngestionUrl`. Copy `DceUri` and `DcrImmutableId` into SOCRadar.
`StreamName` must be `Custom-SOCRadarAlarmsPush`; `TenantId` is the subscription tenant.
Older screenshots show `dceUri`, `dcrImmutableId` and `tenantId` in lower case.

The same values are on the resources: data collection endpoint > Overview > Logs Ingestion, and data collection rule > Overview > Immutable ID.

## 4. Enter the values in SOCRadar

| SOCRadar field | Value |
|----------------|-------|
| Tenant ID | Directory (tenant) ID, step 1.2 |
| Application (client) ID | Application (client) ID, step 1.2 |
| Application secret | the secret value, step 1.3 |
| Data Collection Endpoint URI | `DceUri`, step 3 |
| Data Collection Rule immutable ID | `DcrImmutableId`, step 3 |

## 5. Check

Follow the [setup guide's checks](docs/setup-guide.md#70-test-connection):

1. Select **Test Connection** in SOCRadar, then query `SOCRadar_Push_Alarms_CL` for
   `EventType == "connection.test"`. This row confirms the test reached the table and opens no incident.
2. Wait for the next real `alarm.created` / `OPEN` alarm. Match its entry in SOCRadar **Recent Deliveries**
   to its row in `SOCRadar_Push_Alarms_CL`, the alert and the related incident.

Measured in 7 test runs: 6 completed with an incident. These timings are not a guarantee.
Measurements used test submissions to new workspaces in one region, North Europe.
The first alarm usually reached the table in about 5 to 6 minutes (observed range: under 4 seconds
to about 7 minutes); subsequent alarms took about 2 to 6 seconds. Row to NRT alert took about
2 to 4 minutes; alert to reported incident creation took about 2 seconds to 2 minutes.
For the first incident, expect about 8 to 10 minutes after sending (observed range: about 7 to 11 minutes).

The first ARM API read found the incident about 20 seconds to 10 minutes after creation;
the `SOCRadar` tag's first API read was about 20 seconds to 20 minutes after creation.
These are periodic observations, not exact availability or tag-added times.
Five completed runs used the application's own identity (client credentials).

The remaining test run produced a row and alert, but observation stopped after 15 minutes without an incident; later arrival was not measured.
The incomplete outcome did not recur in the subsequent runs; its cause was not determined.
Wait at least 30 minutes after sending before declaring an incident missing. Search by the
`[SOCRadar]` title prefix while the tag is pending; tag filters can hide a new incident.

The test tenant was connected to Defender and used incident provider Microsoft XDR. The test
workspace was not connected to the Defender portal, so these measurements do not establish portal
visibility timing. Timings can differ in tenants without Defender.

## Analytics rules

One pair of rules (NRT and scheduled backstop) per main type, matched by `AlarmMainType` (exact text), plus `Other` for every type not in the list. Each rule carries the MITRE tactics and techniques below.

| Main type | Tactics | Techniques |
|---|---|---|
| Executive Protection | Reconnaissance | T1589, T1593 |
| Fraud Protection | InitialAccess | T1566 |
| Vulnerability Monitoring | Reconnaissance, InitialAccess | T1595, T1190 |
| Deep&Dark Web Monitoring | CredentialAccess | T1555, T1110 |
| Internet Asset Inventory Monitoring | Reconnaissance | T1595 |
| Configuration Weakness | InitialAccess | T1190 |
| Supply Chain Intelligence | InitialAccess | T1195 |
| Brand Protection | ResourceDevelopment, InitialAccess | T1583, T1566 |
| VIP Protection | Reconnaissance | T1589 |
| Surface Web Monitoring | Reconnaissance, Exfiltration | T1593, T1567 |
| Vulnerability Intelligence | Reconnaissance, InitialAccess | T1595, T1190 |
| Threat Hunting | InitialAccess, CommandAndControl | T1566, T1071 |
| Attack Surface Management | Reconnaissance | T1595, T1596 |
| Industry Attacks Monitoring | Reconnaissance | T1591 |
| Botnet | CredentialAccess | T1555, T1056 |
| Phishing Domain | ResourceDevelopment, InitialAccess | T1583, T1566 |
| Domain | ResourceDevelopment, InitialAccess | T1583, T1566 |
| Other | none | none |

The template uses 18 of the 50 NRT rule slots per workspace. In an otherwise empty workspace,
32 slots remain; existing NRT rules reduce that capacity.

## Where to see it in the Microsoft Defender portal

Before checking incidents, open **Microsoft Defender > System > Settings > Microsoft Sentinel >
Connect a workspace** and select your workspace. If it is already connected, skip reconnection.
Keep an existing primary unchanged and add your workspace as secondary. Do not disconnect other
workspaces. For a tenant's first onboarding, follow Microsoft's primary-selection procedure with
its administrator. Confirm the workspace appears connected in **Workspaces / SIEM workspaces**.
Enabling Sentinel in the template does not establish this connection. RG Owner alone is insufficient;
see the [guide's connection steps](docs/setup-guide.md#101-connect-your-workspace-to-defender),
Microsoft's [onboarding procedure](https://learn.microsoft.com/en-us/unified-secops/microsoft-sentinel-onboard)
and [role/scope requirements](https://learn.microsoft.com/en-us/azure/sentinel/workspaces-defender-portal).

| What | Defender portal |
|---|---|
| Incidents | Investigation & response > Incidents & alerts > Incidents (called Cases in some tenants). If the list looks empty, select **Reset all** and check the time range and workspace; a priority filter can hide incidents. |
| Category and priority | The category reflects the rule's tactics. A low priority score does not mean delivery failed. |
| Finding SOCRadar incidents | The `SOCRadar` label, shown as a tag, or the title `[SOCRadar] #<alarm id> - <title>` |
| Description | Alarm fields and content as plain `key: value` lines, with a link to the source alarm |
| Alert details | Open the alert for the rule name, entities, custom details and Related events > Query results with its `SOCRadar_Push_Alarms_CL` row |
| The table in KQL | Investigation & response > Hunting > Advanced hunting: `SOCRadar_Push_Alarms_CL` (also reads secondary workspaces) |
| Dashboard | Microsoft Sentinel > Threat management > Workbooks. The Defender Workbooks page shows only the primary workspace; for a secondary workspace, use Advanced hunting or Azure Logs. |

## Things to know

- In 7 test runs, 6 completed with an incident. The `SOCRadar` tag's first API read was about
  20 seconds to 20 minutes after creation. These periodic observations are not a guarantee.
  Search by the `[SOCRadar]` title prefix and
  wait at least 30 minutes after sending before declaring an incident missing; see the timings in section 5.
- Each alarm type has two rules: `SOCRadar alarm (NRT): <type>` and `SOCRadar alarm: <type>`. To stop incidents for a type, switch off both.
- The template uses 18 of the 50 NRT rule slots per workspace; 32 remain only in an otherwise
  empty workspace. Existing NRT rules reduce the remaining capacity.
- A resent alarm is added as a second alert to its open incident when the same rule raised both alerts within 7 days. A closed incident is not reopened; a new one opens.
- URL grouping can also place alerts with different `AlarmId` values from the same rule and URL in one incident. A separate incident per alarm is not guaranteed.
- `AlarmText` is truncated to 4000 UTF-16 code units, not 4000 Unicode code points. For example, 1100 emoji plus 1800 `a` characters use 2900 code points but 4000 UTF-16 units.
- HTTP 204 alone is not end-to-end ingestion proof. Validate the JSON locally before sending, then verify the matching row and fields in Log Analytics.
- The NRT rule sometimes raises two alerts for one alarm. They can share an open incident under
  the grouping conditions above; a closed incident is not reopened.
- Per alarm type the NRT rule takes about 30 alarms a minute. The backstop rule takes 149 every 10 minutes and sees rows from 12 minutes to 1 day old, so a big burst of one type still gets incidents, only later: about 900 an hour. An alarm that stays without an incident for a whole day (for example, the rules were switched off) does not get one later.
- Rules skip rows with `EventType` `connection.test`, so SOCRadar's Test connection opens no incident.
- `TimeGenerated` is the time the row reached Azure, so a late alarm is still seen by the rules. The alarm's own time is in `AlarmDate`.
- Normal push delivery is for alarms emitted after setup; it does not backfill history.
- The incident description lists the alarm ID, types, severity, status, date and text, then alarm content as plain
  `key: value` lines and a link to the alarm in SOCRadar. Nested arrays and objects are formatted as readable values
  before the alert is sent. Check the description and source link in your incident.
- A very long alarm URL is omitted with an explicit marker instead of a truncated link. At the mixed UTF-8 tail
  byte-limit fallback, alarm content can be omitted so the description stays within its size limit.
- Incidents are not written back to SOCRadar. Closing an incident does not change the alarm.
- Push and pull use separate tables. Configure only one delivery route for an alarm feed unless duplicate incidents are intended.
- Do not install Push and CCF pull in the same workspace. They share GUID seeds, so CCF rules can target the Push
  table and silently stop opening incidents for CCF alarms. Do not combine these installations during an upgrade or rollback.

## Microsoft limits

| Limit | Value | Source |
|---|---|---|
| NRT rule run | every minute, 2 minute delay, up to 30 alerts (29 + 1 summary) | [NRT rules](https://learn.microsoft.com/en-us/azure/sentinel/near-real-time-rules) |
| NRT rules | 50 per workspace | same |
| Scheduled rule run | every 5 minutes or more, 5 minute delay, up to 150 alerts (149 + 1 summary) | [Scheduled rules](https://learn.microsoft.com/en-us/azure/sentinel/scheduled-rules-overview) |
| Request size | 1 MB | [Logs Ingestion API](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-limits#logs-ingestion-api) |
| Requests per DCR | 12,000 per minute, 2 GB per minute | same |

## Remove

1. Turn the Microsoft Sentinel integration off in SOCRadar, so it stops sending.
2. In the workspace: delete the 36 analytic rules `SOCRadar alarm (NRT): ...` and `SOCRadar alarm: ...`, the automation rule `SOCRadar - label incidents opened by the alarm rules` and the `SOCRadar Alarms` workbook.
3. In the resource group: delete the data collection rule `SOCRadar-Alarms-Push-DCR`, then the endpoint `SOCRadar-Push-DCE`, then the `SOCRadar_Push_Alarms_CL` table. Do not delete `SOCRadar_Alarms_CL`: it can retain legacy Push history or be shared with Pull.
4. Delete the app registration in Microsoft Entra ID only if it is dedicated to this Push installation. A reused app registration can serve other DCR integrations.

If the template created the workspace, deleting the workspace also removes the rules, the table and the data in it. The data collection rule and endpoint stay in the resource group until you delete them.
