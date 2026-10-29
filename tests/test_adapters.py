"""Consumers reject unsafe bundles and render only conditional local adapters."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class AdapterTests(unittest.TestCase):
    def test_bundle_verified_and_conditional_adapters(self):
        from ai_policy.bundle import load_bundle, adapter
        bundle = load_bundle(ROOT / 'policy/bundle.json')
        for host in ('codex', 'claude'):
            rendered = adapter(bundle, host, Path('/synthetic/home'))
            self.assertIn(b'Only when', rendered)
            self.assertNotIn(bundle.files['policy/orca-common.md'], rendered)
            self.assertNotIn(b'@import', rendered)
            self.assertNotIn(b'https://', rendered)
            self.assertIn(b'/synthetic/home/.config/ai-agent-policy/orca/entrypoint.py', rendered)
        self.assertEqual(bundle.manifest['schema'], 1)
        self.assertEqual(len(bundle.manifest['source_hashes']), 5)

    def test_modified_component_and_unknown_schema_rejected(self):
        from ai_policy.bundle import load_bundle, PolicyError
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d).resolve()/'bundle'
            shutil.copytree(ROOT/'policy', dst/'policy')
            shutil.copytree(ROOT/'ai_policy', dst/'ai_policy', ignore=shutil.ignore_patterns('__pycache__'))
            (dst/'policy/orca-common.md').write_bytes(b'foreign bytes')
            with self.assertRaises(PolicyError): load_bundle(dst/'policy/bundle.json')
            m=json.loads((dst/'policy/bundle.json').read_text());m['schema']=9
            (dst/'policy/bundle.json').write_text(json.dumps(m))
            with self.assertRaises(PolicyError): load_bundle(dst/'policy/bundle.json')

    def test_missing_hash_or_traversal_rejected(self):
        from ai_policy.bundle import load_bundle, PolicyError
        with tempfile.TemporaryDirectory() as d:
            dst=Path(d).resolve(); (dst/'policy').mkdir()
            m=json.loads((ROOT/'policy/bundle.json').read_text())
            for bad in ('../outside', '/absolute'):
                m['files']={bad:'0'*64}
                (dst/'policy/bundle.json').write_text(json.dumps(m))
                with self.assertRaises(PolicyError): load_bundle(dst/'policy/bundle.json')

    def test_fifo_refused_before_open(self):
        import os
        from unittest.mock import patch
        from ai_policy.bundle import read_regular,PolicyError
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'fifo';os.mkfifo(p)
            with patch('ai_policy.bundle.os.open',side_effect=AssertionError('opened FIFO')):
                with self.assertRaisesRegex(PolicyError,'non_regular'):read_regular(p)

if __name__ == '__main__': unittest.main()
