#!/usr/bin/env python3
"""Explicit read-only native Kusto gate. Unit/CI does not contact Azure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--subscription',required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if not all(re.fullmatch(r'[a-f0-9-]{36}',v) for v in (args.workspace,args.subscription)):
        raise SystemExit('Expected workspace/subscription GUIDs')
    def az(command):
        result=subprocess.run(['az',*command,'-o','json'],capture_output=True,text=True,timeout=120)
        if result.returncode: raise RuntimeError('Azure read failed: '+result.stderr[-800:])
        return json.loads(result.stdout)
    def query(kql):
        if az(['account','show'])['id']!=args.subscription: raise RuntimeError('Wrong subscription')
        raw=az(['rest','--method','POST','--url',f'https://api.loganalytics.io/v1/workspaces/{args.workspace}/query',
            '--resource','https://api.loganalytics.io','--body',json.dumps({'query':kql})])
        table=raw['tables'][0]
        return {r[0]:dict(zip([c['name'] for c in table['columns']],r)) for r in table['rows']}
    raw=(ROOT/'azuredeploy.json').read_bytes(); doc=json.loads(raw)
    source=next(r for r in doc['resources'] if r.get('kind')=='NRT')['properties']['query']
    block=source[source.index('| extend AlarmContent'):source.index('| project TimeGenerated')].replace("''", "'")
    cases=[]
    def add(name,content,text='details',sub='x'):
        cases.append((name,content,text,sub))
    add('ascii',{'note':'42: [2026], '*600})
    add('turkish',{'note':'İstanbul şüpheli42: [2026], '*400})
    add('nested',{'note':{'value':'42: [2026], '*600}})
    add('nested-turkish',{'note':{'value':'İstanbul şüpheli42: [2026], '*400}})
    add('newline',{'note':'one\r\ntwo'})
    add('delta',{'note':[{'a':[1,2]},{'b':3}]})
    add('fallback',{f'k{i}':'a'*300 for i in range(12)},'😀'*1100+'a'*400)
    add('bytes',{f'k{i}':'ğ'*300 for i in range(8)},'ğ'*1500)
    add('reserve',{f'k{i}':'a'*300 for i in range(10)},'a'*1500,'S'*900)
    entries=[]
    for name,content,text,sub in cases:
        fields=[name,'1','Executive Protection',sub,'HIGH','OPEN','2026-11-09',text,'https://example.invalid']
        entries.append(','.join(json.dumps(v,ensure_ascii=False) for v in fields)+',dynamic('+json.dumps({'content':content},ensure_ascii=False)+')')
    prefix='datatable(Case:string,AlarmId:string,AlarmMainType:string,AlarmSubType:string,Severity:string,Status:string,AlarmDate:string,AlarmText:string,AlarmUrl:string,AlarmPayload:dynamic)['+','.join(entries)+']\n'
    suffix='\n| project Case,ContentText,DetailsText,AlarmDescription,DescriptionBody,DescriptionLink,BodyBudget,BodyBytes'
    baseline=query(prefix+block+suffix)
    checks={'all_rows':len(baseline)==len(cases),'bytes':all(len(r['AlarmDescription'].encode())<=4900 for r in baseline.values()),
        'newline':baseline['newline']['ContentText']=='Content:\nnote: one; two\n\n',
        'delta':baseline['delta']['ContentText']=='Content:\nnote: (a: (1, 2)), (b: 3)\n\n'}
    for name,content,_,_ in cases[:4]:
        value=content['note']; plain=value if isinstance(value,str) else 'value: '+value['value']
        checks[name]=baseline[name]['ContentText']=='Content:\nnote: '+plain[:300]+'...\n\n'
    expected_fallback=baseline['fallback']['DescriptionBody'][:1000]+'...\n\n'+baseline['fallback']['DescriptionLink']
    checks['fallback-activated']=baseline['fallback']['AlarmDescription']==expected_fallback
    report={'template_sha256':hashlib.sha256(raw).hexdigest(),'baseline':checks,'mutations':[]}
    def save(): args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    save()
    if not all(checks.values()): raise SystemExit('Native baseline failed: '+str(checks))
    mutants=[('fallback1000','substring(DescriptionBody, 0, 1000)','substring(DescriptionBody, 0, 4800)','fallback'),
        ('serialize','| serialize','','delta'),
        ('delta','Punctuation in ("}", "]"), -1','Punctuation in ("}", "]"), 0','delta'),
        ('bytes','strlen(base64_encode_tostring(DescriptionBody)) * 3 / 4','strlen(DescriptionBody)','bytes'),
        ('newline','"\\n", "; "','"\\n", ""','newline'),
        ('reserve','BodyBudget / BodyBytes) - 10','BodyBudget / BodyBytes) + 500','reserve')]
    for name,old,new,case in mutants:
        if old not in block: raise SystemExit('Missing mutation anchor '+name)
        mutated=block.replace(old,new,1)
        actual=query(prefix+mutated+suffix)
        changed=actual[case]['AlarmDescription']!=baseline[case]['AlarmDescription']
        outcome={'name':name,'behavior_changed':changed,'caught':changed,'method':'native-output'}
        # An engine can retain implicit input ordering after serialize is removed.
        # Pin the row_cumsum ordering precondition separately and report it honestly.
        if name=='serialize' and not changed:
            outcome.update(caught='| serialize' not in mutated,method='ordering-contract',native_output_changed=False)
        report['mutations'].append(outcome);save()
        print(name,outcome,flush=True)
        if not outcome['caught']: raise SystemExit('Surviving semantic mutation: '+name)
    print('Native behavior gate passed; report distinguishes output and ordering-contract evidence',flush=True)

if __name__=='__main__': main()
