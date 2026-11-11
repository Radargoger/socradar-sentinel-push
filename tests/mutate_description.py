"""Remove a plain-text lexer or its safety envelope; each must turn the test red."""
import json
import os
from pathlib import Path
import subprocess
import sys
from assertion_result import caught
from mutation_isolation import disposable_repo, write_mutant

source_root=Path(__file__).resolve().parents[1]

def drop_value_layer(query, depth):
    lines=[line for line in query.splitlines() if 'DecodedString =' in line]
    if len(lines)!=1: raise RuntimeError('DecodedString mutation target is not unique')
    line=lines[0];prefix,expression=line.split('DecodedString = ',1)
    parents=[]
    for level in range(depth+1):
        if not expression.startswith('replace_string(') or not expression.endswith(')'):
            raise RuntimeError('Expected a replace_string layer')
        body,old,new=expression[len('replace_string('):-1].rsplit(',',2)
        if level<depth: parents.append((old,new))
        expression=body
    for old,new in reversed(parents):
        expression='replace_string('+expression+','+old+','+new+')'
    return query.replace(line,prefix+'DecodedString = '+expression,1)

def override_value(query):
    lines=[line for line in query.splitlines() if 'DecodedString =' in line]
    if len(lines)!=1: raise RuntimeError('DecodedString mutation target is not unique')
    return query.replace(lines[0],lines[0]+'\n        | extend DecodedString = "overridden"',1)

mutations=[('lexer removed',lambda q:q.replace('extract_all(@"\\x22', 'extract_all(@"BROKEN')),
           ('mv-apply grammar removed',lambda q:q.replace('mv-apply with_itemindex=TokenIndex Token = ContentTokens to typeof(dynamic) on (', 'mv-apply Token = ContentTokens on (')),
           ('json decode removed',lambda q:q.replace('parse_json(strcat("\\\"", StringInner, "\\\""))', 'tostring(StringInner)')),
           ('key newline guard removed',lambda q:q.replace(', "\\n", " ")', ', "\\n", "")')),
           ('native type encoding removed',lambda q:q.replace('dynamic_to_json(pack_array(AlarmContent[ContentKey]))', 'tostring(AlarmContent[ContentKey])')),
           ('prelexer truncation 5000 inserted',lambda q:q.replace('RootKind = gettype(AlarmContent[ContentKey])', 'ContentJson = substring(ContentJson, 0, 5000)\n    | extend RootKind = gettype(AlarmContent[ContentKey])')),
           ('prelexer truncation alternate inserted',lambda q:q.replace('RootKind = gettype(AlarmContent[ContentKey])', 'ContentJson = substring(ContentJson, 0, 1234)\n    | extend RootKind = gettype(AlarmContent[ContentKey])')),
           ('packed value truncated',lambda q:q.replace('ContentJson = substring(ContentPacked, 1, strlen(ContentPacked) - 2)', 'ContentPacked = substring(ContentPacked, 0, 5000)\n    | extend ContentJson = substring(ContentPacked, 1, strlen(ContentPacked) - 2)')),
           ('lexer input truncated',lambda q:q.replace(', ContentJson)', ', substring(ContentJson, 0, 5000))')),
           ('exponent scalar removed',lambda q:q.replace('(?:[eE][+-]?\\d+)?', '')),
           ('empty string token lost',lambda q:q.replace('Punctuation in ("}", "]"), iff(Depth == 0, "", ")"),\n            "-")', 'Punctuation in ("}", "]"), iff(Depth == 0, "", ")"),\n            ""')),
           ('root comma separator broken',lambda q:q.replace('iff(RootKind == "array", ", ", "; ")', '", "')),
           ('nested group broken',lambda q:q.replace('iff(Depth == 1, "", "(")', '""')),
           ('fallback 1000 removed',lambda q:q.replace('substring(DescriptionBody, 0, 1000)', 'substring(DescriptionBody, 0, 4800)')),
           ('serialize removed',lambda q:q.replace('| serialize', '')),
           ('closing delta removed',lambda q:q.replace('Punctuation in ("}", "]"), -1', 'Punctuation in ("}", "]"), 0')),
           ('byte count replaced',lambda q:q.replace('strlen(base64_encode_tostring(DescriptionBody)) * 3 / 4', 'strlen(DescriptionBody)')),
           ('value newline guard removed',lambda q:q.replace('"\\n", "; "', '"\\n", ""')),
           ('byte reserve removed',lambda q:q.replace('BodyBudget / BodyBytes) - 10', 'BodyBudget / BodyBytes) + 500')),
           ('cell cap removed',lambda q:q.replace('strlen(ContentValue) > 300', 'strlen(ContentValue) > 99999')),
           ('content cap removed',lambda q:q.replace(')), 0, 2600)', ')), 0, 99999)')),
           ('details cap removed',lambda q:q.replace('"), 0, 1500)', '"), 0, 99999)')),
           ('no details fallback removed',lambda q:q.replace('coalesce(DetailsText, "No details")', 'DetailsText')),
           ('detail carriage return guard removed',lambda q:q.replace('replace_string(AlarmText, "\\r", "")', 'AlarmText')),
           ('long link cap removed',lambda q:q.replace('FullDescriptionLinkBytes > 768', 'FullDescriptionLinkBytes > 999999')),
           ('body budget clamp removed',lambda q:q.replace('max_of(0, 4800 - DescriptionLinkBytes)', '4800 - DescriptionLinkBytes')),
           ('byte guard removed',lambda q:q.replace('> 4900','> 99999')),
           ('value quote layer removed',lambda q:drop_value_layer(q,0)),
           ('value carriage return layer removed',lambda q:drop_value_layer(q,2)),
           ('decoded value overridden',override_value)]
expected = ['lexer', 'grammar', 'decode', 'key-newline', 'native-type',
            'json-lossless', 'json-lossless', 'packed-lossless', 'lexer-input',
            'exponent', 'empty', 'separator', 'nested', 'fallback', 'serialize',
            'delta', 'bytes', 'value-newline', 'reserve', 'cell-cap', 'content-cap',
            'details-cap', 'no-details', 'detail-cr', 'link-cap', 'body-clamp', 'byte-guard',
            'value-layers', 'value-layers', 'value-layers']
if len(expected) != len(mutations):
    raise RuntimeError('Missing expected description assertion')
with disposable_repo(source_root) as root:
    path=root/'azuredeploy.json'
    original=path.read_text()
    blind=[]
    baseline=subprocess.run([sys.executable,str(root/'tests/test_alert_description.py')],
        capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=60)
    if baseline.returncode:
        raise SystemExit('BASELINE_FAILED: tests/test_alert_description.py')
    try:
        for (name, mutate), marker in zip(mutations, expected):
            template=json.loads(original)
            resource=next(r for r in template['resources'] if r.get('kind')=='NRT')
            before=resource['properties']['query']
            resource['properties']['query']=mutate(before)
            if resource['properties']['query']==before:
                raise RuntimeError('No mutation: '+name)
            write_mutant(path, json.dumps(template,ensure_ascii=False,indent=2)+'\n')
            result=subprocess.run([sys.executable,str(root/'tests/test_alert_description.py')],capture_output=True,text=True,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=60)
            matched = caught(result, 'DESCRIPTION:'+marker)
            print(('caught ' if matched else 'BLIND/ERROR ')+name)
            if not matched: blind.append(name)
    finally:
        path.write_text(original)
    print('blind:',len(blind),'of',len(mutations))
    sys.exit(bool(blind))
