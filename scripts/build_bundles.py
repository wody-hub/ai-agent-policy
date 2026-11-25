"""Rewrite policy/bundle.json (Orca) and policy/paseo-bundle.json (Paseo) from the working tree.

Standard library only. File hashes come from the files on disk; the five provenance hashes come from the source
documents; --source-commit records the commit those documents are pinned to. These are integrity and provenance
inputs, not proof of publisher identity. Use --check to verify without writing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_policy.bundle import FLAVORS  # noqa: E402

COMMON_SOURCES=('README.md','claude-code-global-model-routing-prompt.md','codex-global-model-routing-prompt.md','project-task-policy-setup.md')
FLAVOR_SOURCE={'orca':'orca-project-setup.md','paseo':'paseo-project-setup.md'}
MANIFEST={'orca':'policy/bundle.json','paseo':'policy/paseo-bundle.json'}

def sha(path): return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def build(flavor, version, source_commit):
    m={'files':{n:sha(n) for n in sorted(FLAVORS[flavor]['required'])},
       'installer_schema':1,'installer_version':'0.2.0','schema':1,
       'source_commit':source_commit,
       'source_hashes':{n:sha(n) for n in sorted((*COMMON_SOURCES,FLAVOR_SOURCE[flavor]))},
       'version':version}
    if flavor!='orca': m['flavor']=flavor  # an Orca manifest has no flavor key (original format)
    return (json.dumps(m,indent=2,sort_keys=True)+'\n').encode()

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--source-commit',required=True)
    p.add_argument('--orca-version',default='0.2.2'); p.add_argument('--paseo-version',default='0.1.0')
    p.add_argument('--check',action='store_true')
    a=p.parse_args(argv)
    if not re.fullmatch('[0-9a-f]{40}',a.source_commit): p.error('source commit must be a 40-hex sha')
    bad=0
    for flavor,version in (('orca',a.orca_version),('paseo',a.paseo_version)):
        data=build(flavor,version,a.source_commit); path=ROOT/MANIFEST[flavor]
        if a.check:
            same=path.exists() and path.read_bytes()==data
            print(MANIFEST[flavor],'ok' if same else 'DIFFERS'); bad+=not same
        else:
            path.write_bytes(data); print('wrote',MANIFEST[flavor])
    return 1 if bad else 0

if __name__=='__main__': raise SystemExit(main())
