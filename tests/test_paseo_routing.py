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
        self.assertEqual(C['version'], '1.7.0')
        self.assertEqual(C['changelog'][0]['version'], '1.7.0')
        self.assertEqual(C['changelog'][1]['version'], '1.6.0')
        self.assertEqual(C['verified_on'], '2026-11-25')
        self.assertIn('claude-fable-5-2', C['verification_scope']['verified'])
        self.assertIn('claude-haiku-5-5', C['verification_scope']['not_verified'])
        self.assertEqual(C['models']['fable']['access_verified_on'], '2026-11-06')
        self.assertIs(C['models']['fable']['alias_observed']['adopted'], False)
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

    def test_write_block_review_without_claude_is_blocked(self):
        y=r(task_type='security_review', available=['luna'])
        self.assertEqual(y['action'], 'blocked_no_available_model')
        self.assertIsNone(y['paseo_create_agent']); self.assertIsNone(y['paseo_profile'])
        self.assertIsNone(y['alias']); self.assertIsNone(y['model'])
        self.assertTrue(y['paseo_review']['write_block_required'])
        self.assertIn('review_write_block_requires_claude_plan', y['reasons'])
        b=io.StringIO()
        with contextlib.redirect_stdout(b):
            code=routing.main(['--host','paseo','--task-type','security_review','--available','luna','--model-catalog','/nonexistent'])
        self.assertEqual(code, 40); self.assertIsNone(json.loads(b.getvalue())['paseo_create_agent'])

    def test_write_block_review_with_claude_keeps_plan(self):
        x=r(task_type='security_review', available=['sonnet','opus','luna'])
        self.assertEqual(x['action'], 'run')
        self.assertEqual(x['paseo_create_agent']['settings']['modeId'], 'plan')
        self.assertNotIn('review_write_block_requires_claude_plan', x['reasons'])

    def test_non_write_block_review_codex_fallback_still_runs(self):
        x=r(task_type='code_review_claude', available=['luna'])
        self.assertEqual(x['action'], 'run')
        self.assertEqual(x['paseo_review']['tool'], 'codex'); self.assertFalse(x['paseo_review']['write_block_required'])
        self.assertIs(x['paseo_review']['enforced'], False)
        self.assertEqual(x['paseo_create_agent']['settings']['features'], {'plan_mode': True})
        self.assertNotIn('review_write_block_requires_claude_plan', x['reasons'])

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

LIVE_PROFILES=json.loads((Path(__file__).parent/'fixtures'/'paseo_live_profiles.json').read_text(encoding='utf-8'))
LUNA7=[{'slug':'gpt-7-luna','visibility':'list','supported_in_api':True}]

class PaseoProfileSpecTests(unittest.TestCase):
    def test_live_profiles_derive_exactly_to_live_values(self):
        # tests/fixtures/paseo_live_profiles.json is a checked-in copy of the live agentProfiles tuples (the real file is never read by tests).
        self.assertEqual([p['id'] for p in LIVE_PROFILES], [k for k in C['paseo_profiles'] if not C['paseo_profiles'][k].get('provisional')])
        for live in LIVE_PROFILES:
            with self.subTest(profile=live['id']):
                d=routing.paseo_profile_spec(C, live['id'])
                self.assertEqual({k: d[k] for k in ('provider','model','modeId','thinkingOptionId')}, {k: live[k] for k in ('provider','model','modeId','thinkingOptionId')})
                self.assertEqual(d['notes'], live['notes']); self.assertFalse(d['provisional'])

    def test_provisional_profiles_and_no_sol_default(self):
        d=routing.paseo_profile_spec(C, 'scout')
        self.assertEqual((d['provider'], d['model'], d['modeId'], d['thinkingOptionId'], d['provisional']), ('claude','claude-haiku-5-5','plan',None,True))
        d=routing.paseo_profile_spec(C, 'ui-verify'); self.assertEqual((d['model'], d['modeId'], d['thinkingOptionId']), ('gpt-6.1-terra','auto','high'))
        d=routing.paseo_profile_spec(C, 'l5-alt-astra'); self.assertEqual((d['provider'], d['model'], d['thinkingOptionId'], d['provisional']), ('codex','gpt-6.2-astra','high',True))
        self.assertEqual([k for k in C['paseo_profiles'] if '-sol' in routing.paseo_profile_spec(C, k)['model']], [])   # no Sol default profile
        for k in C['paseo_profiles']:
            m=routing.paseo_profile_spec(C, k)['model']
            self.assertTrue(m.startswith(('claude-','gpt-')), m)       # exact ids only, never an alias

    def test_orchestrator_with_only_codex_available_is_blocked(self):
        for role in ('root_orchestrator','project_coordinator'):
            for avail in (['luna'], ['terra'], ['luna','terra']):
                self.assertEqual(r(role=role, available=avail)['action'], 'blocked_no_available_model')

    def test_terra_lateral_names_no_profile(self):
        x=r(level=2, failures=1, failure_kind='verification')
        self.assertEqual((pick(x), x['lateral'], x['paseo_profile']), (('terra','high'), True, None))
        self.assertIn('paseo_profile:none_configure_directly', x['reasons'])

    def test_astra_at_l5_names_no_profile_while_provisional(self):
        x=r(level=4, failures=2, failure_kind='verification', failed_family='claude')
        self.assertEqual((pick(x), x['paseo_profile']), (('astra','high'), None))
        self.assertTrue(C['paseo_profiles']['l5-alt-astra']['provisional'])
        x=r(level=4, failures=2, failure_kind='verification'); self.assertEqual((pick(x), x['paseo_profile']), (('fable','high'), 'l5-last-resort'))

    def test_newer_catalog_id_names_no_profile_pinned_to_older_id(self):
        x=r(level=2, model_catalog=LUNA7)
        self.assertEqual((x['model'], x['paseo_profile']), ('gpt-7-luna', None))
        self.assertEqual(x['paseo_create_agent']['provider'], 'codex/gpt-7-luna')
        self.assertEqual(r(level=2, model_catalog=[{'slug':'gpt-6-luna','visibility':'list','supported_in_api':True}])['paseo_profile'], 'dev-l2-general')

    def test_profile_is_not_named_when_the_mode_differs(self):
        # since C5 important_review runs in plan mode; dev-l3-complex is an auto-mode profile, so it must not be named
        x=r(task_type='important_review')
        self.assertEqual((pick(x), x['paseo_create_agent']['settings']['modeId'], x['paseo_profile']), (('sonnet','high'), 'plan', None))
        self.assertEqual(r(task_type='multi_module')['paseo_profile'], 'dev-l3-complex')
        x=r(task_type='review'); self.assertEqual((pick(x), x['paseo_profile']), (('sonnet','medium'), None))   # plan mode, no level profile matches
        self.assertEqual(r(task_type='code_review_codex')['paseo_profile'], 'review-codex-work')

    def test_profile_validation(self):
        base=json.loads(routing.DEFAULT_CONFIG.read_text())
        def bad(mut, raw=None):
            c=json.loads(json.dumps(base)); mut(c)
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'c.json'; p.write_text(raw(json.dumps(c)) if raw else json.dumps(c))
                with self.assertRaises(PolicyError) as cm: routing.load_config(p)
                self.assertEqual(str(cm.exception), 'routing_config_invalid')
        P=lambda c: c['paseo_profiles']
        bad(lambda c: P(c)['lookup'].update(level=1))                                  # two selectors
        bad(lambda c: P(c)['dev-l1-simple'].update(task_types=['docs'], expect=['luna','medium']))
        bad(lambda c: P(c).update(x={'description':'no selector, not provisional', 'expect':['luna','high']}))
        bad(lambda c: P(c).update(x={'provisional':True, 'description':'selector-less without expect'}))
        bad(lambda c: P(c).update(x={'provisional':'yes', 'expect':['luna','high']}))
        bad(lambda c: P(c)['scout'].update(mode_id='Plan Mode'))
        bad(lambda c: P(c)['lookup'].update(description=''))
        bad(lambda c: P(c)['lookup'].update(surprise=1))
        bad(lambda c: P(c)['dev-l2-general'].update(expect=['opus','high']))             # not a candidate of level 2
        bad(lambda c: P(c)['dev-l2-general'].update(expect=['terra','xhigh']))
        bad(lambda c: P(c)['review-codex-work'].update(expect=['opus','high']))          # not a route or level candidate of code_review_codex
        bad(lambda c: P(c)['root-orchestrator'].update(expect=['terra','high']))         # not a candidate of the role
        bad(lambda c: c['roles']['root_orchestrator'].update(paseo=['luna','high']))     # orchestrator on a tool without Paseo tools
        bad(lambda c: P(c).update({'Bad_Id':{'level':1}}))
        bad(lambda c: P(c).update(x={'level':True}))
        bad(lambda c: c['hosts'].pop('paseo'))
        bad(lambda c: None, raw=lambda t: t.replace('"lookup": {"role"', '"dev-l1-simple": {"level": 1}, "lookup": {"role"', 1))   # duplicate profile id
        bad(lambda c: None, raw=lambda t: t.replace('"schema": 1,', '"schema": 1, "schema": 1,', 1))
        # valid variants load
        c=json.loads(json.dumps(base)); P(c)['dev-l2-general'].update(expect=['sonnet','high']); P(c)['x']={'level':2,'expect':['terra','high'],'provisional':True}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.json'; p.write_text(json.dumps(c)); routing.load_config(p)

class LoaderHoleTests(unittest.TestCase):
    base=json.loads(routing.DEFAULT_CONFIG.read_text())

    def bad(self, mut):
        c=json.loads(json.dumps(self.base)); mut(c)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.json'; p.write_text(json.dumps(c))
            with self.assertRaises(PolicyError) as cm: routing.load_config(p)
            self.assertEqual(str(cm.exception), 'routing_config_invalid')

    def test_review_mode_write_block_types_must_be_review_types(self):
        self.bad(lambda c: c['review_mode'].update(write_block_required_task_types=['security_review','docs']))
        self.bad(lambda c: c['review_mode'].update(write_block_required_task_types='security_review'))
        self.bad(lambda c: c['review_mode'].update(write_block_required_task_types=['nope']))

    def test_review_mode_needs_a_mode_id_for_every_paseo_tool(self):
        for tool in ('claude','codex'):
            self.bad(lambda c: c['review_mode'].pop(tool))
            self.bad(lambda c: c['review_mode'].update({tool: {'note':'no modeId'}}))
        self.bad(lambda c: c['hosts']['paseo'].update(tools=['claude','codex','gemini']))

    def test_lateral_entry_tool_must_be_a_tool_of_that_host(self):
        self.bad(lambda c: c['levels']['2']['lateral'].update(claude=['terra','high']))    # Codex model on the claude-only host
        self.bad(lambda c: c['levels']['2']['lateral'].update(codex=['sonnet','high']))    # Claude model on the codex-only host

    def test_runtime_stays_fail_closed_when_a_review_mode_tool_entry_is_missing(self):
        # a hand-built config without load_config validation: a missing entry means blocked, never unblocked
        for missing, avail in (('codex', ['luna']), ('claude', None), ('claude', ['sonnet'])):
            c=json.loads(json.dumps(self.base)); c['review_mode'].pop(missing)
            x=routing.route(c, host='paseo', task_type='security_review', available=avail)
            self.assertEqual(x['action'], 'blocked_no_available_model', (missing, avail))
            self.assertIsNone(x['paseo_create_agent']); self.assertIn('review_write_block_requires_claude_plan', x['reasons'])
        c=json.loads(json.dumps(self.base)); c['review_mode'].pop('claude')
        x=routing.route(c, host='paseo', task_type='security_review', implementer_family='codex')
        self.assertEqual((x['action'], x['paseo_create_agent']), ('blocked_no_independent_reviewer', None))
        self.assertEqual(routing.route(c, host='paseo', task_type='docs')['action'], 'run')       # other types are unaffected

if __name__=='__main__': unittest.main()
