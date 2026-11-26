"""Paseo bundle flavor: manifest rules, adapters, explicit-home install in temporary directories only."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ORCA=ROOT/'policy/bundle.json'
PASEO=ROOT/'policy/paseo-bundle.json'
OREL=Path('.config/ai-agent-policy/orca'); PREL=Path('.config/ai-agent-policy/paseo')

def snapshot(root):
    return {str(p.relative_to(root)):('dir' if p.is_dir() else 'file',stat.S_IMODE(p.stat().st_mode),p.read_bytes() if p.is_file() else None)
            for p in root.rglob('*')}

class ManifestTests(unittest.TestCase):
    def test_flavors_and_file_sets(self):
        from ai_policy.bundle import load_bundle, REQUIRED, PASEO_REQUIRED
        o=load_bundle(ORCA); p=load_bundle(PASEO)
        self.assertEqual((o.flavor, p.flavor), ('orca','paseo'))
        self.assertNotIn('flavor', o.manifest)            # original Orca manifest format
        self.assertEqual(p.manifest['flavor'], 'paseo')
        self.assertEqual(set(o.files), REQUIRED); self.assertEqual(set(p.files), PASEO_REQUIRED)
        self.assertIn('policy/paseo-common.md', p.files); self.assertNotIn('policy/orca-common.md', p.files)
        self.assertEqual(len(p.manifest['source_hashes']), 5); self.assertIn('paseo-project-setup.md', p.manifest['source_hashes'])
        self.assertEqual(len(o.manifest['source_hashes']), 5); self.assertIn('orca-project-setup.md', o.manifest['source_hashes'])
        self.assertNotEqual(o.sha256, p.sha256)

    def test_paseo_adapters_are_conditional_and_flavor_specific(self):
        from ai_policy.bundle import load_bundle, adapter
        b=load_bundle(PASEO)
        for host in ('codex','claude'):
            text=adapter(b, host, Path('/synthetic/home'))
            self.assertIn(b'Only when', text); self.assertIn(b'PASEO_AGENT_ID', text)
            self.assertIn(b'/synthetic/home/.config/ai-agent-policy/paseo/entrypoint.py', text)
            self.assertNotIn(b.files['policy/paseo-common.md'], text)
            for bad in (b'@import', b'https://', b'orca/entrypoint'): self.assertNotIn(bad, text)

    def test_manifest_flavor_rules(self):
        from ai_policy.bundle import load_bundle, PolicyError
        with tempfile.TemporaryDirectory() as d:
            dst=Path(d).resolve()
            shutil.copytree(ROOT/'policy',dst/'policy'); shutil.copytree(ROOT/'ai_policy',dst/'ai_policy',ignore=shutil.ignore_patterns('__pycache__'))
            def with_manifest(mut, name='paseo-bundle.json'):
                m=json.loads((ROOT/'policy'/name).read_text()); mut(m)
                (dst/'policy'/'test-bundle.json').write_text(json.dumps(m)); return dst/'policy'/'test-bundle.json'
            load_bundle(with_manifest(lambda m: None))
            for label, mut in (('unknown flavor', lambda m: m.update(flavor='other')),
                               ('explicit orca flavor', lambda m: m.update(flavor='orca')),
                               ('orca file set under paseo', lambda m: m.update(files={**{k:v for k,v in m['files'].items() if 'paseo' not in k},'policy/orca-common.md':'0'*64})),
                               ('missing paseo file', lambda m: m['files'].pop('policy/paseo-common.md'))):
                with self.subTest(label), self.assertRaises(PolicyError): load_bundle(with_manifest(mut))
            with self.assertRaises(PolicyError): load_bundle(with_manifest(lambda m: m.update(flavor='paseo'), 'bundle.json'))  # Orca files under a paseo flavor
            (dst/'policy/paseo-common.md').write_bytes(b'foreign')
            with self.assertRaises(PolicyError) as cm: load_bundle(dst/'policy/paseo-bundle.json')
            self.assertEqual(str(cm.exception), 'bundle_drift')

    def test_launchers(self):
        from ai_policy.install import launcher
        self.assertEqual(launcher(), launcher('orca')); self.assertNotIn(b"flavor='paseo'", launcher('orca'))
        self.assertIn(b"main(installed_home=root.parents[2],flavor='paseo')", launcher('paseo'))
        from ai_policy.bundle import PolicyError
        with self.assertRaises(PolicyError): launcher('other')

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai-policy-paseo-test-'); self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name).resolve()
        self.codex=self.home/'.codex/AGENTS.md'; self.claude=self.home/'.claude/CLAUDE.md'
        self.codex.parent.mkdir(); self.claude.parent.mkdir()
        self.codex.write_bytes('개인 노트\r\n'.encode()); self.claude.write_bytes(b'Personal model\n')
        self.codex.chmod(0o640); self.claude.chmod(0o640)
        self.initial={p:(p.read_bytes(),stat.S_IMODE(p.stat().st_mode)) for p in (self.codex,self.claude)}

    def op(self, operation='install', flavor='paseo', bundle=None, backup=None):
        from ai_policy.install import plan, apply
        bundle=bundle if bundle is not None else (PASEO if flavor=='paseo' else ORCA)
        p=plan(operation,self.home,bundle if operation=='install' else None,backup,flavor)
        return apply(p,p.sha256)

    def assert_initial(self):
        for p,(data,mode) in self.initial.items():
            self.assertEqual(p.read_bytes(),data); self.assertEqual(stat.S_IMODE(p.stat().st_mode),mode)

    def test_paseo_install_roundtrip_in_temp_home_only(self):
        from ai_policy.install import check
        r=self.op(); c=check(self.home,'paseo')
        self.assertTrue(c['files_valid'] and c['ownership_valid']); self.assertFalse(c['hook_configured'])
        for k in ('load_verified','origin_verified','enforcement_verified'): self.assertIsNone(c[k])
        self.assertEqual(check(self.home)['state'],'absent')            # the Orca flavor is untouched
        self.assertFalse((self.home/OREL).exists()); self.assertTrue((self.home/PREL/'entrypoint.py').is_file())
        for p in (self.codex,self.claude):
            data=p.read_bytes()
            self.assertEqual(data.count(b'ai-agent-policy:paseo-adapter:begin'),1); self.assertNotIn(b'orca-adapter',data)
        self.assertEqual(stat.S_IMODE((self.home/PREL/'entrypoint.py').stat().st_mode),0o700)
        self.assertEqual(len(list((self.home/PREL/'generations').rglob('paseo-common.md'))),1)
        self.op('restore',backup=r['backup_id']); self.assert_initial()
        self.assertEqual(check(self.home,'paseo')['state'],'absent')

    def test_dry_run_writes_nothing_and_plan_digest_is_required(self):
        from ai_policy.install import plan, apply
        from ai_policy.bundle import PolicyError
        before=snapshot(self.home)
        p=plan('install',self.home,PASEO,None,'paseo')
        self.assertEqual(snapshot(self.home),before)
        self.assertEqual(p.public()['flavor'],'paseo')
        self.assertNotIn('flavor',plan('install',self.home,ORCA).public())      # Orca plan digest shape unchanged
        with self.assertRaisesRegex(PolicyError,'plan_digest_mismatch'): apply(p,'0'*64)
        apply(p,p.sha256)
        p=plan('install',self.home,PASEO,None,'paseo'); before=snapshot(self.home)
        self.assertEqual(p.public()['changes'],[]); self.assertFalse(apply(p,p.sha256)['changed'])
        self.assertEqual(snapshot(self.home),before)

    def test_flavor_mismatch_is_refused(self):
        from ai_policy.install import plan
        from ai_policy.bundle import PolicyError
        before=snapshot(self.home)
        for flavor,bundle in (('orca',PASEO),('paseo',ORCA)):
            with self.subTest(flavor=flavor), self.assertRaisesRegex(PolicyError,'bundle_flavor_mismatch'): plan('install',self.home,bundle,None,flavor)
        with self.assertRaisesRegex(PolicyError,'unsupported_flavor'): plan('install',self.home,PASEO,None,'other')
        self.assertEqual(snapshot(self.home),before)

    def test_orca_and_paseo_coexist_and_remove_independently(self):
        from ai_policy.install import check
        self.op(flavor='orca'); self.op(flavor='paseo')
        self.assertTrue(check(self.home)['files_valid']); self.assertTrue(check(self.home,'paseo')['files_valid'])
        for p in (self.codex,self.claude):
            data=p.read_bytes(); self.assertEqual(data.count(b'orca-adapter:begin'),1); self.assertEqual(data.count(b'paseo-adapter:begin'),1)
        self.op('remove',flavor='paseo')
        self.assertEqual(check(self.home,'paseo')['state'],'absent'); self.assertTrue(check(self.home)['files_valid'])
        for p in (self.codex,self.claude):
            data=p.read_bytes(); self.assertEqual(data.count(b'orca-adapter:begin'),1); self.assertNotIn(b'paseo-adapter',data)
        self.op('remove',flavor='orca')
        self.assert_initial()

    def test_reverse_order_coexistence(self):
        from ai_policy.install import check
        self.op(flavor='paseo'); self.op(flavor='orca')
        self.assertTrue(check(self.home)['files_valid'] and check(self.home,'paseo')['files_valid'])
        self.op('remove',flavor='orca')
        self.assertTrue(check(self.home,'paseo')['files_valid']); self.assertEqual(check(self.home)['state'],'absent')
        self.op('remove',flavor='paseo'); self.assert_initial()

    def test_malformed_and_unowned_paseo_markers_are_refused(self):
        from ai_policy.install import plan, layout
        from ai_policy.bundle import PolicyError
        L=layout('paseo')
        for block in (L.begin, L.end, L.end+L.begin, L.begin+L.begin+L.end, L.begin+b'foreign\n'+L.end+L.begin):
            self.codex.write_bytes(block)
            with self.subTest(block=block), self.assertRaises(PolicyError): plan('install',self.home,PASEO,None,'paseo')
        # A complete foreign Paseo block with no installation record must be adopted explicitly, never overwritten.
        self.codex.write_bytes(L.begin+b'\nforeign\n'+L.end+b'\n')
        with self.assertRaisesRegex(PolicyError,'adoption_required'): plan('install',self.home,PASEO,None,'paseo')

    def test_drift_detected_per_flavor(self):
        from ai_policy.install import check
        self.op(); common=next((self.home/PREL/'generations').rglob('paseo-common.md')); common.write_bytes(b'foreign policy')
        self.assertTrue(check(self.home,'paseo')['drift']); self.assertEqual(check(self.home)['state'],'absent')

    def test_installed_paseo_entrypoint_runs_offline_and_cannot_activate(self):
        self.op()
        hostile=self.home/'hostile'; hostile.mkdir()
        (hostile/'ai_policy.py').write_text('raise RuntimeError("foreign")')
        entry=self.home/PREL/'entrypoint.py'
        env={'PATH':str(hostile),'PYTHONPATH':str(hostile),'PASEO_AGENT_ID':'agent-1'}
        r=subprocess.run([str(entry),'check','--home',str(self.home),'--flavor','paseo'],cwd=hostile,env=env,capture_output=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr.decode()); self.assertTrue(json.loads(r.stdout)['files_valid'])
        r=subprocess.run([str(entry),'guide','--explicit-request','--flavor','paseo'],cwd=hostile,env=env,capture_output=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr.decode()); self.assertIn(b'Paseo orchestration policy',r.stdout)   # installed generation stores the manifest as bundle.json
        r=subprocess.run([str(entry),'guide','--explicit-request'],cwd=hostile,env=env,capture_output=True,timeout=15)
        # The installed Paseo entrypoint fixes its own flavor: the default --flavor orca is overridden, never emitting Orca policy.
        self.assertEqual(r.returncode,0,r.stderr.decode()); self.assertIn(b'Paseo orchestration policy',r.stdout); self.assertNotIn(b'Shared Orca',r.stdout)
        r=subprocess.run([str(entry),'context','--mode','auto','--format','text'],cwd=hostile,env=env,capture_output=True,timeout=15)
        self.assertEqual((r.returncode,r.stdout),(20,b''),r.stderr.decode())   # env hint only: ambiguous, no policy emitted
        env.pop('PASEO_AGENT_ID')
        r=subprocess.run([str(entry),'context','--mode','auto','--format','text'],cwd=hostile,env=env,capture_output=True,timeout=15)
        self.assertEqual((r.returncode,r.stdout),(10,b''),r.stderr.decode())
        self.assertEqual(list((self.home/PREL/'generations').rglob('*.pyc')),[])

    def test_cli_guide_and_install_with_flavor(self):
        def run(*a): return subprocess.run([sys.executable,'-B','-m','ai_policy',*map(str,a)],cwd=ROOT,capture_output=True,timeout=25)
        r=run('guide','--explicit-request','--flavor','paseo'); self.assertEqual(r.returncode,0,r.stderr.decode()); self.assertIn(b'Paseo orchestration policy',r.stdout)
        r=run('guide','--explicit-request'); self.assertIn(b'Shared Orca',r.stdout)
        r=run('guide','--explicit-request','--flavor','paseo','--bundle',ORCA); self.assertEqual(r.returncode,30)
        r=run('install','--home',self.home,'--bundle',PASEO,'--flavor','paseo','--dry-run'); self.assertEqual(r.returncode,0,r.stderr.decode())
        digest=json.loads(r.stdout)['plan_sha256']
        r=run('install','--home',self.home,'--bundle',PASEO,'--plan-sha256',digest)        # default flavor orca: refused, writes nothing
        self.assertEqual(r.returncode,30); self.assertFalse((self.home/PREL).exists())
        r=run('install','--home',self.home,'--bundle',PASEO,'--flavor','paseo','--plan-sha256',digest); self.assertEqual(r.returncode,0,r.stderr.decode())
        r=run('check','--home',self.home,'--flavor','paseo'); self.assertEqual(r.returncode,0); self.assertTrue(json.loads(r.stdout)['files_valid'])
        r=run('check','--home',self.home); self.assertEqual(r.returncode,10)

if __name__=='__main__': unittest.main()
