"""CLI refuses implicit homes, trust knobs and accidental guidance; emits no policy on failure."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class CliTests(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,'-m','ai_policy',*map(str,args)],cwd=ROOT,capture_output=True,timeout=25)

    def test_explicit_inputs_and_no_trust_override(self):
        for args in [('install',),('guide',),('detect','--trust'),('detect','--fixture','x')]:
            with self.subTest(args=args):self.assertNotEqual(self.invoke(*args).returncode,0)

    def test_guidance_cannot_activate_and_needs_verified_bundle(self):
        r=self.invoke('guide','--explicit-request','--bundle',ROOT/'policy/bundle.json')
        self.assertEqual(r.returncode,0,r.stderr.decode());self.assertIn(b'Shared Orca',r.stdout)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()
            r=self.invoke('context','--home',p,'--mode','auto')
            self.assertIn(r.returncode,(10,20));self.assertEqual(r.stdout,b'')
            r=self.invoke('detect','--home',p)
            value=json.loads(r.stdout)
            self.assertFalse(value['policy_emitted']);self.assertFalse(value['checks']['invocation_bound'])

    def test_install_dry_run_and_apply_digest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()
            r=self.invoke('install','--home',p,'--bundle',ROOT/'policy/bundle.json','--dry-run')
            self.assertEqual(r.returncode,0,r.stderr.decode());plan=json.loads(r.stdout)
            self.assertEqual(list(p.iterdir()),[])
            r=self.invoke('install','--home',p,'--bundle',ROOT/'policy/bundle.json','--plan-sha256',plan['plan_sha256'])
            self.assertEqual(r.returncode,0,r.stderr.decode())
            self.assertTrue(json.loads(self.invoke('check','--home',p).stdout)['files_valid'])

if __name__=='__main__':unittest.main()
