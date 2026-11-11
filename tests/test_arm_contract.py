#!/usr/bin/env python3
"""Resolved rule metadata and ingestion URL remain compatible across API updates."""
import json
from pathlib import Path
from urllib.parse import urljoin

template = json.loads((Path(__file__).parents[1]/'azuredeploy.json').read_text())
variables = template['variables']
rules = [r for r in template['resources'] if r.get('kind') in ('Scheduled', 'NRT')]
assert len(rules) == 2
# Resource-kind sections, not cross-version examples in the Learn pages:
# https://learn.microsoft.com/azure/templates/microsoft.securityinsights/2025-09-01/alertrules
# https://learn.microsoft.com/azure/templates/microsoft.securityinsights/2025-07-01-preview/alertrules
documented_kinds = {
    '2025-09-01': {'Fusion', 'MicrosoftSecurityIncidentCreation', 'Scheduled'},
    '2025-07-01-preview': {'Fusion', 'MLBehaviorAnalytics', 'MicrosoftSecurityIncidentCreation',
                           'NRT', 'Scheduled', 'ThreatIntelligence'},
}
for rule in rules:
    assert rule['kind'] in documented_kinds.get(rule['apiVersion'], set()), 'ARM_KIND_API: unsupported-kind-api'
expected = {'AlarmId': 'AlarmId', 'AlarmMainType': 'AlarmMainType',
            'AlarmSubType': 'AlarmSubType', 'SocradarSeverity': 'Severity', 'AlarmStatus': 'Status'}
assert variables['alarmCustomDetails'] == expected
for rule in rules:
    props = rule['properties']
    assert props['customDetails'] == "[variables('alarmCustomDetails')]"
    grouping = props['incidentConfiguration']['groupingConfiguration']
    assert grouping['groupByEntities'] == ['URL']
    assert grouping['groupByAlertDetails'] == "[json('[]')]"
    assert grouping['groupByCustomDetails'] == "[json('[]')]"
    assert grouping['matchingMethod'] == 'Selected'
    assert grouping['reopenClosedIncident'] is False
assert variables['tacticsMap']['Other'] == {'tactics': "[json('[]')]", 'techniques': "[json('[]')]"}
url_expression = template['outputs']['LogIngestionUrl']['value']
assert url_expression.startswith('[uri(reference(')
path_format = '/dataCollectionRules/{0}/streams/Custom-SOCRadarAlarmsPush?api-version=2023-01-01'
assert "format('" + path_format + "', reference(" in url_expression
for endpoint in ('https://example.ingest.monitor.azure.com', 'https://example.ingest.monitor.azure.com/'):
    path = path_format.format('dcr-example')
    assert urljoin(endpoint, path) == endpoint.rstrip('/') + path
print('ARM rule metadata and ingestion URL contract: pass')
