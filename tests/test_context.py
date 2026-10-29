"""Origin is an independent required predicate, never inferred from hints."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

class ContextTests(unittest.TestCase):
    def evidence(self, **kw):
        from ai_policy.context import Evidence
        return replace(Evidence(hints_present=True, registered=True, runtime_reachable=True,
            terminal_live=True, workspace_match=True, runtime_match=True, host_match=True,
            invocation_bound=True), **kw)

    def test_bound_managed_before_task(self):
        from ai_policy.context import decide, render_context
        d=decide(self.evidence(), True)
        self.assertEqual((d['decision'],d['reason']),('active','verified'))
        self.assertEqual(render_context(d,b'common once'),b'common once')
        self.assertNotIn('task',json.dumps(d).lower())

    def test_detection_denials_D02_D16(self):
        from ai_policy.context import decide, Evidence, render_context
        cases=[('origin_unverified',dict(invocation_bound=False)),
               ('workspace_mismatch',dict(workspace_match=False)),
               ('terminal_not_live',dict(terminal_live=False)),
               ('runtime_changed',dict(runtime_match=False)),
               ('host_mismatch',dict(host_match=False)),
               ('runtime_unavailable',dict(runtime_reachable=False)),
               ('schema_invalid',dict(error='schema_invalid'))]
        for reason,kw in cases:
            with self.subTest(reason=reason):
                d=decide(self.evidence(**kw),True)
                self.assertEqual((d['decision'],d['reason']),('ambiguous',reason))
                self.assertEqual(render_context(d,b'must not leak'),b'')
        self.assertEqual(decide(Evidence(),True)['decision'],'inactive')
        self.assertEqual(decide(Evidence(registered=True),True)['decision'],'ambiguous')
        self.assertEqual(decide(self.evidence(),False)['reason'],'bundle_invalid')

    def test_paths_component_containment_and_folder(self):
        from ai_policy.context import contains
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'folder';root.mkdir();(root/'child').mkdir()
            link=Path(t)/'alias';link.symlink_to(root,target_is_directory=True)
            self.assertTrue(contains(root,link/'child'))
            self.assertFalse(contains(root,Path(t)/'folder-other'))
            self.assertFalse(contains(root/'child',root))

    def test_no_secret_env_reads(self):
        from ai_policy.context import environment_hints, ALLOWLIST
        class Spy:
            def get(self,k,default=None):
                if k not in ALLOWLIST: raise AssertionError('forbidden env access')
                return 'private sentinel'
            def __iter__(self): raise AssertionError('env iteration')
        self.assertEqual(set(environment_hints(Spy())),set(ALLOWLIST))

    def test_current_provider_never_attests_even_copied_identifiers(self):
        from ai_policy.context import collect_runtime, decide, ALLOWLIST
        replies=[{'ok':True,'result':{},'_meta':{'runtimeId':'r'}},
                 {'ok':True,'result':{'workspaceId':'w','worktreeId':'t','path':'/fixture'},'_meta':{'runtimeId':'r'}},
                 {'ok':True,'result':{'terminal':{'handle':'h','workspaceId':'w','worktreeId':'t','tabId':'b','connected':True,'orphaned':False}},'_meta':{'runtimeId':'r'}}]
        calls=[]
        def run(argv,cwd,timeout):
            calls.append(argv)
            return replies[len(calls)-1]
        hints=dict(zip(ALLOWLIST,['h','w','t','r','inc','b']))
        e=collect_runtime(Path('/fixture'),hints,run,orca='/fixed/orca')
        self.assertFalse(e.invocation_bound)
        self.assertNotEqual(decide(e,True)['decision'],'active')
        self.assertEqual(calls,[['/fixed/orca','status','--json'],['/fixed/orca','worktree','current','--json'],['/fixed/orca','terminal','show','--terminal','h','--json']])
        self.assertNotIn('private sentinel',json.dumps(decide(e,True)))

    def test_provider_malformed_restart_and_failure_sanitized(self):
        from ai_policy.context import collect_runtime, decide
        for reply in ({'ok':True,'result':'raw private preview'}, {'ok':True,'result':{},'_meta':{}}):
            e=collect_runtime(Path('/fixture'),{'ORCA_TERMINAL_HANDLE':'h'},lambda *args:reply,orca='/fixed/orca')
            d=decide(e,True)
            self.assertEqual(d['decision'],'ambiguous')
            self.assertNotIn('preview',json.dumps(d))
        def down(*args): raise OSError('private secret')
        self.assertEqual(collect_runtime(Path('/fixture'),{'ORCA_TERMINAL_HANDLE':'h'},down,orca='/fixed/orca').error,'runtime_unavailable')

    def test_actual_supported_shape_without_workspace_id(self):
        from ai_policy.context import collect_runtime,decide
        replies=[{'runtime':{'reachable':True}},
                 {'worktree':{'id':'tree','path':'/fixture','repoId':'repo','hostId':'host'}},
                 {'terminal':{'handle':'h','worktreeId':'tree','worktreePath':'/fixture','tabId':'tab',
                              'executionHostId':'host','connected':True,'orphaned':False}}]
        def run(*args):return {'ok':True,'result':replies.pop(0),'_meta':{'runtimeId':'r'}}
        e=collect_runtime(Path('/fixture'),{'ORCA_TERMINAL_HANDLE':'h','ORCA_WORKTREE_ID':'tree','ORCA_TAB_ID':'tab'},run,orca='/fixed/orca')
        self.assertTrue(e.workspace_match)
        self.assertTrue(e.terminal_live)
        self.assertEqual(decide(e,True)['reason'],'origin_unverified')

    def test_restart_and_unregistered_runtime_reply(self):
        from ai_policy.context import collect_runtime,decide
        calls=[]
        def restart(argv,*args):
            calls.append(argv)
            return {'ok':True,'result':{},'_meta':{'runtimeId':'first' if len(calls)==1 else 'second'}}
        e=collect_runtime(Path('/fixture'),{'ORCA_TERMINAL_HANDLE':'h'},restart,orca='/fixed/orca')
        self.assertEqual(decide(e,True)['reason'],'runtime_changed')
        self.assertEqual(len(calls),2)
        def unregistered(argv,*args):
            if argv[1]=='status':return {'ok':True,'result':{},'_meta':{'runtimeId':'r'}}
            return {'ok':False,'error':{'code':'selector_not_found'},'_meta':{'runtimeId':'r'}}
        e=collect_runtime(Path('/fixture'),{},unregistered,orca='/fixed/orca')
        self.assertEqual(decide(e,False)['decision'],'inactive')

    def test_bounded_real_runner(self):
        from ai_policy.context import bounded_query
        from ai_policy.bundle import PolicyError
        with tempfile.TemporaryDirectory() as t:
            for code,reason in [('import time;time.sleep(2)','query_timeout'),
                                ('import sys;sys.stdout.write("x"*1100000)','query_overflow'),
                                ('print("not json private")','query_invalid_json')]:
                with self.subTest(reason=reason),self.assertRaisesRegex(PolicyError,reason):
                    bounded_query([sys.executable,'-I','-c',code],Path(t),0.15)

if __name__ == '__main__': unittest.main()
