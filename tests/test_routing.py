import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ai_policy import routing
from ai_policy.bundle import PolicyError

C=routing.load_config()

def r(**k): return routing.route(C, **k)
def pick(x): return (x['alias'], x['effort'])

class RoutingTests(unittest.TestCase):
    def test_simple(self):
        for t in ('docs','tests','rename'):
            self.assertEqual(pick(r(host='orca', task_type=t)), ('luna','medium'))
        self.assertEqual(pick(r(host='claude', task_type='docs')), ('sonnet','low'))
        self.assertEqual(pick(r(host='codex', task_type='docs')), ('luna','medium'))

    def test_general_and_complex(self):
        for t in ('feature','api'): self.assertEqual(pick(r(host='orca', task_type=t)), ('luna','high'))
        for t in ('multi_module','async'):
            x=r(host='orca', task_type=t); self.assertEqual(pick(x), ('sonnet','high')); self.assertEqual(x['level'], 3)

    def test_orca_task_routes_and_safety_precedence(self):
        cases = {
            'architecture': ('terra', 'high'), 'requirements': ('sonnet', 'high'),
            'frontend_complex': ('sonnet', 'high'), 'log_summary': ('luna', 'low'),
            'code_review_codex': ('sonnet', 'medium'), 'important_review_codex': ('sonnet', 'high'),
            'code_review_claude': ('terra', 'high'), 'diagnose_codex_failure': ('sonnet', 'high'),
            'diagnose_claude_failure': ('luna', 'high'),
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                self.assertEqual(pick(r(host='orca', task_type=task)), expected)
        self.assertEqual(pick(r(host='orca', task_type='api', available=['terra'])), ('terra', 'high'))
        self.assertEqual(pick(r(host='orca', task_type='code_review_claude', available=['luna'])), ('luna', 'high'))
        self.assertEqual(r(host='orca', task_type='code_review_codex', available=['luna'])['action'], 'blocked_no_available_model')
        self.assertEqual(pick(r(host='orca', task_type='frontend', level=1)), ('luna', 'medium'))
        self.assertEqual(pick(r(host='orca', task_type='auth', level=1, available=['sol'])), ('sol', 'high'))
        self.assertEqual(pick(r(host='orca', task_type='architecture', failure_kind='data_integrity_risk')), ('opus', 'high'))
        self.assertEqual(pick(r(host='claude', task_type='feature')), ('sonnet', 'medium'))

    def test_failure_escalation(self):
        x=r(host='orca', task_type='feature', failures=2, failure_kind='verification')
        self.assertEqual((x['action'], x['level'], pick(x)), ('escalate', 3, ('sonnet','high')))
        self.assertTrue(x['escalated']); self.assertTrue(x['handoff_fields'])
        x=r(host='orca', level=3, failures=2); self.assertEqual(pick(x), ('opus','high'))
        self.assertEqual(pick(r(host='codex', level=3, failures=2)), ('sol','high'))
        # the one counted failure at LEVEL 2 now retries on the lateral standard-tier model (Terra) instead of the same model
        x=r(host='orca', level=2, failures=1, failure_kind='reasoning')
        self.assertEqual((x['action'], pick(x), x['escalated']), ('retry', ('terra','high'), False))
        x=r(host='orca', level=3, failures=1, failure_kind='reasoning')
        self.assertEqual((x['action'], pick(x), x['escalated']), ('retry', ('sonnet','high'), False))
        x=r(host='orca', level=4, failures=2, failure_kind='verification')
        self.assertEqual((x['action'], pick(x)), ('escalate', ('fable','high')))
        self.assertTrue(x['preserve_state'] and x['handoff_fields'])

    def test_immediate_and_high_risk(self):
        x=r(host='orca', task_type='feature', failure_kind='architecture_risk')
        self.assertEqual((x['action'], x['level']), ('escalate', 4))
        for t in ('security','destructive_db','auth','crypto'):
            x=r(host='orca', task_type=t); self.assertEqual((x['level'], x['high_risk'], x['human_gate'], x['alias']), (4, True, True, 'opus'))
        self.assertTrue(x['premium'])

    def test_resolved_returns_default(self):
        x=r(host='orca', task_type='docs', failures=5, failure_kind='reasoning', resolved=True)
        self.assertEqual((x['action'], pick(x), x['level']), ('return_to_default', ('luna','medium'), 1))
        self.assertFalse(x['preserve_state'])

    def test_roles(self):
        for role in ('project_coordinator','root_orchestrator'):
            self.assertEqual(pick(r(host='claude', role=role)), ('sonnet','medium'))
        self.assertEqual(pick(r(host='orca', role='root_orchestrator')), ('terra','high'))
        self.assertEqual(pick(r(host='orca', role='project_coordinator')), ('luna','high'))
        self.assertEqual(pick(r(host='codex', role='root_orchestrator')), ('luna','high'))

    def test_availability(self):
        x=r(host='orca', task_type='docs', available=['sonnet','opus'])
        self.assertEqual(pick(x), ('sonnet','medium')); self.assertTrue(x['fallback_used']); self.assertIn('model_unavailable:luna', x['reasons'])
        # fallback takes the effort that model has at the same level elsewhere; premium is never a fallback for ordinary work
        self.assertEqual(pick(r(host='orca', task_type='feature', available=['luna'])), ('luna','high'))
        self.assertEqual(r(host='claude', task_type='docs', available=['opus'])['action'], 'blocked_no_available_model')
        self.assertEqual(r(host='orca', task_type='docs', available=['claude-sonnet-5-5'])['alias'], 'sonnet')
        x=r(host='orca', task_type='docs', available=[])
        self.assertEqual((x['action'], x['alias'], x['model'], x['preserve_state']), ('blocked_no_available_model', None, None, True))
        self.assertEqual(x['orca_worker_args'], [])
        x=r(host='codex', task_type='security', available=['luna'])
        self.assertEqual(x['action'], 'blocked_no_available_model')

    def test_exceptional(self):
        self.assertEqual(r(host='orca', task_type='security')['alias'], 'opus')
        # never a starting route: high-risk starts at LEVEL 4, fallbacks never reach the exceptional tier
        self.assertEqual(r(host='orca', task_type='security')['alias'], 'opus')
        self.assertEqual(r(host='codex', task_type='security', available={'luna'})['action'], 'blocked_no_available_model')
        # LEVEL 4 failing twice escalates to the last resort; failing there hands off
        for host, alias in (('orca','fable'), ('claude','fable'), ('codex','astra')):
            x=r(host=host, level=4, failures=2, failure_kind='verification')
            self.assertEqual((x['action'], x['level'], x['alias'], x['tier']), ('escalate', 5, alias, 'exceptional'))
            self.assertIn('last_resort', x['reasons'])
        self.assertEqual(r(host='orca', level=4, failures=2, failure_kind='verification', available={'astra'})['alias'], 'astra')
        x=r(host='orca', level=5, failures=2, failure_kind='verification')
        self.assertEqual((x['action'], x['alias']), ('handoff_to_lead', 'fable'))
        self.assertEqual(r(host='orca', level=4, failure_kind='architecture_risk')['action'], 'handoff_to_lead')
        x=r(host='orca', task_type='docs', resolved=True); self.assertEqual((x['action'], pick(x)), ('return_to_default', ('luna','medium')))
        for kw in ({}, {'resolved':True}):
            with self.assertRaisesRegex(PolicyError, 'last_resort_requires_escalation'): r(host='orca', level=5, **kw)
        self.assertEqual(r(host='orca', level=5, failures=1, failure_kind='verification')['action'], 'retry')
        x=r(host='orca', level=5, failures=2, failure_kind='verification'); self.assertEqual(x['orca_worker_args'], [])
        # roles escalate one step from their own level, not straight to LEVEL 4
        self.assertEqual(pick(r(host='orca', role='lookup', failures=2)), ('luna','high'))
        self.assertEqual(pick(r(host='orca', role='project_coordinator', failures=2)), ('sonnet','high'))

    def test_non_model_failure(self):
        for k in ('environment','model_unavailable'):
            x=r(host='orca', level=2, failures=1, failure_kind=k)
            self.assertEqual((x['action'], pick(x), x['preserve_state'], x['attempts_reset'], x['escalated']), ('retry_same_model_preserve_state', ('luna','high'), True, False, False))
            self.assertIn('non_model_failure', x['reasons'])
        # Orca execution retries: up to 3 runs in total, then stop without escalating the model
        x=r(host='orca', task_type='feature', failures=2, failure_kind='environment'); self.assertEqual(x['action'], 'retry_same_model_preserve_state')
        x=r(host='orca', task_type='feature', failures=3, failure_kind='tool')
        self.assertEqual((x['action'], x['level'], x['escalated'], x['orca_worker_args']), ('handoff_to_lead', 2, False, []))

    def test_worker_args(self):
        self.assertEqual(r(host='orca', task_type='docs')['orca_worker_args'], ['--agent','codex','--model','gpt-6-luna','--effort','medium'])
        self.assertEqual(r(host='claude', role='lookup')['orca_worker_args'], ['--agent','claude','--model','claude-haiku-5-5'])

    def test_codex_family_uses_newest_supported_cached_generation(self):
        catalog=[
            {'slug':'gpt-6-luna','visibility':'list','supported_in_api':True},
            {'slug':'gpt-7.1-luna','visibility':'list','supported_in_api':True},
            {'slug':'gpt-7.2.1-luna','visibility':'list','supported_in_api':True},
            {'slug':'gpt-9-luna','visibility':'hide','supported_in_api':True},
            {'slug':'gpt-10-luna','visibility':'list','supported_in_api':False},
        ]
        x=routing.route(C, host='codex', task_type='docs', model_catalog=catalog)
        self.assertEqual(x['model'], 'gpt-7.2.1-luna')
        self.assertEqual(x['model_resolution'], 'codex_catalog')
        self.assertEqual(x['orca_worker_args'], ['--agent','codex','--model','gpt-7.2.1-luna','--effort','medium'])

    def test_codex_family_catalog_falls_back_to_pinned_id_when_no_match(self):
        x=routing.route(C, host='codex', task_type='docs', model_catalog=[
            {'slug':'gpt-7.1-sol','visibility':'list','supported_in_api':True},
            {'slug':'gpt-8-luna','visibility':'list','supported_in_api':False},
        ])
        self.assertEqual(x['model'], 'gpt-6-luna')
        self.assertEqual(x['model_resolution'], 'pinned_fallback')

    def test_explicit_availability_must_include_resolved_generation(self):
        x=routing.route(C, host='codex', task_type='docs', available=['gpt-6-luna'], model_catalog=[
            {'slug':'gpt-7-luna','visibility':'list','supported_in_api':True},
        ])
        self.assertEqual(x['action'], 'blocked_no_available_model')

    def test_stale_codex_catalog_does_not_claim_current_generation(self):
        catalog={'fetched_at':'2000-01-01T00:00:00Z','models':[
            {'slug':'gpt-8-luna','visibility':'list','supported_in_api':True},
        ]}
        x=routing.route(C, host='codex', task_type='docs', model_catalog=catalog)
        self.assertEqual((x['model'], x['model_resolution']), ('gpt-6-luna','pinned_fallback'))

    def test_fresh_timestamped_codex_catalog_resolves_generation(self):
        from datetime import datetime, timezone
        catalog={'fetched_at':datetime.now(timezone.utc).isoformat(),'models':[
            {'slug':'gpt-8-luna','visibility':'list','supported_in_api':True},
        ]}
        x=routing.route(C, host='codex', task_type='docs', model_catalog=catalog)
        self.assertEqual((x['model'], x['model_resolution']), ('gpt-8-luna','codex_catalog'))

    def test_resolve_family_preserves_project_selected_codex_family(self):
        x=routing.resolve_codex_family(C, 'terra', model_catalog=[
            {'slug':'gpt-6.1-terra','visibility':'list','supported_in_api':True},
            {'slug':'gpt-7.2.1-terra','visibility':'list','supported_in_api':True},
        ], effort='high')
        self.assertEqual(x['action'], 'run')
        self.assertEqual((x['model'], x['model_resolution']), ('gpt-7.2.1-terra','codex_catalog'))
        self.assertEqual(x['orca_worker_args'], ['--agent','codex','--model','gpt-7.2.1-terra','--effort','high'])

    def test_cli_reads_explicit_model_catalog(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'models.json'
            p.write_text(json.dumps({'fetched_at':datetime.now(timezone.utc).isoformat(), 'models':[{'slug':'gpt-7-luna','visibility':'list','supported_in_api':True}]}))
            b=io.StringIO()
            with contextlib.redirect_stdout(b):
                code=routing.main(['--host','codex','--task-type','docs','--model-catalog',str(p)])
            result=json.loads(b.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((result['model'], result['model_resolution']), ('gpt-7-luna','codex_catalog'))

    def test_errors(self):
        for kw, code in (({'host':'x','task_type':'docs'}, 'unknown_host'), ({'host':'orca','task_type':'nope'}, 'unknown_task_type'),
                         ({'host':'orca','task_type':'docs','failure_kind':'zzz'}, 'unknown_failure_kind'), ({'host':'orca'}, 'invalid_selector'),
                         ({'host':'orca','role':'lookup','level':1}, 'invalid_selector')):
            with self.assertRaises(PolicyError) as cm: r(**kw)
            self.assertEqual(str(cm.exception), code)

    def test_explicit_level_wins(self):
        x=r(host='orca', task_type='docs', level=3); self.assertEqual(x['level'], 3); self.assertIn('explicit_level_overrides_task_type', x['reasons'])

    def test_config_validation(self):
        base=json.loads(routing.DEFAULT_CONFIG.read_text())
        def bad(mut):
            c=json.loads(json.dumps(base)); mut(c)
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'c.json'; p.write_text(json.dumps(c))
                with self.assertRaises(PolicyError) as cm: routing.load_config(p)
                self.assertEqual(str(cm.exception), 'routing_config_invalid')
        bad(lambda c: c['levels']['1'].update(orca=['luna','ultra']))
        bad(lambda c: c['levels']['1'].update(orca=['ghost','low']))
        bad(lambda c: c['roles']['lookup'].update(claude=['haiku','ultra']))
        bad(lambda c: c['models']['luna'].update(codex_family='../luna'))
        bad(lambda c: c.pop('fallbacks'))
        bad(lambda c: c.update(schema=2))
        bad(lambda c: c['cross_family_review'].update(task_types=['nope']))
        bad(lambda c: c['cross_family_review'].update(blocking_types=['docs']))

    def test_cli(self):
        def run(*a):
            b=io.StringIO()
            with contextlib.redirect_stdout(b): code=routing.main(list(a))
            return code, json.loads(b.getvalue())
        self.assertEqual(run('--host','orca','--task-type','docs')[0], 0)
        code, x=run('--host','orca','--task-type','docs','--available','')
        self.assertEqual((code, x['action']), (40, 'blocked_no_available_model'))
        self.assertEqual(run('--host','nope','--task-type','docs'), (30, {'schema':1,'error':'unknown_host'}))
        self.assertEqual(run('--host','orca','--task-type','docs','--config','/nonexistent.json')[1]['error'], 'routing_config_invalid')

PATH_HOSTS={
    # (level, alias, effort) for every attempt when each attempt fails with a counted failure, starting at LEVEL 1
    'orca':   [(1,'luna','medium'),(1,'luna','medium'),(2,'luna','high'),(2,'terra','high'),(3,'sonnet','high'),(3,'sonnet','high'),(4,'opus','high'),(4,'opus','high'),(5,'fable','high'),(5,'fable','high')],
    'paseo':  [(1,'luna','medium'),(1,'luna','medium'),(2,'luna','high'),(2,'terra','high'),(3,'sonnet','high'),(3,'sonnet','high'),(4,'opus','high'),(4,'opus','high'),(5,'fable','high'),(5,'fable','high')],
    'codex':  [(1,'luna','medium'),(1,'luna','medium'),(2,'luna','high'),(2,'terra','high'),(3,'luna','xhigh'),(3,'luna','xhigh'),(4,'sol','high'),(4,'sol','high'),(5,'astra','high'),(5,'astra','high')],
    'claude': [(1,'sonnet','low'),(1,'sonnet','low'),(2,'sonnet','medium'),(2,'sonnet','medium'),(3,'sonnet','high'),(3,'sonnet','high'),(4,'opus','high'),(4,'opus','high'),(5,'fable','high'),(5,'fable','high')],
}

def walk(host, **kw):
    """Fail every attempt (counted failure) from LEVEL 1; an escalate result is the first attempt at its new level."""
    x=r(host=host, level=1, **kw); attempts=[(x['level'], x['alias'], x['effort'])]; level=1; f=0
    for _ in range(40):
        f+=1
        x=r(host=host, level=level, failures=f, failure_kind='verification', **kw)
        if x['action']=='retry': attempts.append((x['level'], x['alias'], x['effort']))
        elif x['action']=='escalate': level, f=x['level'], 0; attempts.append((x['level'], x['alias'], x['effort']))
        else: return attempts, x
    raise AssertionError('no termination')

class LateralStepTests(unittest.TestCase):
    def test_full_escalation_path_and_total_attempts(self):
        for host, expected in PATH_HOSTS.items():
            with self.subTest(host=host):
                attempts, last=walk(host)
                self.assertEqual(attempts, expected)
                self.assertEqual(len(attempts), 10)                       # 2 attempts per level, 5 levels, bounded
                self.assertEqual(sum(1 for a in attempts if a[0]==2), 2)  # Luna + lateral = exactly the two LEVEL 2 attempts
                self.assertEqual(last['action'], 'handoff_to_lead')
                self.assertEqual(len([a for a in attempts if a[0]<4]), 6)  # at most six attempts before LEVEL 4
        self.assertNotIn('claude', C['levels']['2']['lateral'])      # the claude host has no Codex tool, so no lateral

    def test_lateral_is_standard_tier_never_premium_and_never_sol(self):
        for host in ('orca','paseo','codex'):
            x=r(host=host, level=2, failures=1, failure_kind='verification')
            self.assertEqual((x['alias'], x['tier'], x['action'], x['fallback_used'], x['premium'], x['lateral']), ('terra','standard','retry',False,False,True))
            self.assertIn('lateral_step', x['reasons'])
        # Sol is never a default or lateral for LEVEL 1-3 or any role; it stays the LEVEL 4 codex/alternate choice only
        for lv in ('1','2','3'):
            for k, e in C['levels'][lv].items():
                if k in C['hosts']: self.assertNotEqual(e[0], 'sol')
                if k.endswith('_alternatives') or k=='lateral': self.assertNotIn('sol', str(e))
        self.assertFalse(any(e['paseo'][0]=='sol' or any(h[0]=='sol' for h in e.get('orca_alternatives', ())) for e in C['roles'].values()))
        x=r(host='claude', level=2, failures=1, failure_kind='verification')
        self.assertEqual((pick(x), x['lateral']), (('sonnet','medium'), False))  # no Codex tool: same model

    def test_lateral_unavailable_goes_to_level_3_never_opus(self):
        x=r(host='orca', level=2, failures=1, failure_kind='verification', available=['luna','sonnet','opus','sol'])
        self.assertEqual((x['action'], x['level'], x['alias'], x['lateral']), ('escalate', 3, 'sonnet', False))
        self.assertIn('lateral_unavailable:terra', x['reasons'])
        for host in ('orca','paseo'):
            x=r(host=host, level=2, failures=1, failure_kind='verification', available=['sol','opus'])
            self.assertEqual((x['action'], x['alias'], x['level']), ('blocked_no_available_model', None, 3))
        # fallbacks are off for the lateral step: unavailable Terra never turns into Sonnet, Luna or Opus at LEVEL 2
        self.assertNotEqual(r(host='paseo', level=2, failures=1, failure_kind='verification', available=['opus','sonnet'])['level'], 2)

    def test_lateral_applies_to_task_types_and_not_to_roles_or_non_model_failures(self):
        self.assertEqual(pick(r(host='orca', task_type='feature', failures=1, failure_kind='verification')), ('terra','high'))
        self.assertEqual(pick(r(host='orca', role='project_coordinator', failures=1, failure_kind='verification')), ('luna','high'))
        self.assertEqual(pick(r(host='orca', level=2, failures=1, failure_kind='environment')), ('luna','high'))
        self.assertEqual(r(host='orca', level=2, failures=0)['alias'], 'luna')
        self.assertEqual(r(host='orca', level=2, failures=2, failure_kind='verification')['level'], 3)
        self.assertFalse(r(host='orca', level=2, failures=0)['lateral'])

    def test_lateral_on_paseo_overrides_task_route_and_orchestrator_roles_are_untouched(self):
        # Paseo uses orca_task_routes for tasks; the lateral step must replace the routed choice, not be hidden by it.
        x=r(host='paseo', task_type='feature')
        self.assertEqual((pick(x), x['lateral']), (('luna','high'), False))
        x=r(host='paseo', task_type='feature', failures=1, failure_kind='verification')
        self.assertEqual((pick(x), x['lateral'], x['paseo_create_agent']['provider']), (('terra','high'), True, 'codex/gpt-6.1-terra'))
        self.assertIsNone(x['paseo_profile'])
        for role in ('root_orchestrator','project_coordinator'):
            x=r(host='paseo', role=role, failures=1, failure_kind='verification')
            self.assertEqual((pick(x), x['lateral']), (('sonnet','high'), False))

class FailedFamilyTests(unittest.TestCase):
    def l5(self, host='paseo', **kw): return r(host=host, level=4, failures=2, failure_kind='verification', **kw)

    def test_opposite_family_of_last_l4_failure(self):
        for host in ('orca','paseo'):
            self.assertEqual(pick(self.l5(host, failed_family='claude')), ('astra','high'))
            self.assertEqual(pick(self.l5(host, failed_family='codex')), ('fable','high'))
            self.assertEqual(pick(self.l5(host, failed_family=['claude','codex'])), ('fable','high'))
            self.assertEqual(pick(self.l5(host, failed_family='both')), ('fable','high'))
            self.assertEqual(pick(self.l5(host)), ('fable','high'))
            self.assertEqual(pick(self.l5(host, failed_family=[])), ('fable','high'))
        x=self.l5(failed_family='claude')
        self.assertEqual((x['level'], x['action'], x['premium'], x['fallback_used']), (5, 'escalate', True, False))
        self.assertIn('l5_opposite_family:astra', x['reasons'])
        self.assertEqual(x['paseo_create_agent']['provider'], 'codex/gpt-6.2-astra')
        # level 5 retry/handoff keep the same selection
        x=r(host='paseo', level=5, failures=1, failure_kind='verification', failed_family='claude'); self.assertEqual((x['action'], x['alias']), ('retry','astra'))

    def test_preference_is_soft_and_host_bound(self):
        x=self.l5(failed_family='claude', available=['fable'])
        self.assertEqual(x['alias'], 'fable'); self.assertIn('l5_opposite_family_unavailable', x['reasons'])
        self.assertEqual(pick(self.l5('claude', failed_family='claude')), ('fable','high'))   # claude host cannot run Astra
        self.assertEqual(pick(self.l5('codex', failed_family='codex')), ('astra','high'))
        self.assertEqual(pick(self.l5('codex', failed_family='claude')), ('astra','high'))

    def test_last_resort_is_still_never_a_starting_level(self):
        for kw in ({}, {'failed_family':'claude'}, {'failed_family':'codex'}):
            with self.assertRaisesRegex(PolicyError, 'last_resort_requires_escalation'): r(host='paseo', level=5, **kw)
        self.assertEqual(r(host='paseo', level=4, failures=1, failure_kind='verification', failed_family='claude')['level'], 4)  # one L4 failure: retry at L4
        self.assertEqual(r(host='paseo', level=4, failed_family='claude')['alias'], 'opus')
        self.assertEqual(r(host='paseo', task_type='security', failed_family='claude')['alias'], 'opus')
        for bad in ('gemini', ['claude','gemini'], 3):
            with self.assertRaisesRegex(PolicyError, 'unknown_failed_family'): self.l5(failed_family=bad)

    def test_sol_not_chosen_when_it_already_failed(self):
        self.assertEqual(r(host='orca', level=4, available=['sol'])['alias'], 'sol')
        x=r(host='orca', level=4, available=['sol'], failed_models=['sol'])
        self.assertEqual((x['action'], x['alias']), ('blocked_no_available_model', None)); self.assertIn('excluded_failed_model:sol', x['reasons'])
        self.assertEqual(r(host='orca', level=4, failed_models=['sol'])['alias'], 'opus')
        self.assertEqual(r(host='codex', level=4, failed_models=['gpt-6.2-sol'])['action'], 'blocked_no_available_model')
        self.assertEqual(r(host='orca', level=3, failed_models=['sol'])['alias'], 'sonnet')   # only the L4 choice is restricted
        # any failed model is skipped at L4, and Paseo is not special
        x=r(host='paseo', level=4, failed_models='opus'); self.assertEqual(x['alias'], 'sol'); self.assertIn('excluded_failed_model:opus', x['reasons'])
        self.assertEqual(r(host='paseo', level=4, failed_models=['opus','sol'])['action'], 'blocked_no_available_model')

class PremiumFlagTests(unittest.TestCase):
    def test_premium_choices_require_reason(self):
        for kw in ({'host':'orca','level':4},{'host':'paseo','level':4},{'host':'codex','level':4},{'host':'paseo','level':4,'failures':2,'failure_kind':'verification'},
                   {'host':'codex','level':4,'failures':2,'failure_kind':'verification'},{'host':'orca','level':4,'available':['sol']}):
            with self.subTest(kw=kw):
                x=r(**kw); self.assertTrue(x['premium'] and x['premium_requires_reason'])
        for kw in ({'host':'paseo','level':2},{'host':'orca','level':2,'failures':1,'failure_kind':'verification'}):
            x=r(**kw); self.assertFalse(x['premium'] or x['premium_requires_reason'])
        self.assertEqual(C['limits']['max_concurrent_premium_workers'], 1)
        self.assertFalse(r(host='orca', task_type='docs', available=[])['premium_requires_reason'])
        self.assertFalse(r(host='paseo', task_type='security_review', available=['luna'])['premium_requires_reason'])  # blocked: nothing to launch

class CliNewInputsTests(unittest.TestCase):
    def test_cli_passes_new_inputs(self):
        def run(*a):
            b=io.StringIO()
            with contextlib.redirect_stdout(b): code=routing.main(list(a))
            return code, json.loads(b.getvalue())
        nc=('--model-catalog','/nonexistent')
        code, x=run('--host','paseo','--level','4','--failures','2','--failure-kind','verification','--failed-family','claude',*nc)
        self.assertEqual((code, x['alias'], x['orca_worker_args']), (0, 'astra', []))
        code, x=run('--host','orca','--level','4','--failures','2','--failure-kind','verification','--failed-family','claude',*nc)
        self.assertEqual((code, x['alias'], x['orca_worker_args'][:4]), (0, 'astra', ['--agent','codex','--model','gpt-6.2-astra']))
        code, x=run('--host','orca','--level','4','--available','sol','--failed-model','sol',*nc)
        self.assertEqual((code, x['action']), (40, 'blocked_no_available_model'))
        self.assertEqual(run('--host','paseo','--level','4','--failed-family','gemini',*nc), (30, {'schema':1,'error':'unknown_failed_family'}))
        self.assertEqual(run('--host','paseo','--task-type','review','--implementer-family','gemini',*nc), (30, {'schema':1,'error':'unknown_implementer_family'}))

class CrossFamilyReviewTests(unittest.TestCase):
    def test_reviewer_family_differs_from_implementer(self):
        for host in ('orca','paseo'):
            x=r(host=host, task_type='review', implementer_family='claude'); self.assertEqual((x['tool'], x['degraded_independence']), ('codex', False))
            x=r(host=host, task_type='review', implementer_family='codex'); self.assertEqual((x['tool'], x['degraded_independence']), ('claude', False))
        self.assertEqual(pick(r(host='orca', task_type='code_review_claude', implementer_family='claude')), ('terra','high'))
        self.assertEqual(r(host='orca', task_type='security_review', implementer_family='claude')['tool'], 'codex')
        self.assertEqual(r(host='orca', task_type='security_review', implementer_family='codex')['tool'], 'claude')
        # no implementer_family: behavior unchanged
        self.assertEqual(r(host='orca', task_type='review')['degraded_independence'], False)
        self.assertEqual(pick(r(host='orca', task_type='review')), ('sonnet','medium'))

    def test_degraded_independence_for_ordinary_reviews(self):
        x=r(host='orca', task_type='review', implementer_family='claude', available=['sonnet'])
        self.assertEqual((x['action'], x['alias'], x['degraded_independence']), ('run','sonnet',True)); self.assertIn('degraded_independence', x['reasons'])
        x=r(host='claude', task_type='review', implementer_family='claude')   # claude host: no Codex tool at all
        self.assertEqual((x['action'], x['tool'], x['degraded_independence']), ('run','claude',True))
        x=r(host='orca', task_type='important_review', implementer_family='codex', available=['terra'])   # level 3 candidates: sonnet, terra
        self.assertTrue(x['degraded_independence'] and x['alias']=='terra')
        x=r(host='orca', task_type='important_review', implementer_family='codex', available=['luna'])  # not a candidate at this level
        self.assertEqual((x['action'], x['degraded_independence']), ('blocked_no_available_model', False))
        # Paseo: the ordinary review proceeds degraded and still carries its review start configuration
        x=r(host='paseo', task_type='code_review_claude', implementer_family='codex', available=['luna'])
        self.assertEqual((x['action'], x['tool'], x['degraded_independence']), ('run', 'codex', True))
        self.assertIsNotNone(x['paseo_create_agent']); self.assertNotIn('independent_reviewer_required', x['reasons'])
        x=r(host='paseo', task_type='review', implementer_family='claude', available=['sonnet'])
        self.assertEqual((x['action'], x['tool'], x['degraded_independence'], x['paseo_create_agent']['settings']['modeId']), ('run', 'claude', True, 'plan'))

    def test_security_and_high_risk_reviews_are_blocked_without_independence(self):
        x=r(host='orca', task_type='security_review', implementer_family='claude', available=['sonnet'])
        self.assertEqual((x['action'], x['alias'], x['degraded_independence'], x['orca_worker_args']), ('blocked_no_independent_reviewer', None, False, []))
        self.assertTrue(x['preserve_state']); self.assertIn('independent_reviewer_required', x['reasons'])
        self.assertEqual(r(host='claude', task_type='security_review', implementer_family='claude')['action'], 'blocked_no_independent_reviewer')
        self.assertEqual(r(host='codex', task_type='security_review', implementer_family='codex')['action'], 'blocked_no_independent_reviewer')
        # nothing usable at all stays the generic block
        self.assertEqual(r(host='orca', task_type='review', implementer_family='claude', available=[])['action'], 'blocked_no_available_model')

    def test_existing_code_review_codex_block_is_kept(self):
        self.assertEqual(r(host='orca', task_type='code_review_codex', available=['luna'])['action'], 'blocked_no_available_model')
        self.assertEqual(r(host='orca', task_type='code_review_codex', implementer_family='codex', available=['luna'])['action'], 'blocked_no_available_model')
        self.assertEqual(pick(r(host='orca', task_type='code_review_codex', implementer_family='codex')), ('sonnet','medium'))

    def test_bad_implementer_family_and_non_review_types_ignored(self):
        with self.assertRaisesRegex(PolicyError, 'unknown_implementer_family'): r(host='orca', task_type='review', implementer_family='gemini')
        x=r(host='orca', task_type='docs', implementer_family='codex'); self.assertEqual((pick(x), x['degraded_independence']), (('luna','medium'), False))
        x=r(host='orca', role='lookup', implementer_family='codex'); self.assertFalse(x['degraded_independence'])

    def test_degraded_independence_key_is_always_present(self):
        for kw in ({'task_type':'docs'},{'level':4},{'role':'lookup'},{'task_type':'review','implementer_family':'claude'}):
            self.assertIs(r(host='paseo', **kw)['degraded_independence'], False)

    def test_cross_family_and_write_block_types_are_kept_in_sync(self):
        self.assertEqual(set(C['cross_family_review']['task_types']), set(C['review_mode']['task_types']))
        base=json.loads(routing.DEFAULT_CONFIG.read_text())
        def bad(mut):
            c=json.loads(json.dumps(base)); mut(c)
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'c.json'; p.write_text(json.dumps(c))
                with self.assertRaises(PolicyError) as cm: routing.load_config(p)
                self.assertEqual(str(cm.exception), 'routing_config_invalid')
        bad(lambda c: c['review_mode'].update(task_types=[t for t in c['review_mode']['task_types'] if t!='important_review']))
        bad(lambda c: c['cross_family_review'].update(task_types=[t for t in c['cross_family_review']['task_types'] if t!='review'], blocking_types=['security_review']))
        bad(lambda c: c.pop('cross_family_review'))
        bad(lambda c: c.pop('review_mode'))

class PaseoSecurityReviewIndependenceTests(unittest.TestCase):
    """security_review on Paseo combines independence (MINE) with the write-block (THEIRS); fail-closed by decision D1."""
    def sr(self, impl, available=None): return r(host='paseo', task_type='security_review', implementer_family=impl, available=available)

    def assert_blocked(self, x):
        self.assertEqual(x['action'], 'blocked_no_independent_reviewer')
        self.assertIsNone(x['paseo_create_agent']); self.assertIsNone(x['paseo_profile'])
        for k in ('alias','tool','agent','model','effort','tier'): self.assertIsNone(x[k])
        self.assertEqual(x['orca_worker_args'], [])
        self.assertFalse(x['premium'] or x['premium_requires_reason'] or x['degraded_independence']); self.assertTrue(x['preserve_state'])

    def test_codex_implementer_with_claude_available_runs_claude_plan_reviewer(self):
        for avail in (None, ['sonnet','luna'], ['sonnet']):
            x=self.sr('codex', avail)
            self.assertEqual((x['action'], pick(x), x['paseo_create_agent']['settings']['modeId'], x['degraded_independence']), ('run', ('sonnet','high'), 'plan', False))
            self.assertTrue(x['paseo_review']['write_block_required'])
            self.assertNotIn('review_write_block_requires_claude_plan', x['reasons'])

    def test_codex_implementer_with_only_codex_is_blocked_with_both_reasons(self):
        x=self.sr('codex', ['luna'])
        self.assert_blocked(x)
        self.assertIn('independent_reviewer_required', x['reasons']); self.assertIn('review_write_block_requires_claude_plan', x['reasons'])
        self.assertNotIn('degraded_independence', x['reasons'])

    def test_claude_implementer_with_only_claude_is_blocked(self):
        x=self.sr('claude', ['sonnet'])
        self.assert_blocked(x); self.assertIn('independent_reviewer_required', x['reasons'])
        self.assertNotIn('review_write_block_requires_claude_plan', x['reasons'])

    def test_claude_implementer_with_both_families_is_blocked(self):
        for avail in (None, ['sonnet','luna']):
            x=self.sr('claude', avail)
            self.assert_blocked(x)
            self.assertIn('review_write_block_requires_claude_plan', x['reasons']); self.assertIn('independent_reviewer_required', x['reasons'])

    def test_important_review_joins_review_mode(self):
        # review_mode.task_types now equals cross_family_review.task_types, so important_review gets the Claude plan-mode start configuration.
        x=r(host='paseo', task_type='important_review')
        self.assertEqual((pick(x), x['paseo_create_agent']['settings']['modeId'], x['paseo_review']['write_block_required']), (('sonnet','high'), 'plan', False))

    def test_without_implementer_family_the_write_block_behaviour_is_unchanged(self):
        x=r(host='paseo', task_type='security_review', available=['luna'])
        self.assertEqual(x['action'], 'blocked_no_available_model'); self.assertNotIn('independent_reviewer_required', x['reasons'])
        self.assertEqual(r(host='paseo', task_type='security_review')['paseo_create_agent']['settings']['modeId'], 'plan')

    def test_cli_exit_code_and_state_preserved(self):
        def run(*a):
            b=io.StringIO()
            with contextlib.redirect_stdout(b): code=routing.main(list(a))
            return code, json.loads(b.getvalue())
        nc=('--model-catalog','/nonexistent')
        code, x=run('--host','paseo','--task-type','security_review','--implementer-family','claude',*nc)
        self.assertEqual((code, x['action'], x['preserve_state']), (40, 'blocked_no_independent_reviewer', True))
        code, x=run('--host','paseo','--task-type','security_review','--implementer-family','codex',*nc)
        self.assertEqual((code, x['action'], x['paseo_create_agent']['settings']['modeId']), (0, 'run', 'plan'))
        code, x=run('--host','orca','--task-type','security_review','--implementer-family','claude','--available','sonnet',*nc)
        self.assertEqual((code, x['action']), (40, 'blocked_no_independent_reviewer'))

class LateralScopeTests(unittest.TestCase):
    """The lateral compares with the model the first attempt really used, keeps its tool, and never touches cross-family review types."""
    def retry(self, host, t, **kw): return r(host=host, task_type=t, failures=1, failure_kind='verification', **kw)

    def test_review_and_diagnose_routes_keep_their_first_attempt_tool(self):
        for host in ('orca','paseo'):
            for t in ('code_review_codex','review','important_review_codex','security_review','code_review_claude','diagnose_codex_failure','diagnose_claude_failure'):
                with self.subTest(host=host, task=t):
                    first, again=r(host=host, task_type=t), self.retry(host, t)
                    self.assertEqual((again['tool'], again['action']), (first['tool'], 'retry'))
                    if t!='diagnose_claude_failure': self.assertFalse(again['lateral'])   # Luna-first and Codex-tool: the Terra lateral keeps the tool
        for host in ('orca','paseo'):
            for t in ('code_review_codex','review','diagnose_codex_failure','important_review_codex'):
                self.assertEqual((pick(self.retry(host, t)), self.retry(host, t)['tool']), (pick(r(host=host, task_type=t)), 'claude'))   # exactly the first route again
        # no independence downgrade without or with implementer_family
        x=self.retry('orca', 'code_review_codex', implementer_family='codex')
        self.assertEqual((pick(x), x['degraded_independence']), (('sonnet','medium'), False))
        x=self.retry('paseo', 'review', implementer_family='codex')
        self.assertEqual((x['tool'], x['degraded_independence'], x['paseo_create_agent']['settings']['modeId']), ('claude', False, 'plan'))
        x=self.retry('paseo', 'review')
        self.assertEqual((x['tool'], x['paseo_create_agent']['settings']['modeId']), ('claude', 'plan'))
        self.assertEqual(pick(self.retry('orca', 'diagnose_codex_failure')), ('sonnet','high'))

    def test_luna_first_routes_and_plain_level_2_still_get_the_lateral(self):
        for host in ('orca','paseo'):
            for t in ('feature','api','frontend','bugfix','test_implementation'):
                with self.subTest(host=host, task=t):
                    x=self.retry(host, t); self.assertEqual((pick(x), x['lateral'], x['action']), (('terra','high'), True, 'retry'))
        for host in ('orca','paseo','codex'):
            x=r(host=host, level=2, failures=1, failure_kind='verification'); self.assertEqual((pick(x), x['lateral']), (('terra','high'), True))
        self.assertEqual(pick(self.retry('codex', 'feature')), ('terra','high'))

    def test_lateral_needs_the_same_tool_as_the_first_attempt(self):
        # A Claude-first level 2 route (requirements: Sonnet high) is not turned into a Codex attempt.
        x=self.retry('orca', 'requirements'); self.assertEqual((pick(x), x['lateral'], x['action']), (('sonnet','high'), False, 'retry'))
        x=self.retry('paseo', 'requirements'); self.assertEqual((pick(x), x['lateral']), (('sonnet','high'), False))

    def test_two_attempt_total_is_unchanged(self):
        for host, expected in PATH_HOSTS.items():
            attempts, last=walk(host); self.assertEqual((attempts, len(attempts)), (expected, 10))
        # a skipped lateral still escalates after the second counted failure
        x=r(host='orca', task_type='code_review_codex', failures=2, failure_kind='verification')
        self.assertEqual((x['action'], x['level']), ('escalate', 3))

if __name__=='__main__': unittest.main()
