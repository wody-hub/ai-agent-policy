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
        for t in ('feature','api'): self.assertEqual(pick(r(host='orca', task_type=t)), ('sonnet','medium'))
        for t in ('multi_module','async'):
            x=r(host='orca', task_type=t); self.assertEqual(pick(x), ('sonnet','high')); self.assertEqual(x['level'], 3)

    def test_failure_escalation(self):
        x=r(host='orca', task_type='feature', failures=2, failure_kind='verification')
        self.assertEqual((x['action'], x['level'], pick(x)), ('escalate', 3, ('sonnet','high')))
        self.assertTrue(x['escalated']); self.assertTrue(x['handoff_fields'])
        x=r(host='orca', level=3, failures=2); self.assertEqual(pick(x), ('opus','high'))
        self.assertEqual(pick(r(host='codex', level=3, failures=2)), ('sol','high'))
        x=r(host='orca', level=2, failures=1, failure_kind='reasoning')
        self.assertEqual((x['action'], pick(x), x['escalated']), ('retry', ('sonnet','medium'), False))
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
        for h in ('orca','claude'):
            for role in ('project_coordinator','root_orchestrator'): self.assertEqual(pick(r(host=h, role=role)), ('sonnet','medium'))
        self.assertEqual(pick(r(host='codex', role='root_orchestrator')), ('luna','high'))

    def test_availability(self):
        x=r(host='orca', task_type='docs', available=['sonnet','opus'])
        self.assertEqual(pick(x), ('sonnet','low')); self.assertTrue(x['fallback_used']); self.assertIn('model_unavailable:luna', x['reasons'])
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
        self.assertEqual(pick(r(host='orca', role='lookup', failures=2)), ('sonnet','medium'))
        self.assertEqual(pick(r(host='orca', role='project_coordinator', failures=2)), ('sonnet','high'))

    def test_non_model_failure(self):
        for k in ('environment','model_unavailable'):
            x=r(host='orca', level=2, failures=1, failure_kind=k)
            self.assertEqual((x['action'], pick(x), x['preserve_state'], x['attempts_reset'], x['escalated']), ('retry_same_model_preserve_state', ('sonnet','medium'), True, False, False))
            self.assertIn('non_model_failure', x['reasons'])
        # Orca execution retries: up to 3 runs in total, then stop without escalating the model
        x=r(host='orca', task_type='feature', failures=2, failure_kind='environment'); self.assertEqual(x['action'], 'retry_same_model_preserve_state')
        x=r(host='orca', task_type='feature', failures=3, failure_kind='tool')
        self.assertEqual((x['action'], x['level'], x['escalated'], x['orca_worker_args']), ('handoff_to_lead', 2, False, []))

    def test_worker_args(self):
        self.assertEqual(r(host='orca', task_type='docs')['orca_worker_args'], ['--agent','codex','--model','gpt-6-luna','--effort','medium'])
        self.assertEqual(r(host='claude', role='lookup')['orca_worker_args'], ['--agent','claude','--model','claude-haiku-4-5-20251001'])

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
        bad(lambda c: c['roles']['lookup'].update(claude=['haiku','high']))
        bad(lambda c: c.pop('fallbacks'))
        bad(lambda c: c.update(schema=2))

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

if __name__=='__main__': unittest.main()
