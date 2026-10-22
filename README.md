# SOCRadar Alarms for Microsoft Sentinel (push)

SOCRadar sends each new alarm to your workspace through the Azure Monitor Logs Ingestion API.
Nothing runs in your Azure subscription: no Logic App, no Function App, no storage account.

The template creates the `SOCRadar_Alarms_CL` table, a data collection endpoint and rule,
two analytic rules per alarm type (10 NRT rules and 10 scheduled backstop rules), an automation
rule that labels incidents `SOCRadar`, and the `SOCRadar Alarms` workbook. Table, workbook and
incidents are the same as in the pull template (SOCRadar-Azure-Incidents-CCF).
The scheduled rules only pick up what the NRT rules missed.

## 1. Register an application

1. Azure portal > Microsoft Entra ID > App registrations > New registration. Any name, no redirect URI, Register.
2. On the Overview page copy the Application (client) ID and the Directory (tenant) ID.
3. Certificates & secrets > New client secret. Copy the Value right away, it is shown once. Note the expiry date: when it expires, alarms stop until you enter a new secret in SOCRadar.
4. Get the Object ID of the app's service principal. This is the value for `ServicePrincipalObjectId` in step 2. It is not the Application (client) ID and not the Object ID shown on the App registrations page.
   1. Still on the app's Overview page under App registrations, find **Managed application in local directory** and click the app name next to it.
   2. The Enterprise application page opens. On its Overview (or Properties) page copy **Object ID**.

   Or with Azure CLI: `az ad sp show --id <Application (client) ID> --query id -o tsv`

The app needs no API permissions and no admin consent. Its only right is the Monitoring Metrics Publisher role on the data collection rule, which the template gives it when you pass the Object ID.

## 2. Deploy

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FRadargoger%2Fsocradar-sentinel-push%2Fmain%2Fazuredeploy.json)

When you set `ServicePrincipalObjectId`, you need Owner or User Access Administrator on the resource group (the template assigns a role).

| Parameter | Description |
|-----------|-------------|
| `WorkspaceName` | Microsoft Sentinel workspace name (not the GUID) |
| `DeployNewWorkspace` | `true` creates the workspace and enables Microsoft Sentinel on it. `false` uses an existing Microsoft Sentinel workspace in the same resource group. Default `true` |
| `WorkspaceLocation` | Region of the workspace. Defaults to the resource group region |
| `ServicePrincipalObjectId` | The Object ID from step 1.4. Empty: no role is assigned, and you give the app the Monitoring Metrics Publisher role on the data collection rule yourself |
| `TableRetentionDays` | Retention of `SOCRadar_Alarms_CL`. Default 90 |

To update an existing setup to the latest template, deploy again into the same resource group with the same values.

## 3. Copy the outputs

Open the deployment > Outputs and copy `DceUri` and `DcrImmutableId`. `TenantId` is the tenant of the subscription.

## 4. Enter the values in SOCRadar

| SOCRadar field | Value |
|----------------|-------|
| Tenant ID | Directory (tenant) ID, step 1.2 |
| Application (client) ID | Application (client) ID, step 1.2 |
| Application secret | the secret value, step 1.3 |
| Data Collection Endpoint URI | `DceUri`, step 3 |
| Data Collection Rule immutable ID | `DcrImmutableId`, step 3 |

## 5. Check

```
SOCRadar_Alarms_CL | take 10
```

The first rows of a new table can take up to 15 minutes. After that, a new alarm should open an incident
titled `[SOCRadar] #<alarm id> - <title>` in about 3-5 minutes (NRT rule). An NRT rule raises at most
30 alerts per run, so if more than 30 alarms of one type arrive in one minute, the backstop scheduled
rule for that type picks up the rest, 149 every 10 minutes, starting 12 to 22 minutes after they arrive.
Measured: 150 alarms of one type in one minute all had incidents after 21 minutes, 300 after 31 minutes.
Above 30, the NRT rule also opens one summary incident that carries the title of the first alarm.

## Things to know

- Each alarm type has two rules: `SOCRadar alarm (NRT): <type>` and `SOCRadar alarm: <type>`. To stop incidents for a type, switch off both.
- The template adds 10 NRT rules. Microsoft: "No more than 50 rules can be defined per customer."
- A resent alarm is added as a second alert to its open incident when the same rule raised both alerts within 7 days. A closed incident is not reopened; a new one opens.
- The NRT rule sometimes raises two alerts for one alarm. Both land in the same incident.
- Per alarm type the NRT rule takes about 30 alarms a minute. The backstop rule takes 149 every 10 minutes and sees rows from 12 minutes to 1 day old, so a big burst of one type still gets incidents, only later: about 900 an hour. An alarm that stays without an incident for a whole day (for example, the rules were switched off) does not get one later.
- Rules skip rows with `EventType` `connection.test`, so SOCRadar's Test connection opens no incident.
- `TimeGenerated` is the time the row reached Azure, so a late alarm is still seen by the rules. The alarm's own time is in `AlarmDate`.
- Only alarms created after setup arrive. Older alarms are not sent.
- Incidents are not written back to SOCRadar. Closing an incident does not change the alarm.
- Use one route per workspace: this push template or the pull template, not both.

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
2. In the workspace: delete the 20 analytic rules `SOCRadar alarm (NRT): ...` and `SOCRadar alarm: ...`, the automation rule `SOCRadar - label incidents opened by the alarm rules` and the `SOCRadar Alarms` workbook.
3. In the resource group: delete the data collection rule `SOCRadar-Alarms-Push-DCR`, then the endpoint `SOCRadar-Push-DCE`, then the `SOCRadar_Alarms_CL` table.
4. Delete the app registration in Microsoft Entra ID.

If the template created the workspace, deleting the workspace also removes the rules, the table and the data in it. The data collection rule and endpoint stay in the resource group until you delete them.
