"""No implicit live-home writes, remote fetches, hook activation or trust bypass."""
import argparse
import json
import os
from pathlib import Path
import sys
from .bundle import PolicyError, load_bundle, read_regular
from .context import collect_runtime, decide, environment_hints, render_context
from .install import ROOT, apply, check, home_path, installed_state, plan

def parser():
    p=argparse.ArgumentParser(description='Offline shared Orca policy: explicit-home installation and fail-closed context.')
    sub=p.add_subparsers(dest='command',required=True)
    for op in ('install','remove','restore'):
        q=sub.add_parser(op);q.add_argument('--home',type=Path,required=True)
        if op=='install':q.add_argument('--bundle',type=Path,required=True)
        if op=='restore':q.add_argument('--backup',required=True)
        exclusive=q.add_mutually_exclusive_group(required=True)
        exclusive.add_argument('--dry-run',action='store_true')
        exclusive.add_argument('--plan-sha256')
    q=sub.add_parser('check');q.add_argument('--home',type=Path,required=True);q.add_argument('--format',choices=['json'],default='json')
    for op in ('detect','context'):
        q=sub.add_parser(op);q.add_argument('--home',type=Path)
        q.add_argument('--mode',choices=['auto'],default='auto')
        q.add_argument('--format',choices=['text'] if op=='context' else ['json'],default='text' if op=='context' else 'json')
    q=sub.add_parser('guide');q.add_argument('--explicit-request',action='store_true',required=True)
    q.add_argument('--bundle',type=Path)
    return p

def main(argv=None, *, installed_home=None):
    args=parser().parse_args(argv)
    try:
        if args.command in ('install','remove','restore'):
            p=plan(args.command,args.home,getattr(args,'bundle',None),getattr(args,'backup',None))
            value=p.public() if args.dry_run else apply(p,args.plan_sha256)
            print(json.dumps(value,sort_keys=True));return 0
        if args.command=='check':
            value=check(args.home);print(json.dumps(value,sort_keys=True))
            return 0 if value['files_valid'] else 10 if value['state']=='absent' else 30
        if args.command=='guide':
            # Caller/agent must already have explicit user intent. The flag records
            # the chosen mode, not evidence of consent or managed origin.
            path=args.bundle or Path(__file__).resolve().parents[1]/'policy/bundle.json'
            bundle=load_bundle(path)
            sys.stdout.buffer.write(bundle.files['policy/orca-common.md']);return 0
        home=args.home or installed_home
        valid=False;policy=b'';bundle_hash=None
        if home is not None:
            home=home_path(home)
            state=installed_state(home)
            if state:
                bundle_hash=state['bundle_sha256']
                bundle=load_bundle(home/ROOT/'generations'/bundle_hash/'policy/bundle.json')
                policy=bundle.files['policy/orca-common.md'];valid=True
        evidence=collect_runtime(Path.cwd(),environment_hints(os.environ))
        value=decide(evidence,valid,bundle_hash)
        if args.command=='detect':print(json.dumps(value,sort_keys=True))
        else:sys.stdout.buffer.write(render_context(value,policy))
        return {'active':0,'inactive':10,'ambiguous':20}[value['decision']]
    except PolicyError as e:
        if args.command=='context':print(str(e),file=sys.stderr)
        else:print(json.dumps({'schema':1,'error':str(e),'policy_emitted':False},sort_keys=True))
        return 30
    except OSError:
        if args.command=='context':print('filesystem_error',file=sys.stderr)
        else:print(json.dumps({'schema':1,'error':'filesystem_error','policy_emitted':False}))
        return 30

if __name__=='__main__':raise SystemExit(main())
