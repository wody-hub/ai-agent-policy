"""Paseo managed-context evidence: parent assignment message + parent label; env hint alone never counts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PaseoContextTests(unittest.TestCase):
    def ev(self, **kw):
        from ai_policy.context import PaseoEvidence
        base=dict(hints_present=True, assignment_message=True, parent_label=True, workspace_match=True)
        base.update(kw); return PaseoEvidence(**base)

    def test_both_evidence_kinds_and_valid_bundle_activate(self):
        from ai_policy.context import decide_paseo, render_context
        d=decide_paseo(self.ev(), True, 'a'*64)
        self.assertEqual((d['decision'], d['reason'], d['policy_emitted']), ('active', 'verified', True))
        self.assertEqual(d['flavor'], 'paseo'); self.assertEqual(d['provenance']['bundle_sha256'], 'a'*64)
        self.assertEqual(render_context(d, b'paseo common'), b'paseo common')
        # Environment hint is not required once both facts are attested.
        self.assertEqual(decide_paseo(self.ev(hints_present=False), True)['decision'], 'active')

    def test_environment_hint_alone_is_not_evidence(self):
        from ai_policy.context import decide_paseo, PaseoEvidence, render_context
        d=decide_paseo(PaseoEvidence(hints_present=True), True)
        self.assertEqual((d['decision'], d['reason'], d['policy_emitted']), ('ambiguous', 'origin_unverified', False))
        self.assertEqual(render_context(d, b'x'), b'')
        for kw in (dict(assignment_message=False, parent_label=False), dict(assignment_message=None, parent_label=None)):
            self.assertEqual(decide_paseo(self.ev(**kw), True)['decision'], 'ambiguous')

    def test_single_evidence_kind_is_not_enough(self):
        from ai_policy.context import decide_paseo
        d=decide_paseo(self.ev(parent_label=None), True); self.assertEqual((d['decision'], d['reason']), ('ambiguous', 'parent_label_missing'))
        d=decide_paseo(self.ev(assignment_message=None), True); self.assertEqual((d['decision'], d['reason']), ('ambiguous', 'assignment_message_missing'))
        d=decide_paseo(self.ev(hints_present=False, parent_label=True, assignment_message=None), True)
        self.assertEqual((d['decision'], d['reason']), ('ambiguous', 'assignment_message_missing'))

    def test_denials_fail_closed(self):
        from ai_policy.context import decide_paseo, PaseoEvidence
        cases=[('bundle_invalid', self.ev(), False), ('workspace_mismatch', self.ev(workspace_match=False), True),
               ('daemon_unreachable', self.ev(error='daemon_unreachable'), True)]
        for reason, ev, valid in cases:
            with self.subTest(reason=reason):
                d=decide_paseo(ev, valid)
                self.assertEqual((d['decision'], d['reason'], d['policy_emitted']), ('ambiguous', reason, False))
        d=decide_paseo(PaseoEvidence(), True)
        self.assertEqual((d['decision'], d['reason']), ('inactive', 'not_managed'))
        d=decide_paseo(PaseoEvidence(), False)
        self.assertEqual(d['decision'], 'inactive')   # nothing claimed: an invalid bundle changes nothing

    def test_subprocess_view_never_activates_and_ignores_other_variables(self):
        from ai_policy.context import collect_paseo_runtime, decide_paseo, paseo_hints, environment_hints
        self.assertEqual(paseo_hints({'PASEO_AGENT_ID': ''}), {})
        self.assertEqual(paseo_hints({'OTHER': 'x'}), {})
        e=collect_paseo_runtime({'PASEO_AGENT_ID': 'agent-1'})
        self.assertTrue(e.hints_present); self.assertIsNone(e.assignment_message); self.assertIsNone(e.parent_label)
        self.assertEqual(decide_paseo(e, True)['decision'], 'ambiguous')
        self.assertEqual(decide_paseo(collect_paseo_runtime({}), True)['decision'], 'inactive')
        # The Orca path does not read the Paseo variable, and Orca evidence is not Paseo evidence.
        self.assertEqual(environment_hints({'PASEO_AGENT_ID': 'agent-1'}), {})

    def test_orca_decision_unchanged(self):
        from ai_policy.context import decide, Evidence
        d=decide(Evidence(hints_present=True, registered=True, runtime_reachable=True, terminal_live=True,
                          workspace_match=True, runtime_match=True, host_match=True, invocation_bound=False), True)
        self.assertEqual((d['decision'], d['reason']), ('ambiguous', 'origin_unverified')); self.assertNotIn('flavor', d)

    def test_cli_flavor_paseo_never_active_and_emits_nothing(self):
        import os
        env={**os.environ, 'PASEO_AGENT_ID': 'agent-1'}
        with tempfile.TemporaryDirectory() as d:
            home=Path(d).resolve()
            r=subprocess.run([sys.executable,'-B','-m','ai_policy','detect','--home',str(home),'--flavor','paseo'],cwd=ROOT,env=env,capture_output=True,timeout=25)
            value=json.loads(r.stdout)
            self.assertEqual((r.returncode, value['decision'], value['policy_emitted'], value['flavor']), (20, 'ambiguous', False, 'paseo'))
            r=subprocess.run([sys.executable,'-B','-m','ai_policy','context','--home',str(home),'--flavor','paseo'],cwd=ROOT,env=env,capture_output=True,timeout=25)
            self.assertEqual((r.returncode, r.stdout), (20, b''))
            env.pop('PASEO_AGENT_ID')
            r=subprocess.run([sys.executable,'-B','-m','ai_policy','detect','--home',str(home),'--flavor','paseo'],cwd=ROOT,env=env,capture_output=True,timeout=25)
            self.assertEqual((r.returncode, json.loads(r.stdout)['decision']), (10, 'inactive'))
            self.assertEqual(list(home.iterdir()), [])   # detection writes nothing

if __name__=='__main__': unittest.main()
