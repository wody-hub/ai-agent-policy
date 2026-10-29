"""Review regressions exercise final mutation and interpreter trust boundaries."""
import importlib.util
import json
from pathlib import Path
import py_compile
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import ai_policy.install as m

B=Path(__file__).resolve().parents[1]/'policy/bundle.json'

def op(home,kind='install',backup=None):
    p=m.plan(kind,home,B if kind=='install' else None,backup)
    return m.apply(p,p.sha256)

class ReviewRegressions(unittest.TestCase):
    def test_poisoned_unchecked_cache_never_executes(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();op(h)
            gen=next((h/m.ROOT/'generations').iterdir())
            cache=Path(importlib.util.cache_from_source(str(gen/'ai_policy/__main__.py')))
            cache.parent.mkdir();fake=h/'cache-source.py';sentinel=h/'executed'
            fake.write_text('from pathlib import Path\nPath('+repr(str(sentinel))+').touch()\nraise SystemExit(0)\n')
            py_compile.compile(str(fake),cfile=str(cache),doraise=True,invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            r=subprocess.run([str(h/m.ENTRY),'check','--home',str(h)],capture_output=True,timeout=10)
            self.assertFalse(sentinel.exists(),'unverified bytecode executed')
            self.assertEqual(r.returncode,0,r.stderr.decode());self.assertTrue(json.loads(r.stdout)['files_valid'])

    def test_restore_later_personal_mode_and_exact_crlf_inverse(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();op(h);removed=op(h,'remove')
            f=h/'.codex/AGENTS.md';f.write_bytes(b'new personal text\n');f.chmod(0o640)
            from tests.test_install import snapshot
            before=snapshot(h,True)
            with self.assertRaisesRegex(m.PolicyError,'mode_conflict'):m.plan('restore',h,None,removed['backup_id'])
            self.assertEqual(snapshot(h,True),before)
            self.assertEqual(f.read_bytes(),b'new personal text\n')
            self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o640)
            self.assertEqual(m.check(h)['state'],'absent')
            self.assertFalse(op(h,'remove')['changed'])

    def test_exact_crlf_inverse_with_later_text(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir()
            f.write_bytes(b'personal\r\nlast line');op(h)
            f.write_bytes(f.read_bytes()+b'new note\r\n');op(h,'remove')
            self.assertEqual(f.read_bytes(),b'personal\r\nlast linenew note\r\n')

    def test_final_journal_fsync_failure_retains_recovery_gate(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'original\n')
            p=m.plan('install',h,B);real=m.sync_dir;fired=[False]
            def sync(path):
                if Path(path)==h/m.ROOT and not (h/m.ROOT/'transaction.json').exists() and (h/m.CURRENT).exists() and not fired[0]:
                    fired[0]=True;f.write_bytes(b'concurrent unmanaged bytes\n');raise OSError('final commit fsync')
                return real(path)
            with patch.object(m,'sync_dir',side_effect=sync),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
            self.assertEqual(f.read_bytes(),b'concurrent unmanaged bytes\n')
            self.assertTrue(m.check(h)['partial'])
            with self.assertRaises(m.PolicyError):m.plan('install',h,B)

if __name__=='__main__':unittest.main()

class MutationBoundaryRegressions(unittest.TestCase):
    def replace_boundary(self, action):
        # During RED this targets the old actual replacement; GREEN targets the
        # supported native exchange that is the new final mutation boundary.
        if hasattr(m,'atomic_exchange'):
            return patch.object(m,'atomic_exchange',side_effect=action),m.atomic_exchange
        return patch.object(m.os,'replace',side_effect=action),m.os.replace

    def test_final_replace_preserves_inplace_and_atomic_save(self):
        for atomic_save in (False,True):
            with self.subTest(atomic_save=atomic_save),tempfile.TemporaryDirectory() as t:
                h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'baseline\n')
                p=m.plan('install',h,B);fired=[False];real=[None];save=m.os.replace
                def race(src,dst):
                    if Path(dst)==f and not fired[0]:
                        fired[0]=True
                        if atomic_save:
                            temp=h/'external-save';temp.write_bytes(b'latest unmanaged\n');save(temp,f)
                        else:f.write_bytes(b'latest unmanaged\n')
                    return real[0](src,dst)
                patcher,real[0]=self.replace_boundary(race)
                with patcher,self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
                self.assertTrue(fired[0]);self.assertEqual(f.read_bytes(),b'latest unmanaged\n')
                self.assertTrue(m.check(h)['partial'])

    def test_absent_target_creation_is_noclobber(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';p=m.plan('install',h,B);fired=[False]
            is_native=hasattr(m,'atomic_exchange');has_create=hasattr(m,'atomic_create')
            real=m.atomic_create if has_create else m.os.link if is_native else m.os.replace
            def race(src,dst,*args,**kwargs):
                if Path(dst)==f and not fired[0]:fired[0]=True;f.write_bytes(b'new personal file\n')
                return real(src,dst,*args,**kwargs)
            with patch.object(m if has_create else m.os,'atomic_create' if has_create else 'link' if is_native else 'replace',side_effect=race),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
            self.assertTrue(fired[0]);self.assertEqual(f.read_bytes(),b'new personal file\n')

    def test_final_deletion_preserves_unexpected_inode(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();op(h);f=h/'.codex/AGENTS.md';p=m.plan('remove',h)
            native=hasattr(m,'atomic_move');real=m.atomic_move if native else m.os.unlink;fired=[False]
            def race(src,*args,**kwargs):
                if Path(src)==f and not fired[0]:fired[0]=True;f.write_bytes(b'late personal deletion race\n')
                return real(src,*args,**kwargs)
            target=m if native else m.os
            with patch.object(target,'atomic_move' if native else 'unlink',side_effect=race),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
            self.assertTrue(fired[0]);self.assertEqual(f.read_bytes(),b'late personal deletion race\n')

    def test_rollback_final_boundary_preserves_edit(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'baseline\n')
            p=m.plan('install',h,B);calls=[0];real=[None]
            def race(src,dst):
                if Path(dst)==f:
                    calls[0]+=1
                    if calls[0]==2:f.write_bytes(b'personal edit during rollback\n')
                return real[0](src,dst)
            def fail(phase,path):
                if phase=='before_replace' and path=='.claude/CLAUDE.md':raise OSError('trigger rollback')
            patcher,real[0]=self.replace_boundary(race)
            with patcher,self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256,fs_event=fail)
            self.assertGreaterEqual(calls[0],2);self.assertEqual(f.read_bytes(),b'personal edit during rollback\n')
            self.assertTrue(m.check(h)['partial'])

class RecoveryBoundaryRegressions(unittest.TestCase):
    def test_lock_cleanup_failures_recreate_gate(self):
        for boundary in ('before_lock_cleanup','after_lock_cleanup','lock_cleanup_fsync'):
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory() as t:
                h=Path(t).resolve();p=m.plan('install',h,B);real=m.sync_dir;fired=[False]
                def event(phase,name):
                    if phase==boundary and not fired[0]:fired[0]=True;raise OSError('lock cleanup')
                def sync(path):
                    if boundary=='lock_cleanup_fsync' and Path(path)==h/m.ROOT and not (h/m.ROOT/'writer.lock').exists() and not (h/m.ROOT/'transaction.json').exists() and (h/m.CURRENT).exists() and not fired[0]:
                        fired[0]=True;raise OSError('lock cleanup fsync')
                    return real(path)
                with patch.object(m,'sync_dir',side_effect=sync),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256,fs_event=event)
                self.assertTrue(fired[0]);self.assertTrue(m.check(h)['partial'])
                with self.assertRaises(m.PolicyError):m.plan('install',h,B)
                r=subprocess.run([str(h/m.ENTRY),'context'],capture_output=True,timeout=10)
                self.assertEqual(r.stdout,b'');self.assertNotEqual(r.returncode,0)

    def test_open_inode_write_and_undo_boundary_versions_retained(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'baseline')
            p=m.plan('install',h,B);real=m.atomic_exchange;count=[0]
            with f.open('r+b') as held:
                def exchange(src,dst):
                    if Path(dst)==f:
                        count[0]+=1
                        if count[0]==2:f.write_bytes(b'late edit during undo')
                    real(src,dst)
                    if Path(dst)==f and count[0]==1:
                        held.seek(0);held.write(b'open-inode concurrent write');held.truncate();held.flush()
                with patch.object(m,'atomic_exchange',side_effect=exchange),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
            versions=[q.read_bytes() for q in (h/m.ROOT/'retained').rglob('*') if q.is_file()]
            self.assertEqual(f.read_bytes(),b'open-inode concurrent write')
            self.assertIn(b'late edit during undo',versions)
            self.assertTrue(m.check(h)['partial'])
            self.assertTrue(any(q.name=='metadata.json' for q in (h/m.ROOT/'retained').rglob('*')))

    def test_unsupported_native_capability_has_zero_dry_run_writes(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve()
            with patch.object(m,'_native_functions',side_effect=m.PolicyError('atomic_mutation_unsupported')):
                with self.assertRaisesRegex(m.PolicyError,'atomic_mutation_unsupported'):m.plan('install',h,B)
            self.assertEqual(list(h.iterdir()),[])

class MutationOwnershipRegressions(unittest.TestCase):
    def test_failed_delete_never_recreates_external_absence(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();op(h);f=h/'.codex/AGENTS.md';p=m.plan('remove',h)
            real=m.atomic_move;fired=[False]
            def remove_first(src,dst):
                if Path(src)==f and not fired[0]:fired[0]=True;f.unlink()
                return real(src,dst)
            with patch.object(m,'atomic_move',side_effect=remove_first),self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256)
            self.assertTrue(fired[0]);self.assertFalse(f.exists())
            self.assertTrue(m.check(h)['partial'])
            with self.assertRaises(m.PolicyError):m.plan('remove',h)

    def test_unperformed_matching_postimage_is_not_ours(self):
        for initially_absent in (False,True):
            with self.subTest(initially_absent=initially_absent),tempfile.TemporaryDirectory() as t:
                h=Path(t).resolve();f=h/'.codex/AGENTS.md'
                if not initially_absent:f.parent.mkdir();f.write_bytes(b'initial personal')
                p=m.plan('install',h,B);post=next(c['post'] for c in p.changes if c['path']=='.codex/AGENTS.md')
                external_inode=[None]
                def fail_before_mutation(phase,name):
                    if phase=='before_replace' and name=='.codex/AGENTS.md':
                        f.write_bytes(m.raw(post));f.chmod(post['mode']);external_inode[0]=f.stat().st_ino
                        raise OSError('no own transition happened')
                with self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256,fs_event=fail_before_mutation)
                self.assertEqual(f.read_bytes(),m.raw(post));self.assertEqual(f.stat().st_ino,external_inode[0])
                self.assertTrue(m.check(h)['partial'])

    def test_rollback_preserves_same_bytes_external_inode(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'initial personal')
            p=m.plan('install',h,B);external_inode=[None]
            def fail(phase,name):
                if phase=='before_replace' and name=='.claude/CLAUDE.md':
                    tmp=h/'external-save';tmp.write_bytes(f.read_bytes());tmp.chmod(stat.S_IMODE(f.stat().st_mode));m.os.replace(tmp,f)
                    external_inode[0]=f.stat().st_ino
                    raise OSError('rollback after external atomic-save with identical bytes')
            with self.assertRaisesRegex(m.PolicyError,'recovery_required'):m.apply(p,p.sha256,fs_event=fail)
            self.assertEqual(f.stat().st_ino,external_inode[0]);self.assertIn(m.BEGIN,f.read_bytes())
            self.assertTrue(m.check(h)['partial'])

    def test_native_success_receipt_precedes_wrapper_failure(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();f=h/'.codex/AGENTS.md';f.parent.mkdir();f.write_bytes(b'initial personal')
            p=m.plan('install',h,B);real=m.atomic_exchange;fired=[False]
            def after_success(src,dst):
                real(src,dst)
                if Path(dst)==f and not fired[0]:fired[0]=True;raise OSError('native succeeded before wrapper raised')
            with patch.object(m,'atomic_exchange',side_effect=after_success),self.assertRaisesRegex(m.PolicyError,'operation_failed'):m.apply(p,p.sha256)
            self.assertTrue(fired[0]);self.assertEqual(f.read_bytes(),b'initial personal')
            self.assertEqual(m.check(h)['state'],'absent')

class CompatibleRestoreRegressions(unittest.TestCase):
    def test_compatible_later_mode_restore_check_and_remove(self):
        with tempfile.TemporaryDirectory() as t:
            h=Path(t).resolve();op(h);removed=op(h,'remove')
            f=h/'.codex/AGENTS.md';f.write_bytes(b'later compatible personal text\n');f.chmod(0o600)
            op(h,'restore',removed['backup_id'])
            self.assertTrue(m.check(h)['files_valid']);self.assertTrue(m.check(h)['ownership_valid'])
            op(h,'remove')
            self.assertEqual(f.read_bytes(),b'later compatible personal text\n')
            self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
            self.assertEqual(m.check(h)['state'],'absent')
