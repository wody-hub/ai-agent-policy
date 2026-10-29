"""Synthetic-home preservation, conflict refusal and interrupted-operation evidence."""
import base64
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'policy/bundle.json'
REL=Path('.config/ai-agent-policy/orca')

def snapshot(root, timestamps=False):
    return {str(p.relative_to(root)):('dir' if p.is_dir() else 'file',stat.S_IMODE(p.stat().st_mode),
             p.read_bytes() if p.is_file() else None,*((p.stat().st_mtime_ns,) if timestamps else ()))
            for p in root.rglob('*')}

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai-policy-test-')
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name).resolve()
        self.codex=self.home/'.codex/AGENTS.md'; self.claude=self.home/'.claude/CLAUDE.md'
        self.codex.parent.mkdir();self.claude.parent.mkdir()
        self.codex.write_bytes('개인 노트\r\n'.encode())
        self.claude.write_bytes(b'<!-- model-routing:begin -->\r\nPersonal model\r\n<!-- model-routing:end -->\r\n')
        self.codex.chmod(0o640);self.claude.chmod(0o640)
        self.initial={p:(p.read_bytes(),stat.S_IMODE(p.stat().st_mode)) for p in (self.codex,self.claude)}

    def runop(self,operation='install',backup=None,**kw):
        from ai_policy.install import plan,apply
        p=plan(operation,self.home,BUNDLE if operation=='install' else None,backup)
        return apply(p,p.sha256,**kw)

    def assert_initial(self):
        for p,(data,mode) in self.initial.items():
            self.assertEqual(p.read_bytes(),data); self.assertEqual(stat.S_IMODE(p.stat().st_mode),mode)

    def test_clean_install_roundtrip_I01_I04_I20(self):
        from ai_policy.install import check
        r=self.runop();c=check(self.home)
        self.assertTrue(c['files_valid']);self.assertTrue(c['ownership_valid'])
        self.assertFalse(c['hook_configured'])
        for k in ('load_verified','origin_verified','enforcement_verified'): self.assertIsNone(c[k])
        for p,(data,mode) in self.initial.items():
            self.assertTrue(p.read_bytes().startswith(data));self.assertEqual(stat.S_IMODE(p.stat().st_mode),mode)
        common=list((self.home/REL/'generations').rglob('orca-common.md'))
        self.assertEqual(len(common),1)
        self.runop('restore',r['backup_id']);self.assert_initial()
        self.assertEqual(check(self.home)['state'],'absent')
        self.assertTrue((self.home/REL/'backups'/r['backup_id']).is_dir())

    def test_noop_and_dry_run_I02_I03(self):
        from ai_policy.install import plan,apply
        before=snapshot(self.home,True)
        p=plan('install',self.home,BUNDLE)
        self.assertEqual(snapshot(self.home,True),before)
        apply(p,p.sha256); before=snapshot(self.home,True)
        p=plan('install',self.home,BUNDLE)
        self.assertEqual(p.public()['changes'],[])
        self.assertFalse(apply(p,p.sha256)['changed'])
        self.assertEqual(snapshot(self.home,True),before)

    def test_bad_markers_I05_I06(self):
        from ai_policy.install import plan,BEGIN,END
        from ai_policy.bundle import PolicyError
        for block in (BEGIN,END,END+BEGIN,BEGIN+BEGIN+END,BEGIN+END+BEGIN+END,
                      b'<!-- ai-agent-policy:orca-adapter:begin schema=9 -->\n'+END,BEGIN+b'foreign\n'+END):
            self.codex.write_bytes(block);before=snapshot(self.home,True)
            with self.subTest(block=block),self.assertRaises(PolicyError):plan('install',self.home,BUNDLE)
            self.assertEqual(snapshot(self.home,True),before)

    def test_stale_plan_and_mode_I08(self):
        from ai_policy.install import plan,apply
        from ai_policy.bundle import PolicyError
        p=plan('install',self.home,BUNDLE);self.codex.write_bytes(b'Concurrent edit')
        before=snapshot(self.home,True)
        with self.assertRaisesRegex(PolicyError,'stale_plan'):apply(p,p.sha256)
        self.assertEqual(snapshot(self.home,True),before)
        p=plan('install',self.home,BUNDLE);self.codex.chmod(0o600)
        with self.assertRaisesRegex(PolicyError,'stale_plan'):apply(p,p.sha256)

    def test_drift_I07(self):
        from ai_policy.install import plan,check
        from ai_policy.bundle import PolicyError
        first=self.runop()
        self.codex.write_bytes(self.codex.read_bytes().replace(b'Only when',b'Always use'))
        before=snapshot(self.home,True)
        self.assertTrue(check(self.home)['drift'])
        for op,b in [('install',None),('restore',first['backup_id']),('remove',None)]:
            with self.assertRaises(PolicyError):plan(op,self.home,BUNDLE if op=='install' else None,b)
        self.assertEqual(snapshot(self.home,True),before)

    def test_remove_restore_roundtrip_I14(self):
        installed=self.runop();current=(self.codex.read_bytes(),self.claude.read_bytes())
        removed=self.runop('remove');self.assert_initial()
        self.runop('restore',removed['backup_id'])
        self.assertEqual((self.codex.read_bytes(),self.claude.read_bytes()),current)
        self.runop('restore',installed['backup_id']);self.assert_initial()

    def test_restore_preserves_later_unmanaged_I15_I16(self):
        r=self.runop();extra=b'\nLater personal note\n'
        self.codex.write_bytes(self.codex.read_bytes()+extra)
        self.runop('restore',r['backup_id'])
        self.assertEqual(self.codex.read_bytes(),self.initial[self.codex][0]+extra)
        self.codex.unlink();self.claude.unlink();r=self.runop()
        self.codex.write_bytes(self.codex.read_bytes()+extra)
        self.runop('restore',r['backup_id'])
        self.assertEqual(self.codex.read_bytes(),extra)
        self.assertFalse(self.claude.exists())

    def test_backup_corruption_and_traversal_I11(self):
        from ai_policy.install import plan
        from ai_policy.bundle import PolicyError
        r=self.runop();b=self.home/REL/'backups'/r['backup_id']/'backup.json'
        b.write_bytes(b.read_bytes()+b'corruption');before=snapshot(self.home,True)
        for ident in (r['backup_id'],'../outside','/absolute'):
            with self.assertRaises(PolicyError):plan('restore',self.home,None,ident)
            self.assertEqual(snapshot(self.home,True),before)

    def test_symlink_and_unsafe_mode_I12(self):
        from ai_policy.install import plan
        from ai_policy.bundle import PolicyError
        other=self.home/'other';other.write_bytes(b'untouched')
        self.codex.unlink();self.codex.symlink_to(other)
        with self.assertRaises(PolicyError):plan('install',self.home,BUNDLE)
        self.assertEqual(other.read_bytes(),b'untouched')
        self.codex.unlink();self.codex.write_bytes(b'safe');self.codex.chmod(0o666)
        with self.assertRaises(PolicyError):plan('install',self.home,BUNDLE)
        self.codex.chmod(0o600);self.codex.parent.chmod(0o777)
        with self.assertRaises(PolicyError):plan('install',self.home,BUNDLE)
        self.codex.parent.chmod(0o700)

    def test_override_and_concurrency_I13_I19(self):
        from ai_policy.install import plan,apply,check
        from ai_policy.bundle import PolicyError
        override=self.home/'.codex/AGENTS.override.md';override.write_bytes(b'personal override')
        self.runop();self.assertTrue(check(self.home)['codex_shadowed'])
        self.assertEqual(override.read_bytes(),b'personal override')
        (self.home/REL/'writer.lock').write_bytes(b'stale')
        p=plan('remove',self.home)
        before=snapshot(self.home,True)
        with self.assertRaisesRegex(PolicyError,'writer_locked'):apply(p,p.sha256)
        self.assertEqual(snapshot(self.home,True),before)
        self.assertTrue((self.home/REL/'writer.lock').exists())

    def test_failure_rolls_back_and_journal_fails_closed_I09_I10(self):
        from ai_policy.install import plan,apply,check
        from ai_policy.bundle import PolicyError
        # Failure at a target after generation writes exercises real partial replacement.
        p=plan('install',self.home,BUNDLE)
        def fail(phase,path):
            if phase=='before_replace' and path=='.claude/CLAUDE.md': raise OSError('injected')
        with self.assertRaisesRegex(PolicyError,'operation_failed'):apply(p,p.sha256,fs_event=fail)
        self.assert_initial();self.assertEqual(check(self.home)['state'],'absent')
        # A simulated process death leaves its durable journal; startup never recovers.
        class Crash(BaseException):pass
        def crash(phase,path):
            if phase=='before_replace' and path=='.claude/CLAUDE.md': raise Crash()
        p=plan('install',self.home,BUNDLE)
        with self.assertRaises(Crash):apply(p,p.sha256,fs_event=crash)
        before=snapshot(self.home,True);c=check(self.home)
        self.assertTrue(c['partial']);self.assertFalse(c['files_valid'])
        self.assertEqual(snapshot(self.home,True),before)
        with self.assertRaisesRegex(PolicyError,'recovery_required'):plan('install',self.home,BUNDLE)

    def test_failure_preserves_concurrent_edit_I09(self):
        from ai_policy.install import plan,apply,check
        from ai_policy.bundle import PolicyError
        p=plan('install',self.home,BUNDLE)
        def conflict(phase,path):
            if phase=='before_replace' and path=='.claude/CLAUDE.md':
                self.codex.write_bytes(b'Concurrent content must survive')
                raise OSError('injected')
        with self.assertRaisesRegex(PolicyError,'recovery_required'):apply(p,p.sha256,fs_event=conflict)
        self.assertEqual(self.codex.read_bytes(),b'Concurrent content must survive')
        self.assertTrue(check(self.home)['partial'])

    def test_offline_entrypoint_ignores_hostile_cwd_and_pythonpath_I17_I18_I21(self):
        from ai_policy.install import check
        self.runop();hostile=self.home/'hostile';hostile.mkdir()
        sentinel=self.home/'executed'
        (hostile/'ai_policy.py').write_text('raise RuntimeError("hostile import")')
        (hostile/'orca').write_text('#!/bin/sh\ntouch '+str(sentinel)+'\n');(hostile/'orca').chmod(0o700)
        entry=self.home/REL/'entrypoint.py'
        env={'PATH':str(hostile),'PYTHONPATH':str(hostile)}
        # All source modules are inaccessible to the child through cwd or module path.
        p=subprocess.run([str(entry),'check','--home',str(self.home)],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr.decode());self.assertTrue(json.loads(p.stdout)['files_valid'])
        p=subprocess.run([str(entry),'context','--mode','auto'],cwd=hostile,env=env,capture_output=True,timeout=20)
        self.assertIn(p.returncode,(10,20));self.assertEqual(p.stdout,b'');self.assertFalse(sentinel.exists())
        self.assertFalse((self.home/'.claude/settings.json').exists())
        self.assertIsNone(check(self.home)['enforcement_verified'])

    def test_all_replace_and_fsync_boundaries_rollback(self):
        from ai_policy.install import plan,apply,check
        from ai_policy.bundle import PolicyError
        # A first install has immutable generation files, both adapters, entrypoint,
        # manifest and the final selector. Every mutation boundary is exercised.
        for phase in ('before_replace','before_fsync','after_replace','before_dir_fsync'):
            for name in [c['path'] for c in plan('install',self.home,BUNDLE).changes]:
                with self.subTest(phase=phase,path=name),tempfile.TemporaryDirectory() as d:
                    home=Path(d).resolve()
                    for src in (self.codex,self.claude):
                        dst=home/src.relative_to(self.home);dst.parent.mkdir();dst.write_bytes(src.read_bytes());dst.chmod(0o640)
                    p=plan('install',home,BUNDLE)
                    def fail(event,path):
                        if event==phase and path==name:raise OSError('injected boundary')
                    with self.assertRaises(PolicyError):apply(p,p.sha256,fs_event=fail)
                    for src in (self.codex,self.claude):
                        dst=home/src.relative_to(self.home)
                        self.assertEqual(dst.read_bytes(),src.read_bytes())
                        self.assertEqual(stat.S_IMODE(dst.stat().st_mode),0o640)
                    self.assertEqual(check(home)['state'],'absent')

    def test_symlinked_component_journal_and_unowned_markers_refused(self):
        from ai_policy.install import plan,check,BEGIN,END
        from ai_policy.bundle import PolicyError
        self.codex.write_bytes(BEGIN+b'\nforeign\n'+END)
        self.assertFalse(check(self.home)['ownership_valid'])
        with self.assertRaises(PolicyError):plan('install',self.home,BUNDLE)
        self.codex.write_bytes(self.initial[self.codex][0]);self.runop()
        (self.home/REL/'transaction.json').symlink_to(self.home/'absent')
        self.assertFalse(check(self.home)['files_valid'])
        with self.assertRaises(PolicyError):plan('remove',self.home)

    def test_same_target_race_is_preserved(self):
        from ai_policy.install import plan,apply
        from ai_policy.bundle import PolicyError
        p=plan('install',self.home,BUNDLE)
        def race(phase,path):
            if phase=='before_replace' and path=='.codex/AGENTS.md':self.codex.write_bytes(b'Last-moment user edit')
        with self.assertRaisesRegex(PolicyError,'recovery_required'):apply(p,p.sha256,fs_event=race)
        self.assertEqual(self.codex.read_bytes(),b'Last-moment user edit')

    def test_private_exact_backups(self):
        self.runop()
        backups=self.home/REL/'backups'
        for p in backups.rglob('*'):
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700 if p.is_dir() else 0o600)

    def test_entrypoint_after_source_copy_deleted(self):
        source=self.home/'source-copy';source.mkdir()
        for name in ('ai_policy','policy'):
            shutil.copytree(ROOT/name,source/name,ignore=shutil.ignore_patterns('__pycache__'))
        args=[sys.executable,'-m','ai_policy','install','--home',str(self.home),'--bundle',str(source/'policy/bundle.json')]
        r=subprocess.run(args+['--dry-run'],cwd=source,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode());h=json.loads(r.stdout)['plan_sha256']
        r=subprocess.run(args+['--plan-sha256',h],cwd=source,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode())
        shutil.rmtree(source) # only this test-created copy; real repository untouched
        hostile=self.home/'hostile-source-test';hostile.mkdir()
        (hostile/'ai_policy.py').write_text('raise RuntimeError("foreign")')
        (hostile/'sitecustomize.py').write_text('raise RuntimeError("foreign")')
        entry=self.home/REL/'entrypoint.py'
        env={'PATH':str(hostile),'PYTHONPATH':str(hostile)}
        for args in (['check','--home',str(self.home)],['guide','--explicit-request']):
            r=subprocess.run([str(entry),*args],cwd=hostile,env=env,capture_output=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr.decode())
        self.assertFalse(source.exists())
        before=snapshot(self.home,True)
        r=subprocess.run([str(entry),'remove','--home',str(self.home),'--dry-run'],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode());h=json.loads(r.stdout)['plan_sha256']
        self.assertEqual(snapshot(self.home,True),before)
        r=subprocess.run([str(entry),'remove','--home',str(self.home),'--plan-sha256',h],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode());backup=json.loads(r.stdout)['backup_id']
        self.assertTrue(entry.is_file(),'removal must retain the offline restoration entrypoint')
        r=subprocess.run([str(entry),'check','--home',str(self.home)],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,10,r.stderr.decode());self.assertEqual(json.loads(r.stdout)['state'],'absent')
        r=subprocess.run([str(entry),'restore','--home',str(self.home),'--backup',backup,'--dry-run'],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode());h=json.loads(r.stdout)['plan_sha256']
        r=subprocess.run([str(entry),'restore','--home',str(self.home),'--backup',backup,'--plan-sha256',h],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode())
        r=subprocess.run([str(entry),'check','--home',str(self.home)],cwd=hostile,env=env,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr.decode())
        self.assertEqual(list((self.home/REL/'generations').rglob('*.pyc')),[])

    def test_drifted_generation_manifest_and_partial_context(self):
        from ai_policy.install import check,plan
        from ai_policy.bundle import PolicyError
        self.runop()
        common=next((self.home/REL/'generations').rglob('orca-common.md'))
        common.write_bytes(b'foreign policy')
        self.assertTrue(check(self.home)['drift'])
        before=snapshot(self.home,True)
        with self.assertRaises(PolicyError):plan('remove',self.home)
        self.assertEqual(snapshot(self.home,True),before)
        r=subprocess.run([sys.executable,'-m','ai_policy','context','--home',str(self.home)],cwd=ROOT,capture_output=True,timeout=10)
        self.assertEqual(r.returncode,30);self.assertEqual(r.stdout,b'')

if __name__=='__main__':unittest.main()
