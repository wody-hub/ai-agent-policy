"""Host paseo: create_agent start configuration, orchestrator restriction, profile map, review mode."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ai_policy import routing
from ai_policy.bundle import PolicyError

C=routing.load_config()

def r(**k): return routing.route(C, host='paseo', **k)
def pick(x): return (x['alias'], x['effort'])

class PaseoRoutingTests(unittest.TestCase):
    def test_config_version_and_changelog(self):
        self.assertEqual(C['version'], '1.6.0')
        self.assertEqual(C['changelog'][0]['version'], '1.6.0')
        self.assertIn('paseo', C['hosts'])
        self.assertEqual(C['hosts']['paseo']['orchestrator_tools'], ['claude'])

    def test_start_configuration_fields(self):
        x=r(task_type='feature')
        self.assertEqual(pick(x), ('luna','high'))
        self.assertEqual(x['paseo_create_agent'], {'provider':'codex/gpt-6-luna','settings':{'modeId':'auto','thinkingOptionId':'high'}})
        self.assertEqual(x['paseo_profile'], 'dev-l2-general')
        self.assertEqual(x['orca_worker_args'], [])   # Orca-only argument form is not emitted for Paseo
        self.assertEqual(x['action'], 'run')

    def test_orchestrator_roles_are_sonnet_high_with_no_fallback(self):
        for role, profile in (('root_orchestrator','root-orchestrator'), ('project_coordinator','project-coordinator')):
            x=r(role=role)
            self.assertEqual(pick(x), ('sonnet','high')); self.assertEqual(x['paseo_profile'], profile)
            self.assertEqual(x['paseo_create_agent']['provider'], 'claude/claude-sonnet-5-5')
            # No Codex candidate (no Paseo tools) and no other fallback.
            for avail in (['luna'], ['terra'], ['luna','terra']):
                y=r(role=role, available=avail)
                self.assertEqual(y['action'], 'blocked_no_available_model'); self.assertIsNone(y['paseo_create_agent'])
        self.assertEqual(r(role='lookup')['paseo_create_agent']['provider'], 'codex/gpt-6-luna')

    def test_orca_roles_unchanged_by_paseo_roles(self):
        x=routing.route(C, host='orca', role='project_coordinator')
        self.assertEqual(pick(x), ('luna','high'))
        self.assertEqual(pick(routing.route(C, host='orca', role='project_coordinator', available=['terra'])), ('terra','high'))
        self.assertEqual(routing.route(C, host='orca', role='project_coordinator', available=['sonnet'])['action'], 'blocked_no_available_model')
        self.assertNotIn('paseo_create_agent', x)

    def test_escalated_coordinator_is_a_worker_not_an_orchestrator(self):
        x=r(role='project_coordinator', failures=2)
        self.assertEqual((x['action'], x['level'], pick(x), x['paseo_profile']), ('escalate', 3, ('sonnet','high'), 'dev-l3-complex'))

    def test_levels_and_profile_map(self):
        expect={1:('luna','medium','dev-l1-simple'),2:('luna','high','dev-l2-general'),3:('sonnet','high','dev-l3-complex')}
        for lv,(a,e,prof) in expect.items():
            x=r(level=lv); self.assertEqual((pick(x), x['paseo_profile']), ((a,e), prof))
        x=r(task_type='security'); self.assertEqual((pick(x), x['paseo_profile'], x['human_gate']), (('opus','high'), 'l4-critical', True))
        x=r(level=4, failures=2, failure_kind='reasoning')
        self.assertEqual((x['action'], pick(x), x['paseo_profile']), ('escalate', ('fable','high'), 'l5-last-resort'))
        # A routed value that differs from the profile assumption configures directly.
        x=r(task_type='architecture'); self.assertEqual(pick(x), ('terra','high')); self.assertIsNone(x['paseo_profile'])
        self.assertIn('paseo_profile:none_configure_directly', x['reasons'])
        self.assertIsNone(r(task_type='log_summary')['paseo_profile'])

    def test_paseo_selection_matches_orca_selection_for_workers(self):
        for t in ('docs','feature','api','multi_module','architecture','code_review_codex','security','requirements'):
            with self.subTest(task=t):
                o=routing.route(C, host='orca', task_type=t); p=r(task_type=t)
                self.assertEqual((o['alias'],o['effort'],o['level'],o['action']), (p['alias'],p['effort'],p['level'],p['action']))

    def test_review_mode_claude_plan_and_codex_not_enforced(self):
        x=r(task_type='code_review_codex')
        self.assertEqual(x['paseo_create_agent']['settings']['modeId'], 'plan')
        self.assertEqual(x['paseo_profile'], 'review-codex-work'); self.assertEqual(x['paseo_review']['tool'], 'claude')
        x=r(task_type='code_review_claude')
        self.assertEqual(x['paseo_profile'], 'review-claude-work')
        review=x['paseo_review']
        self.assertIs(review['enforced'], False); self.assertEqual(review['evidence'], 'git_status_diff_unchanged')
        self.assertEqual(x['paseo_create_agent']['settings']['features'], {'plan_mode': True})
        self.assertEqual(x['paseo_create_agent']['settings']['modeId'], 'auto')
        self.assertFalse(review['write_block_required'])
        self.assertIsNone(r(task_type='feature')['paseo_review'])

    def test_write_block_review_prefers_claude_and_flags_codex_fallback(self):
        x=r(task_type='security_review')
        self.assertEqual((pick(x), x['paseo_create_agent']['settings']['modeId'], x['paseo_review']['write_block_required']), (('sonnet','high'), 'plan', True))
        y=r(task_type='security_review', available=['luna'])
        self.assertEqual(y['paseo_review']['tool'], 'codex')
        self.assertIn('review_write_block_requires_claude_plan', y['reasons'])

    def test_handoff_and_non_model_failure_actions(self):
        x=r(level=4, failures=2, failure_kind='reasoning', resolved=False)
        self.assertEqual(x['action'], 'escalate')
        x=r(task_type='bugfix', failure_kind='tool', failures=3)
        self.assertEqual(x['action'], 'handoff_to_lead'); self.assertIsNone(x['paseo_create_agent'])
        x=r(task_type='bugfix', failure_kind='tool', failures=1)
        self.assertEqual(x['action'], 'retry_same_model_preserve_state'); self.assertTrue(x['preserve_state'])
        self.assertIsNotNone(x['paseo_create_agent'])

    def test_cli_exit_codes_and_resolve_family(self):
        def run(*a):
            b=io.StringIO()
            with contextlib.redirect_stdout(b): code=routing.main(list(a))
            return code, json.loads(b.getvalue())
        code, x=run('--host','paseo','--task-type','docs','--model-catalog','/nonexistent')
        self.assertEqual((code, x['paseo_create_agent']['provider']), (0, 'codex/gpt-6-luna'))
        code, x=run('--host','paseo','--role','root_orchestrator','--available','luna','--model-catalog','/nonexistent')
        self.assertEqual((code, x['action']), (40, 'blocked_no_available_model'))
        code, x=run('--host','paseo','--task-type','bugfix','--failure-kind','tool','--failures','3','--model-catalog','/nonexistent')
        self.assertEqual((code, x['action']), (41, 'handoff_to_lead'))
        code, x=run('--host','paseo','--resolve-family','terra','--effort','high','--model-catalog','/nonexistent')
        self.assertEqual(code, 0)
        self.assertEqual(x['paseo_create_agent'], {'provider':'codex/gpt-6.1-terra','settings':{'modeId':'auto','thinkingOptionId':'high'}})
        self.assertEqual(x['orca_worker_args'], [])
        code, x=run('--host','orca','--resolve-family','terra','--effort','high','--model-catalog','/nonexistent')
        self.assertEqual(x['orca_worker_args'], ['--agent','codex','--model','gpt-6.1-terra','--effort','high'])
        self.assertNotIn('paseo_create_agent', x)

    def test_config_validation_for_paseo_blocks(self):
        base=json.loads(routing.DEFAULT_CONFIG.read_text())
        def bad(mut):
            c=json.loads(json.dumps(base)); mut(c)
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'c.json'; p.write_text(json.dumps(c))
                with self.assertRaises(PolicyError) as cm: routing.load_config(p)
                self.assertEqual(str(cm.exception), 'routing_config_invalid')
        bad(lambda c: c['levels']['1'].pop('paseo'))
        bad(lambda c: c['levels']['2'].update(paseo_alternatives=[['ghost','high']]))
        bad(lambda c: c['hosts']['paseo'].update(orchestrator_tools=['gemini']))
        bad(lambda c: c['paseo_profiles'].update(x={'level': 9}))
        bad(lambda c: c['paseo_profiles'].update(x={'task_types': ['nope'], 'expect': ['sonnet','high']}))
        bad(lambda c: c['review_mode'].update(task_types=['nope']))
        bad(lambda c: c['review_mode'].update(codex={'features': {}}))

if __name__=='__main__': unittest.main()
