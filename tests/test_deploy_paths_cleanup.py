"""Offline process tests of the live harness. No real Azure executable is called."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/test_deploy_paths.sh'
SUB = '00000000-0000-0000-0000-000000000001'
FAKE = r'''
import json, os, pathlib, sys
a = sys.argv[1:]
root = pathlib.Path(os.environ['FAKE_ROOT'])
statefile = root / 'state.json'
state = json.loads(statefile.read_text()) if statefile.exists() else {'groups': {}, 'calls': []}
state['calls'].append(a)
scenario = os.environ['SCENARIO']
def arg(key, default=''):
    return a[a.index(key)+1] if key in a else default
def done(value='', rc=0):
    statefile.write_text(json.dumps(state))
    if value != '': print(value)
    sys.exit(rc)
assert arg('--subscription') == os.environ['TEST_SUBSCRIPTION_ID'], 'unscoped Azure call'
name = arg('-n')
rg = arg('-g', name)
query = arg('--query')
if a[:2] == ['account', 'show']: done(os.environ['TEST_SUBSCRIPTION_ID'])
if a[:2] == ['group', 'exists']:
    if scenario == 'unreadable' and not state['groups']: done('cannot read', 2)
    if scenario == 'preexisting' and not state['groups']: done('true')
    done('true' if name in state['groups'] else 'false')
if a[:2] == ['group', 'create']:
    state['groups'][name] = arg('--tags').split('=', 1)[1]
    if scenario == 'partial-create' and len(state['groups']) == 2: done('partial create failure', 9)
    done()
if a[:2] == ['group', 'show']:
    if scenario == 'ownership-unreadable': done('cannot read ownership', 3)
    tag = state['groups'].get(name, '')
    if scenario == 'foreign-owner': tag = 'some-other-run'
    resource_name = 'unexpected-resource-group' if scenario == 'wrong-id' else name
    done('/subscriptions/' + os.environ['TEST_SUBSCRIPTION_ID'] + '/resourceGroups/' + resource_name + '\n' + tag)
if a[:2] == ['group', 'delete']:
    assert '--ids' not in a, 'az group delete does not support --ids'
    name = arg('-n')
    assert name in state['groups'], 'attempted delete outside owned set'
    if scenario == 'delete-failure': done('delete failed', 7)
    if scenario != 'timeout': del state['groups'][name]
    done()
if a[:3] == ['deployment', 'group', 'create']: done()
if a[:3] == ['deployment', 'group', 'show']:
    if 'workspaceId' in query: done('12345678-0000-0000-0000-000000000000')
    if scenario == 'original-failure' and name == 'path-b': done('Failed')
    done('Failed' if name in ('path-a', 'path-c-bare') else 'Succeeded')
if a[:4] == ['deployment', 'operation', 'group', 'list']:
    if 'length' in query: done('0')
    if query.endswith('.properties.provisioningState'): done('Succeeded')
    done('precheck-workspace-exists' if name in ('path-a', 'path-c-bare') else '')
if a[:2] == ['resource', 'list']:
    done('1' if '--resource-type' in a or 'paths-c-' in rg else '0')
if a[:5] == ['monitor', 'log-analytics', 'workspace', 'table', 'show']: done('SOCRadar_Push_Alarms_CL')
if a[:4] == ['monitor', 'log-analytics', 'workspace', 'show']:
    if query == 'id': done('/subscriptions/' + os.environ['TEST_SUBSCRIPTION_ID'] + '/resourceGroups/' + rg + '/providers/Microsoft.OperationalInsights/workspaces/test')
    done('{"name":"test","retentionInDays":60}')
if a[:3] == ['monitor', 'log-analytics', 'workspace'] and a[3] in ('create', 'update'): done()
if a[:1] == ['rest']: done()
done('unsupported fake call ' + repr(a), 90)
'''


class DeployCleanup(unittest.TestCase):
    def run_harness(self, scenario, keep=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / 'az'
            fake.write_text('#!' + sys.executable + '\n' + FAKE)
            fake.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n')
            sleep.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       FAKE_ROOT=str(root), SCENARIO=scenario, TEST_SUBSCRIPTION_ID=SUB,
                       KEEP_RESOURCES='true' if keep else 'false')
            shell = '/bin/bash' if sys.platform == 'darwin' else 'bash'
            run = subprocess.run([shell, str(SCRIPT)], env=env, text=True, capture_output=True, timeout=30)
            state = json.loads((root / 'state.json').read_text())
            return run, state

    def test_success_absence_and_pinned_calls(self):
        run, state = self.run_harness('success')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertFalse(state['groups'])
        self.assertEqual(run.stdout.count('cleanup OK:'), 2)
        for call in state['calls']:
            self.assertEqual(call[call.index('--subscription') + 1], SUB)
        creates = [c for c in state['calls'] if c[:2] == ['group', 'create']]
        self.assertEqual(len(creates), 2)
        self.assertEqual(len(creates[0][creates[0].index('--tags') + 1].split('=')[1]), 32)

    def test_preexisting_and_unreadable_never_mutate(self):
        for scenario in ('preexisting', 'unreadable'):
            with self.subTest(scenario=scenario):
                run, state = self.run_harness(scenario)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(any(c[:2] in (['group', 'create'], ['group', 'delete']) for c in state['calls']))

    def test_partial_create_is_cleaned_after_readback(self):
        run, state = self.run_harness('partial-create')
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(state['groups'])
        self.assertEqual(run.stdout.count('cleanup OK:'), 2)

    def test_unknown_or_foreign_ownership_never_deleted(self):
        for scenario in ('ownership-unreadable', 'foreign-owner'):
            with self.subTest(scenario=scenario):
                run, state = self.run_harness(scenario)
                self.assertNotEqual(run.returncode, 0)
                self.assertTrue(state['groups'])
                self.assertFalse(any(c[:2] == ['group', 'delete'] for c in state['calls']))

    def test_delete_failure_fails_process(self):
        run, state = self.run_harness('delete-failure')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(len(state['groups']), 2)
        self.assertIn('delete rejected', run.stdout)

    def test_wrong_resource_id_with_correct_tag_never_deleted(self):
        run, state = self.run_harness('wrong-id')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(len(state['groups']), 1)
        creates = [c for c in state['calls'] if c[:2] == ['group', 'create']]
        self.assertEqual(len(creates), 1)
        original_tag = creates[0][creates[0].index('--tags') + 1].split('=', 1)[1]
        self.assertEqual(list(state['groups'].values()), [original_tag])
        self.assertIn('ownership unproved', run.stdout)
        self.assertFalse(any(c[:2] == ['group', 'delete'] for c in state['calls']))

    def test_timeout_is_bounded_and_fails_process(self):
        run, state = self.run_harness('timeout')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout.count('absence not proved after 12 reads'), 2)
        self.assertEqual(sum(c[:2] == ['group', 'exists'] for c in state['calls']), 30)

    def test_original_assertion_failure_survives_successful_cleanup(self):
        run, state = self.run_harness('original-failure')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('assertion(s) failed', run.stdout)
        self.assertFalse(state['groups'])

    def test_keep_reports_exact_owned_resources(self):
        run, state = self.run_harness('success', keep=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(len(state['groups']), 2)
        self.assertEqual(run.stdout.count('cleanup KEEP: /subscriptions/' + SUB), 2)
        self.assertFalse(any(c[:2] == ['group', 'delete'] for c in state['calls']))


if __name__ == '__main__':
    unittest.main()
