"""Prove documented rule timings and closed-incident behavior match the template."""
import json
import os
from pathlib import Path
import subprocess
import sys
from assertion_result import caught
from mutation_isolation import disposable_repo, write_mutant

source_root=Path(__file__).resolve().parents[1]
mutations=[('Scheduled','queryPeriod','P2D'),('Scheduled','queryFrequency','PT5M'),
           ('Scheduled','reopenClosedIncident',True),('Scheduled','lookbackDuration','P1D'),
           ('NRT','reopenClosedIncident',True),('NRT','lookbackDuration','P1D')]
with disposable_repo(source_root) as root:
    path=root/'azuredeploy.json'
    original=path.read_text()
    test=root/'tests/test_delivery_docs.py'
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    baseline=subprocess.run([sys.executable,str(test)],capture_output=True,text=True,env=env,timeout=60)
    if baseline.returncode: raise SystemExit('BASELINE_FAILED: tests/test_delivery_docs.py')
    blind=[]
    try:
        for kind,field,value in mutations:
            template=json.loads(original)
            rules=[r for r in template['resources'] if r.get('kind')==kind]
            if len(rules)!=1: raise RuntimeError('Mutation target is not unique')
            target=rules[0]['properties']
            if field not in ('queryPeriod','queryFrequency'):
                target=target['incidentConfiguration']['groupingConfiguration']
            if field not in target or target[field]==value: raise RuntimeError('No mutation: '+field)
            target[field]=value
            write_mutant(path, json.dumps(template,ensure_ascii=False,indent=2)+'\n')
            result=subprocess.run([sys.executable,str(test)],capture_output=True,text=True,env=env,timeout=60)
            matched=caught(result,'LIMIT:'+field)
            name=kind+' '+field
            print(('caught ' if matched else 'BLIND/ERROR ')+name)
            if not matched: blind.append(name)
    finally:
        path.write_text(original)
    print('blind:',len(blind),'of',len(mutations))
    sys.exit(bool(blind))
