"""Read-only drift check of Paseo agent profiles against the policy's paseo_roles. Never writes, fetches or calls Paseo."""
import argparse
import json
from pathlib import Path
import re

from .bundle import PolicyError
from .routing import load_codex_model_catalog, load_config, resolve_codex_family

DEFAULT_PASEO_CONFIG=Path.home()/'.paseo'/'config.json'
ALIAS_NOTE='claude ids are pinned exact ids; whether an alias now resolves elsewhere needs a live Paseo list_models check (not done offline)'

def _generation(model_id):
    m=re.fullmatch(r'gpt-(\d+(?:\.\d+)*)-[a-z0-9]+', model_id or '')
    return tuple(int(x) for x in m.group(1).split('.')) if m else None

def _read(path):
    try:
        p=Path(path)
        if p.stat().st_size>8*1024*1024: raise PolicyError('paseo_config_too_large')
        data=json.loads(p.read_text(encoding='utf-8'))
    except OSError: raise PolicyError('paseo_config_unavailable')
    except ValueError: raise PolicyError('paseo_config_invalid')
    profiles=data.get('daemon', {}).get('agentProfiles', []) if isinstance(data, dict) and isinstance(data.get('daemon', {}), dict) else None
    if not isinstance(profiles, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in profiles): raise PolicyError('paseo_config_invalid')
    return profiles

CLAUDE_ID=re.compile(r'claude-([a-z]+)((?:-\d{1,3})+)')

def _claude_version(model_id):
    # claude-<family>-<n>[-<n>...]; dated ids (8-digit part), "[1m]" variants, bare aliases and anything else do not parse.
    m=CLAUDE_ID.fullmatch(model_id) if isinstance(model_id, str) else None
    return (m.group(1), tuple(int(x) for x in m.group(2).split('-')[1:])) if m else None

def _read_models(path):
    try:
        p=Path(path)
        if p.stat().st_size>1024*1024: raise PolicyError('paseo_models_too_large')
        data=json.loads(p.read_text(encoding='utf-8'))
    except OSError: raise PolicyError('paseo_models_unavailable')
    except ValueError: raise PolicyError('paseo_models_invalid')
    items=data.get('models') if isinstance(data, dict) else data
    if not isinstance(items, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in items): raise PolicyError('paseo_models_invalid')
    return [x['id'] for x in items]

def check_profiles(config, profiles, *, model_catalog=None, paseo_models=None):
    managed=config.get('paseo_roles', {})
    seen, dup={}, set()
    for x in profiles:
        if x['id'] in seen: dup.add(x['id'])
        seen.setdefault(x['id'], x)
    report, drift, info={}, False, ([ALIAS_NOTE] if paseo_models is None else [])
    for pid, want in managed.items():
        model=config['models'][want['model']]
        row={'status':'ok','differences':[],'notes_differ':False,'info':[]}
        got=seen.get(pid)
        if got is None:
            row['status']='missing_provisional' if want.get('provisional') else 'missing'
            drift=drift or not want.get('provisional')
        else:
            expected={'provider':want['provider'],'model':want['pinned_id'],'modeId':want['mode_id']}
            if want['effort'] is not None: expected['thinkingOptionId']=want['effort']
            for field, value in expected.items():
                if got.get(field)!=value: row['differences'].append({'field':field,'expected':value,'actual':got.get(field)})
            if pid in dup: row['differences'].append({'field':'id','expected':'unique','actual':'duplicate'})
            if row['differences']: row['status']='drift'; drift=True
            row['notes_differ']=got.get('notes')!=want['description']
        if want.get('provisional'): row['provisional']=True
        if model['tool']=='claude':
            row['info'].append('pinned:'+want['pinned_id'])
            seen_alias=model.get('alias_observed')
            if isinstance(seen_alias, dict) and seen_alias.get('id')!=want['pinned_id']:
                row['info'].append('newer_alias_observed:%s on %s; not adopted, upgrade only by explicit sync'%(seen_alias.get('id'), seen_alias.get('observed_on')))
            if paseo_models is not None:
                pin=_claude_version(want['pinned_id'])
                found={(v, i) for i in set(paseo_models) for f, v in [_claude_version(i) or (None, None)] if pin and f==pin[0] and v>pin[1]}
                row['newer_available']=[i for _, i in sorted(found)]
        else:
            resolved=resolve_codex_family(config, model['codex_family'], model_catalog=model_catalog)
            r_id, how=resolved['model'], resolved['model_resolution']
            row['codex_resolution']={'pinned':want['pinned_id'],'resolved':r_id,'resolution':how}
            if how=='pinned_fallback':
                row['info'].append('catalog_stale_or_missing: pinned id kept, no upgrade suggested')
            elif r_id!=want['pinned_id']:
                a, b=_generation(r_id), _generation(want['pinned_id'])
                row['info'].append(('newer_generation_available:'+r_id) if a and b and a>b else 'catalog_not_newer_than_pinned: no change suggested')
        report[pid]=row
    unmanaged=sorted(set(seen)-set(managed))
    return {'schema':1,'drift':drift,'profiles':report,'unmanaged_profiles':unmanaged,'info':info}

def main(argv=None):
    p=argparse.ArgumentParser(prog='ai_policy.paseo'); sub=p.add_subparsers(dest='cmd', required=True)
    q=sub.add_parser('check', help='Read-only: compare Paseo agent profiles with policy paseo_roles')
    q.add_argument('--config', type=Path, default=DEFAULT_PASEO_CONFIG, help='Paseo config.json (default ~/.paseo/config.json)')
    q.add_argument('--policy', help='model-routing.json; defaults to the repository policy')
    q.add_argument('--model-catalog', help='Codex model cache JSON; defaults to CODEX_HOME/models_cache.json')
    q.add_argument('--paseo-models', type=Path, help='Offline JSON of Paseo list_models (provider claude): {"models":[{"id":...}]} or a bare list; reports newer same-family ids')
    a=p.parse_args(argv)
    try:
        value=check_profiles(load_config(a.policy), _read(a.config), model_catalog=load_codex_model_catalog(a.model_catalog),
                             paseo_models=_read_models(a.paseo_models) if a.paseo_models else None)
    except PolicyError as e:
        print(json.dumps({'schema':1,'error':str(e)}, sort_keys=True)); return 2
    print(json.dumps(value, sort_keys=True))
    return 1 if value['drift'] else 0

if __name__=='__main__': raise SystemExit(main())
