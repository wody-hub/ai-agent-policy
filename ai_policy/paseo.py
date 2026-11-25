"""Paseo agent profiles vs the policy's paseo_profiles (the managed set; values derived by routing.paseo_profile_spec).

`check` is read-only. `sync` (dry run by default) and `sync --restore` write only ~/.paseo/config.json-style files that the caller names, only
after a confirmed plan hash, and never fetch or call Paseo. The running Paseo daemon does not hot-reload that file."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import stat

from .bundle import PolicyError, digest, encode
from .routing import _profile_target, load_codex_model_catalog, load_config, paseo_profile_spec, resolve_codex_family

DEFAULT_PASEO_CONFIG=Path.home()/'.paseo'/'config.json'

def default_state_dir(config_path):
    """Per-user state and backup directory keyed by the config's absolute path; never inside a repository.
    Backups are full copies of the config and can hold secrets."""
    xdg=os.environ.get('XDG_STATE_HOME')
    base=Path(xdg) if xdg and os.path.isabs(xdg) else Path.home()/'.local'/'state'
    return base/'ai-policy'/'paseo-sync'/digest(os.path.abspath(config_path).encode('utf-8'))[:8]

def _state_dir(a): return a.state_dir if a.state_dir is not None else default_state_dir(a.config)
ALIAS_NOTE='claude ids are pinned exact ids; whether an alias now resolves elsewhere needs a live Paseo list_models check (not done offline)'

def _codex_family(model_id):
    m=re.fullmatch(r'gpt-\d+(?:\.\d+)*-([a-z0-9]+)', model_id or '')
    return m.group(1) if m else None

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

def _managed(config):
    """Managed profiles: id -> (derived spec, model alias). Only paseo_profiles defines this set; features (plan_mode) are never managed."""
    return {pid: (paseo_profile_spec(config, pid), _profile_target(config, config['paseo_profiles'][pid])[0]) for pid in config.get('paseo_profiles', {})}

def check_profiles(config, profiles, *, model_catalog=None, paseo_models=None):
    managed=_managed(config)
    seen, dup={}, set()
    for x in profiles:
        if x['id'] in seen: dup.add(x['id'])
        seen.setdefault(x['id'], x)
    report, drift, info={}, False, ([ALIAS_NOTE] if paseo_models is None else [])
    for pid, (want, alias) in managed.items():
        model=config['models'][alias]
        row={'status':'ok','differences':[],'notes_differ':False,'info':[]}
        got=seen.get(pid)
        if got is None:
            row['status']='missing_provisional' if want['provisional'] else 'missing'
            drift=drift or not want['provisional']
        else:
            expected=_desired(want)
            for field, value in expected.items():
                if got.get(field)!=value: row['differences'].append({'field':field,'expected':value,'actual':got.get(field)})
            if pid in dup: row['differences'].append({'field':'id','expected':'unique','actual':'duplicate'})
            if row['differences']: row['status']='drift'; drift=True
            row['notes_differ']=want['notes'] is not None and got.get('notes')!=want['notes']
        if want['provisional']: row['provisional']=True
        if model['tool']=='claude':
            row['info'].append('pinned:'+want['model'])
            seen_alias=model.get('alias_observed')
            if isinstance(seen_alias, dict) and seen_alias.get('id')!=want['model']:
                row['info'].append('newer_alias_observed:%s on %s; not adopted, upgrade only by explicit sync'%(seen_alias.get('id'), seen_alias.get('observed_on')))
            if paseo_models is not None:
                pin=_claude_version(want['model'])
                found={(v, i) for i in set(paseo_models) for f, v in [_claude_version(i) or (None, None)] if pin and f==pin[0] and v>pin[1]}
                row['newer_available']=[i for _, i in sorted(found)]
        else:
            resolved=resolve_codex_family(config, model['codex_family'], model_catalog=model_catalog)
            r_id, how=resolved['model'], resolved['model_resolution']
            row['codex_resolution']={'pinned':want['model'],'resolved':r_id,'resolution':how}
            if how=='pinned_fallback':
                row['info'].append('catalog_stale_or_missing: pinned id kept, no upgrade suggested')
            elif r_id!=want['model']:
                a, b=_generation(r_id), _generation(want['model'])
                row['info'].append(('newer_generation_available:'+r_id) if a and b and a>b else 'catalog_not_newer_than_pinned: no change suggested')
        report[pid]=row
    unmanaged=sorted(set(seen)-set(managed))
    return {'schema':1,'drift':drift,'profiles':report,'unmanaged_profiles':unmanaged,'info':info}

FIELDS=('provider','model','modeId','thinkingOptionId')
BACKUP_NAME=re.compile(r'config\.\d{8}T\d{6}Z\.([0-9a-f]{8})\.json')
RELOAD_NOTE=('The running Paseo daemon does not hot-reload config.json: restart the Paseo daemon (or app) for this change to take effect. '
             'Saving profiles from the Paseo app UI before that restart could overwrite this change.')
MAX_BYTES=8*1024*1024

# ---- file helpers -------------------------------------------------------------------------------------------------------------------------
def _read_bytes(path):
    """Config bytes (a symlinked config is readable; writing to one is refused)."""
    try:
        fd=os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode): raise PolicyError('paseo_config_unavailable')
            if st.st_size>MAX_BYTES: raise PolicyError('paseo_config_too_large')
            return f.read(MAX_BYTES+1)
    except OSError: raise PolicyError('paseo_config_unavailable')

def _read_nofollow(path, error):
    try:
        fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size>MAX_BYTES: raise PolicyError(error)
            return f.read(MAX_BYTES+1)
    except OSError: raise PolicyError(error)

def _sync_dir(path):
    fd=os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)

def _private_dir(path, error, create=False):
    """True if the directory exists and is a private directory of ours (not a symlink); creates it 0700 when asked."""
    try: st=os.lstat(path)
    except FileNotFoundError:
        if not create: return False
        missing=[]
        p=Path(path)
        while not os.path.lexists(p): missing.append(p); p=p.parent
        for d in reversed(missing):   # every created parent is private too
            try: os.mkdir(d, 0o700)
            except FileExistsError: pass
            os.chmod(d, 0o700)
        st=os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode & 0o077: raise PolicyError(error)
    return True

def _before_replace(path):
    """Test seam: runs after the temp file is complete and before the final sha re-check."""

def _write_atomic(path, data, expected_sha256, mode):
    """Temp file in the same directory, fsync, mode, sha re-check of the target, os.replace. Leaves no temp file on any failure."""
    path=Path(path)
    if os.path.islink(path): raise PolicyError('config_symlink')
    tmp=path.parent/('.%s.%s.tmp'%(path.stem, secrets.token_hex(6)))
    fd=os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fchmod(f.fileno(), mode); os.fsync(f.fileno())
        _before_replace(path)
        if digest(_read_bytes(path))!=expected_sha256: raise PolicyError('config_changed')
        os.replace(tmp, path); tmp=None
        _sync_dir(path.parent)
    finally:
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass

def _backup(state_dir, raw):
    """Private copy of the config bytes. Never printed: the file can hold secrets."""
    _private_dir(state_dir, 'state_dir_unsafe', create=True)
    b=Path(state_dir)/'backups'
    if not _private_dir(b, 'backups_dir_unsafe'): os.mkdir(b, 0o700); os.chmod(b, 0o700)
    path=b/('config.%s.%s.json'%(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'), digest(raw)[:8]))
    try: fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if _read_nofollow(path, 'backup_exists')==raw: return path
        raise PolicyError('backup_exists')
    try:
        with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fchmod(f.fileno(), 0o600); os.fsync(f.fileno())
        _sync_dir(b)
    except BaseException:
        try: os.unlink(path)
        except OSError: pass
        raise
    return path

def _load_state(state_dir, config_path):
    """Last-applied values per profile. A state written for another config file (or without a path) is refused, never mixed in."""
    if not _private_dir(state_dir, 'state_dir_unsafe'): return {}
    p=Path(state_dir)/'state.json'
    try: os.lstat(p)
    except FileNotFoundError: return {}
    try:
        data=json.loads(_read_nofollow(p, 'state_invalid'))
        profiles=data['profiles']
        if data['schema']!=1 or not isinstance(profiles, dict) or any(not isinstance(v, dict) for v in profiles.values()): raise ValueError()
    except (ValueError, TypeError, KeyError): raise PolicyError('state_invalid')
    if data.get('config_path')!=os.path.abspath(config_path): raise PolicyError('state_config_mismatch')
    return profiles

def _save_state(state_dir, profiles, config_sha256, config_path):
    _private_dir(state_dir, 'state_dir_unsafe', create=True)
    path=Path(state_dir)/'state.json'; tmp=Path(state_dir)/('.state.%s.tmp'%secrets.token_hex(6))
    fd=os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write((json.dumps({'schema':1,'config_path':os.path.abspath(config_path),'config_sha256':config_sha256,'profiles':profiles}, indent=2, sort_keys=True)+'\n').encode())
            f.flush(); os.fchmod(f.fileno(), 0o600); os.fsync(f.fileno())
        os.replace(tmp, path); tmp=None; _sync_dir(state_dir)
    finally:
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass

# ---- sync plan ---------------------------------------------------------------------------------------------------------------------------
def _parse(raw):
    try: data=json.loads(raw.decode('utf-8'))
    except ValueError: raise PolicyError('paseo_config_invalid')   # includes UnicodeDecodeError
    d=data.get('daemon') if isinstance(data, dict) else None
    profiles=d.get('agentProfiles') if isinstance(d, dict) else None
    if not isinstance(profiles, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in profiles): raise PolicyError('paseo_config_invalid')
    return data, profiles

def _dump(data): return (json.dumps(data, indent=2, ensure_ascii=False)+'\n').encode('utf-8')

def _recorded(want):
    """What a profile looks like once it matches the policy (an unset thinking option is recorded as None)."""
    d=_desired(want); d.setdefault('thinkingOptionId', None); return d

def _desired(want):
    d={'provider':want['provider'],'model':want['model'],'modeId':want['modeId']}
    if want['thinkingOptionId'] is not None: d['thinkingOptionId']=want['thinkingOptionId']
    return d

def _refusal(config, alias, current_model, desired_model, model_catalog):
    """Never touch a Codex model id on a stale/missing catalog and never move a model to a lower generation. Not overridable."""
    if config['models'][alias]['tool']=='codex':
        family=config['models'][alias]['codex_family']
        if resolve_codex_family(config, family, model_catalog=model_catalog)['model_resolution']=='pinned_fallback': return 'pinned_fallback'
        # Generations are only comparable within one family (Terra 6.1 -> Luna 6 or Sol 6.2 -> Terra 6.1 is a family change, not a downgrade).
        a, b=_generation(desired_model), _generation(current_model)
        return 'downgrade' if a and b and _codex_family(desired_model)==_codex_family(current_model) and a<b else None
    a, b=_claude_version(desired_model), _claude_version(current_model)
    return 'downgrade' if a and b and a[0]==b[0] and a[1]<b[1] else None

def plan_sync(raw, config_path, config, *, model_catalog, state, include_provisional, overwrite):
    data, profiles=_parse(raw)
    managed=_managed(config)
    by_id={}
    for x in profiles:
        if x['id'] in managed and x['id'] in by_id: raise PolicyError('duplicate_profile_id')
        by_id.setdefault(x['id'], x)
    rows, writes, record=({}, {}, {})
    for pid, (want, alias) in managed.items():
        desired=_desired(want); cur=by_id.get(pid); row={'action':None,'fields':[]}
        if cur is None:
            if want['provisional'] and not include_provisional: row['action']='skip_provisional'
            else:
                row['action']='create'; row['fields']=[{'field':f,'current':None,'desired':v} for f, v in desired.items()]
                new={'id':pid,'name':pid}; new.update(desired); new.update(options=None)
                if want['notes'] is not None: new['notes']=want['notes']
                row['new_profile']=new
        else:
            diffs=[{'field':f,'current':cur.get(f),'desired':v} for f, v in desired.items() if cur.get(f)!=v]
            row['fields']=diffs
            if want['notes'] is not None and cur.get('notes')!=want['notes']: row['notes_differ']=True
            if not diffs: row['action']='noop'
            else:
                model_diff=next((d for d in diffs if d['field']=='model'), None)
                refusal=_refusal(config, alias, model_diff['current'], model_diff['desired'], model_catalog) if model_diff else None
                recorded=state.get(pid, {})
                unsafe=[d for d in diffs if not (d['field'] in recorded and recorded[d['field']]==d['current'])]
                if refusal: row['action']='refused:'+refusal
                elif unsafe and pid not in overwrite: row['action']='conflict'
                else:
                    row['action']='update'
                    if unsafe: row['overwritten']=True
        if row['action'] in ('create','update'): writes[pid]=desired
        if row['action'] in ('noop','create','update'): record[pid]=_recorded(want)   # adopted baseline for later conflict checks
        rows[pid]=row
    conflicts=[p for p, r in rows.items() if r['action']=='conflict']
    refusals=[p for p, r in rows.items() if r['action'].startswith('refused:')]
    new_bytes=None
    if writes:
        if _dump(data)!=raw: raise PolicyError('config_format_drift')
        for pid, row in rows.items():
            if row['action']=='create': profiles.append(dict(row['new_profile']))
            elif row['action']=='update': by_id[pid].update(writes[pid])
        new_bytes=_dump(data)
    body={'schema':1,'operation':'sync','config_path':os.path.abspath(config_path),'config_sha256':digest(raw),'include_provisional':bool(include_provisional),
          'overwrite':sorted(overwrite),'profiles':rows,'changes':len(writes),'conflicts':conflicts,'refusals':refusals,
          'after_sha256':digest(new_bytes) if new_bytes is not None else None}
    return {'body':body,'plan_sha256':digest(encode(body)),'new_bytes':new_bytes,'writes':writes,'record':record}

def _verify_hash(given, plan):
    if given is None: return
    if not isinstance(given, str) or not re.fullmatch('[0-9a-f]{64}', given): raise PolicyError('plan_sha256_invalid')
    if given!=plan['plan_sha256']: raise PolicyError('plan_sha256_mismatch')

def _result(body, plan_sha256, applied, **extra):
    out=dict(body); out.pop('config_path', None)
    out.update(plan_sha256=plan_sha256, dry_run=extra.pop('dry_run'), applied=applied, daemon_reload_required=applied)
    out.update(extra)
    if applied: out['note']=RELOAD_NOTE
    return out

def run_sync(a):
    config=load_config(a.policy); catalog=load_codex_model_catalog(a.model_catalog)
    overwrite={x for chunk in (a.overwrite or []) for x in chunk.split(',') if x}
    if overwrite-set(config['paseo_profiles']): raise PolicyError('overwrite_unknown_id')
    raw=_read_bytes(a.config)
    plan=plan_sync(raw, a.config, config, model_catalog=catalog, state=_load_state(_state_dir(a), a.config), include_provisional=a.include_provisional, overwrite=overwrite)
    _verify_hash(a.plan_sha256, plan)
    body=plan['body']; code=1 if body['conflicts'] or body['refusals'] else 0
    if a.plan_sha256 is None: return _result(body, plan['plan_sha256'], False, dry_run=True), code
    if not plan['writes']:
        # Nothing to write to the config (its bytes and mtime stay untouched), but the matching profiles are the adopted baseline.
        state=_load_state(_state_dir(a), a.config); state.update(plan['record'])
        _save_state(_state_dir(a), state, digest(raw), a.config)
        return _result(body, plan['plan_sha256'], False, dry_run=False, state_saved=True), code
    mode=stat.S_IMODE(os.stat(a.config).st_mode)
    backup=_backup(_state_dir(a), raw)
    _write_atomic(a.config, plan['new_bytes'], digest(raw), mode)
    after=_read_bytes(a.config)
    try: _, now=_parse(after)
    except PolicyError: now=[]
    got={x['id']:x for x in now}
    if after!=plan['new_bytes'] or any(got.get(pid, {}).get(f, KeyError)!=v for pid, want in plan['writes'].items() for f, v in want.items()):
        raise PolicyError('post_write_verification_failed')
    state=_load_state(_state_dir(a), a.config); state.update(plan['record'])
    _save_state(_state_dir(a), state, digest(after), a.config)
    return _result(body, plan['plan_sha256'], True, dry_run=False, backup=str(backup), state_saved=True), code

# ---- restore -----------------------------------------------------------------------------------------------------------------------------
def _resolve_backup(state_dir, arg):
    """Only a regular, correctly named, uncorrupted file directly inside <state-dir>/backups/ (no symlinks, no traversal)."""
    if not _private_dir(state_dir, 'state_dir_unsafe'): raise PolicyError('backup_outside_backups_dir')
    bdir=Path(state_dir)/'backups'
    if not _private_dir(bdir, 'backups_dir_unsafe'): raise PolicyError('backup_outside_backups_dir')
    cand=Path(os.path.abspath(arg))
    real=Path(os.path.realpath(bdir))
    if Path(os.path.realpath(cand.parent))!=real: raise PolicyError('backup_outside_backups_dir')
    m=BACKUP_NAME.fullmatch(cand.name)
    if not m: raise PolicyError('backup_name_invalid')
    path=real/cand.name
    try: st=os.lstat(path)
    except OSError: raise PolicyError('backup_unavailable')
    if stat.S_ISLNK(st.st_mode): raise PolicyError('symlink')
    if not stat.S_ISREG(st.st_mode): raise PolicyError('non_regular')
    raw=_read_nofollow(path, 'backup_unavailable')
    if digest(raw)[:8]!=m.group(1): raise PolicyError('backup_corrupt')
    try: _parse(raw)
    except PolicyError: raise PolicyError('backup_invalid')
    return path, raw

def run_restore(a):
    path, braw=_resolve_backup(_state_dir(a), a.restore)
    _load_state(_state_dir(a), a.config)   # a state for another config file is refused here too
    raw=_read_bytes(a.config)   # the file being replaced may itself be broken; only its bytes matter
    body={'schema':1,'operation':'restore','config_path':os.path.abspath(a.config),'config_sha256':digest(raw),'backup':path.name,'backup_sha256':digest(braw),
          'changes':int(raw!=braw)}
    plan={'plan_sha256':digest(encode(body))}
    _verify_hash(a.plan_sha256, plan)
    if a.plan_sha256 is None: return _result(body, plan['plan_sha256'], False, dry_run=True), 0
    if raw==braw: return _result(body, plan['plan_sha256'], False, dry_run=False), 0
    mode=stat.S_IMODE(os.stat(a.config).st_mode)
    pre=_backup(_state_dir(a), raw)   # the file being replaced stays recoverable
    _write_atomic(a.config, braw, digest(raw), mode)
    if _read_bytes(a.config)!=braw: raise PolicyError('post_write_verification_failed')
    return _result(body, plan['plan_sha256'], True, dry_run=False, pre_restore_backup=str(pre)), 0

def main(argv=None):
    p=argparse.ArgumentParser(prog='ai_policy.paseo'); sub=p.add_subparsers(dest='cmd', required=True)
    q=sub.add_parser('check', help='Read-only: compare Paseo agent profiles with policy paseo_profiles')
    q.add_argument('--config', type=Path, default=DEFAULT_PASEO_CONFIG, help='Paseo config.json (default ~/.paseo/config.json)')
    q.add_argument('--policy', help='model-routing.json; defaults to the repository policy')
    q.add_argument('--model-catalog', help='Codex model cache JSON; defaults to CODEX_HOME/models_cache.json')
    q.add_argument('--paseo-models', type=Path, help='Offline JSON of Paseo list_models (provider claude): {"models":[{"id":...}]} or a bare list; reports newer same-family ids')
    s=sub.add_parser('sync', help='Write policy values into managed Paseo profiles. Dry run unless --plan-sha256 is given')
    s.add_argument('--config', type=Path, default=DEFAULT_PASEO_CONFIG, help='Paseo config.json (default ~/.paseo/config.json)')
    s.add_argument('--policy', help='model-routing.json; defaults to the repository policy')
    s.add_argument('--model-catalog', help='Codex model cache JSON; defaults to CODEX_HOME/models_cache.json')
    s.add_argument('--state-dir', type=Path, default=None, help='last-applied state and backups (default ${XDG_STATE_HOME:-~/.local/state}/ai-policy/paseo-sync/<sha256(abs config path)[:8]>)')
    s.add_argument('--include-provisional', action='store_true', help='also create missing provisional profiles')
    s.add_argument('--overwrite', action='append', metavar='ID[,ID...]', help='write these managed profiles even if hand-edited (never overrides refused:*)')
    s.add_argument('--plan-sha256', help='apply the plan whose hash a dry run printed; recomputed and refused on any difference')
    s.add_argument('--restore', metavar='BACKUP_PATH', help='replace the config with a backup from <state-dir>/backups/ (dry run unless --plan-sha256)')
    a=p.parse_args(argv)
    try:
        if a.cmd=='sync':
            if a.restore and (a.include_provisional or a.overwrite): raise PolicyError('restore_incompatible_flags')
            value, code=(run_restore if a.restore else run_sync)(a)
            print(json.dumps(value, sort_keys=True)); return code
        value=check_profiles(load_config(a.policy), _read(a.config), model_catalog=load_codex_model_catalog(a.model_catalog),
                             paseo_models=_read_models(a.paseo_models) if a.paseo_models else None)
    except PolicyError as e:
        print(json.dumps({'schema':1,'error':str(e)}, sort_keys=True)); return 2
    except OSError:
        print(json.dumps({'schema':1,'error':'filesystem_error'}, sort_keys=True)); return 2
    print(json.dumps(value, sort_keys=True))
    return 1 if value['drift'] else 0

if __name__=='__main__': raise SystemExit(main())
