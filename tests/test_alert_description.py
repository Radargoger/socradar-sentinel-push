"""Pin Defender plain-text formatting and the existing alert safety envelope."""
import json
from pathlib import Path
import re
import unittest

TEMPLATE = Path(__file__).resolve().parents[1] / 'azuredeploy.json'
DECODED_STRING = r'replace_string(replace_string(replace_string(tostring(parse_json(strcat("\"", StringInner, "\""))), "\r", ""), "\n", "; "), "\"", "”")'

class AlertDescriptionTests(unittest.TestCase):
    def test_both_rule_kinds_use_plain_text(self):
        template = json.loads(TEMPLATE.read_text())
        rules = [r for r in template['resources'] if r.get('kind') in ('Scheduled', 'NRT')]
        self.assertEqual({r['kind'] for r in rules}, {'Scheduled','NRT'})
        formatting = []
        for rule in rules:
            with self.subTest(kind=rule['kind']):
                p=rule['properties']
                q=p['query']
                self.assertNotIn('| Field | Value |',q)
                self.assertNotIn('Markdown',q)
                self.assertIn('extract_all(@"\\x22((?:\\\\.|[^\\x22\\\\])*)\\x22|([{}\\[\\],:])|',q, 'DESCRIPTION:lexer')
                self.assertIn('mv-apply with_itemindex=TokenIndex Token = ContentTokens to typeof(dynamic) on (',q, 'DESCRIPTION:grammar')
                self.assertIn('parse_json(strcat("\\\"", StringInner, "\\\""))',q, 'DESCRIPTION:decode')
                self.assertIn('PlainKey = replace_string(replace_string(replace_string(replace_string(ContentKey, "\\r", ""), "\\n", " "), "\\"", "”"), "_", " ")',q, 'DESCRIPTION:key-newline')
                self.assertIn('dynamic_to_json(pack_array(AlarmContent[ContentKey]))',q, 'DESCRIPTION:native-type')
                self.assertIn('substring(ContentPacked, 1, strlen(ContentPacked) - 2)',q)
                self.assertNotIn('substring(ContentJson, 0, 6000)',q)
                # ContentPacked is losslessly unwrapped before lexical tokenization.
                # Any pre-lexer ContentJson truncation corrupts quoted long values.
                self.assertRegex(q, r'ContentJson = substring\(ContentPacked, 1, strlen\(ContentPacked\) - 2\)')
                self.assertTrue(re.findall(r'\bContentPacked\s*=\s*([^\n]+)', q) == ['dynamic_to_json(pack_array(AlarmContent[ContentKey]))'], 'DESCRIPTION:packed-lossless')
                self.assertTrue(re.findall(r'\bContentJson\s*=\s*([^\n]+)', q) == ['substring(ContentPacked, 1, strlen(ContentPacked) - 2)'], 'DESCRIPTION:json-lossless')
                token_sources = re.findall(r'\bContentTokens\s*=\s*([^\n]+)', q)
                self.assertEqual(len(token_sources), 1)
                self.assertTrue(token_sources[0].endswith(', ContentJson)'), 'DESCRIPTION:lexer-input')
                self.assertIn('RootKind = gettype(AlarmContent[ContentKey])',q)
                self.assertIn('(?:[eE][+-]?\\d+)?',q, 'DESCRIPTION:exponent')
                self.assertIn('isnotempty(StringInner), DecodedString',q)
                self.assertIn('Punctuation in ("}", "]"), iff(Depth == 0, "", ")"),\n            "-")',q, 'DESCRIPTION:empty')
                self.assertIn('"\\n", "; "',q, 'DESCRIPTION:value-newline')
                self.assertTrue(re.findall(r'\bDecodedString\s*=\s*([^\n]+)', q) == [DECODED_STRING],
                                'DESCRIPTION:value-layers')
                self.assertIn('Punctuation == ",", iff(RootKind == "array", ", ", "; ")',q, 'DESCRIPTION:separator')
                self.assertIn('Punctuation in ("{", "["), iff(Depth == 1, "", "(")',q, 'DESCRIPTION:nested')
                self.assertIn('Punctuation in ("}", "]"), iff(Depth == 0, "", ")")',q)
                self.assertIn('strcat(PlainKey, ": ",',q)
                self.assertIn('strcat_array(ContentRows, "\\n")',q)
                self.assertIn('strlen(ContentValue) > 300',q, 'DESCRIPTION:cell-cap')
                self.assertIn('substring(ContentValue, 0, 300)',q)
                self.assertIn('substring(strcat("Content:\\n", strcat_array(ContentRows, "\\n")), 0, 2600)',q, 'DESCRIPTION:content-cap')
                self.assertIn('replace_string(AlarmText, "\\r", "")',q, 'DESCRIPTION:detail-cr')
                self.assertIn('substring(replace_string(AlarmText, "\\r", ""), 0, 1500)',q, 'DESCRIPTION:details-cap')
                self.assertIn('coalesce(DetailsText, "No details")',q, 'DESCRIPTION:no-details')
                self.assertNotIn('| Field | Value |',q)
                self.assertIn('FullDescriptionLinkBytes > 768',q, 'DESCRIPTION:link-cap')
                self.assertIn('View in SOCRadar: link omitted (URL too long)',q)
                self.assertIn('BodyBudget = max_of(0, 4800 - DescriptionLinkBytes)',q, 'DESCRIPTION:body-clamp')
                self.assertIn('strlen(base64_encode_tostring(DescriptionBody)) * 3 / 4',q, 'DESCRIPTION:bytes')
                self.assertIn('> 4900',q, 'DESCRIPTION:byte-guard')
                self.assertIn('| serialize',q, 'DESCRIPTION:serialize')
                self.assertIn('Punctuation in ("}", "]"), -1',q, 'DESCRIPTION:delta')
                self.assertIn('substring(DescriptionBody, 0, 1000)',q, 'DESCRIPTION:fallback')
                self.assertIn('BodyBudget / BodyBytes) - 10',q, 'DESCRIPTION:reserve')
                self.assertIn('FullDescriptionLink = strcat("View in SOCRadar: ", AlarmUrl)',q)
                self.assertEqual(p['alertDetailsOverride']['alertDescriptionFormat'],'{{AlarmDescription}}')
                self.assertIn('toupper(Status) == "OPEN"',q)
                self.assertIn('"connection.test"',q)
                formatting.append(q[q.index('| extend AlarmContent'):q.index('| project TimeGenerated')])
        if len(formatting) == len(rules):
            self.assertEqual(formatting[0],formatting[1])

    def test_content_golden_cases_are_live_engine_fixtures_not_a_python_formatter(self):
        fixtures = Path(__file__).resolve().parent / 'fixtures' / 'alert_description_content.json'
        cases = json.loads(fixtures.read_text())
        self.assertEqual(
            {case['name'] for case in cases},
            {'array', 'object', 'nested', 'empty', 'scalars', 'quotes_and_punctuation', 'escaped_backslash_and_quote',
             'literal_json_looking_string', 'newline', 'exponent_array', 'null_and_empty_string', 'newline_key'},
        )
        by_name = {case['name']: case for case in cases}
        self.assertEqual(by_name['array']['expected'], 'tags: sentetik, örnek')
        self.assertEqual(by_name['object']['expected'], 'evidence: source: test; value: bir | iki')
        self.assertEqual(by_name['empty']['expected'], 'empty array: -; empty object: -')
        self.assertEqual(by_name['scalars']['expected'], 'count: 42; enabled: true')
        self.assertEqual(by_name['quotes_and_punctuation']['expected'], 'note: tırnak ”iç” ve virgül, brace { korunur')
        self.assertEqual(by_name['escaped_backslash_and_quote']['expected'], 'note: tırnak \\”iç\\” korunur')
        self.assertEqual(by_name['literal_json_looking_string']['expected'], 'note: [literal]')
        self.assertEqual(by_name['newline']['expected'], 'note: ilk; ikinci')
        self.assertEqual(by_name['exponent_array']['expected'], 'values: 1e100, -0.0025')
        self.assertEqual(by_name['null_and_empty_string']['expected'], 'none: -; blank: -')
        self.assertEqual(by_name['newline_key']['expected'], 'line key: value')

if __name__=='__main__':
    unittest.main()
