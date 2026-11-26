"""Render and safely apply the three managed global instruction blocks (core, orca, paseo) to a host's global instruction file.

Standalone tool: `python3 -B -m ai_policy.globalblocks render|check|sync|restore`. Sources live in policy/global/. The target file is a user's
instruction file that holds private text outside the managed blocks: this tool never prints file contents and never touches bytes outside the
managed regions."""
import argparse
from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from .bundle import PolicyError, digest, encode
from .paseo import _private_dir, _read_nofollow, _sync_dir

SOURCE_DIR=Path(__file__).resolve().parent.parent/'policy'/'global'
MAX_BYTES=8*1024*1024
HOSTS=('claude', 'codex')
ORDER=('core', 'orca', 'paseo')
NOTE='New sessions load the changed instruction files; running sessions keep the old text.'
# Refusals that need a human decision exit 1; every other error exits 2.
HUMAN_REFUSALS={'unrecognized_block', 'no_managed_block', 'partial_install', 'unexpected_block', 'downgrade_block'}
TOKEN=re.compile(r'<!--\s*ai-agent-policy:')
STRICT=re.compile(r'<!-- (ai-agent-policy:[A-Za-z0-9_-]+):(start|end)(?: version=([0-9A-Za-z][0-9A-Za-z._+-]*))? -->')
BACKUP_NAME=re.compile(r'(.+)\.\d{8}T\d{6}Z\.([0-9a-f]{8})')

# ---- sources and rendering ----------------------------------------------------------------------------------------------------------------
def _source_text(name):
    try: raw=(SOURCE_DIR/name).read_bytes()
    except OSError: raise PolicyError('source_unavailable')
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError: raise PolicyError('source_not_utf8')
    if '\r' in text: raise PolicyError('source_has_cr')
    return text

def load_config(source_dir=None):
    try: cfg=json.loads((Path(source_dir) if source_dir else SOURCE_DIR).joinpath('blocks.json').read_text(encoding='utf-8'))
    except (OSError, ValueError): raise PolicyError('blocks_config_invalid')
    return cfg

def render_block(marker, version, body):
    return '<!-- %s:start version=%s -->\n%s\n<!-- %s:end -->\n'%(marker, version, body.rstrip('\n'), marker)

def marker_of(cfg, name, host):
    """Core carries a per-host marker (a claude core block is never mistaken for a codex one); orca and paseo are shared."""
    return cfg[name]['markers'][host] if name=='core' else cfg[name]['marker']

def selected_blocks(host, cfg=None, with_orca=False):
    """The block names to manage for a host, always in the order core, orca, paseo. The shipped default is core + paseo; orca is opt-in."""
    if host not in HOSTS: raise PolicyError('host_invalid')
    cfg=cfg or load_config()
    try: names=set(cfg['hosts'][host]['default_blocks'])
    except (KeyError, TypeError): raise PolicyError('blocks_config_invalid')
    if not names<=set(ORDER) or 'core' not in names: raise PolicyError('blocks_config_invalid')
    if with_orca: names.add('orca')
    return [n for n in ORDER if n in names]

def render_blocks(host, cfg=None, selected=None):
    """[(name, rendered block text)] for the selected blocks (default: the host's default set) in the fixed order core, orca, paseo."""
    if host not in HOSTS: raise PolicyError('host_invalid')
    cfg=cfg or load_config()
    out=[]
    for name in (selected if selected is not None else selected_blocks(host, cfg)):
        c=cfg[name]; src=c['sources'][host] if 'sources' in c else c['source']
        out.append((name, render_block(marker_of(cfg, name, host), c['version'], _source_text(src))))
    return out

def render(host, cfg=None, selected=None):
    return '\n'.join(text for _, text in render_blocks(host, cfg, selected))

# ---- target reading and scanning ----------------------------------------------------------------------------------------------------------
def _read_target(path, write=True):
    """Target bytes. Symlinks, non-regular files and oversized files are refused (and, when the file may be replaced, hard-linked ones: the
    replace would silently detach the other links); the content is never echoed."""
    try: st=os.lstat(path)
    except OSError: raise PolicyError('target_unavailable')
    if stat.S_ISLNK(st.st_mode): raise PolicyError('target_symlink')
    if not stat.S_ISREG(st.st_mode): raise PolicyError('target_not_regular')
    if st.st_size>MAX_BYTES: raise PolicyError('target_too_large')
    if write and st.st_nlink>1: raise PolicyError('target_hardlinked')
    try:
        fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode): raise PolicyError('target_not_regular')
            if write and st.st_nlink>1: raise PolicyError('target_hardlinked')
            raw=f.read(MAX_BYTES+1)
    except OSError: raise PolicyError('target_unavailable')
    if len(raw)>MAX_BYTES: raise PolicyError('target_too_large')
    return raw

def _decode(raw):
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError: raise PolicyError('target_not_utf8')
    if '\r' in text: raise PolicyError('target_has_cr')
    return text

def _names(host, cfg):
    names={cfg['legacy'][host]['marker']:'legacy', cfg['orca']['marker']:'orca', cfg['paseo']['marker']:'paseo'}
    for h in HOSTS: names[marker_of(cfg, 'core', h)]='core' if h==host else 'foreign_core'
    return names

def scan(text, host, cfg):
    """Completed managed regions [(name, start, end, version)] in file order; structural problems raise. Offsets are character offsets of whole lines,
    end is just after the end marker line's newline."""
    names=_names(host, cfg)
    pos=0; open_=None; done=[]
    for line in text.split('\n'):
        nxt=pos+len(line)+1
        if TOKEN.search(line):
            m=STRICT.fullmatch(line)
            if not m or (m.group(2)=='start')!=(m.group(3) is not None): raise PolicyError('malformed_marker')
            name=names.get(m.group(1))
            if name=='foreign_core': raise PolicyError('host_mismatch')   # this target already carries the other host's core block
            if name is None:
                if open_ is not None: raise PolicyError('nested_markers')
            elif m.group(2)=='start':
                if open_ is not None: raise PolicyError('nested_markers')
                if any(d[0]==name for d in done): raise PolicyError('duplicate_markers')
                open_=(name, pos, m.group(3))
            else:
                if open_ is None or open_[0]!=name: raise PolicyError('unbalanced_markers')
                done.append((name, open_[1], min(nxt, len(text)), open_[2])); open_=None
        pos=nxt
    if open_ is not None: raise PolicyError('unbalanced_markers')
    return done

def classify(regions, selected):
    """none | legacy | current | partial. A managed block of this tool that is present but not selected is refused (unexpected_block)."""
    names=[r[0] for r in regions]
    if not names: return 'none'
    if names==['legacy']: return 'legacy'
    if 'legacy' in names: return 'partial'
    if names==list(selected): return 'current'
    if any(n not in selected for n in names): raise PolicyError('unexpected_block')
    if sorted(names)==sorted(selected): raise PolicyError('out_of_order_markers')
    return 'partial'

def _version_key(v):
    """Comparable release key; a pre-release suffix (e.g. -draft) sorts before the plain release. None when the version is not x.y.z[-suffix]."""
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-(.+))?', v or '')
    return None if not m else (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if m.group(4) else 1)

def block_status(name, host, cfg, region_text, found_version, rendered_text):
    """current: the exact current render. newer: the target block's version is newer than this tool's (applying would downgrade it).
    known: text of an earlier release pinned in blocks.json. unrecognized: anything else (hand-edited, or an unknown/older unpinned text)."""
    if region_text==rendered_text: return 'current'
    found=_version_key(found_version); now=_version_key(cfg[name]['version'])
    if found is not None and now is not None and found>now: return 'newer'
    if digest(_e(region_text)) in cfg[name].get('known_sha256', {}).get(host, []): return 'known'
    return 'unrecognized'

def _outside(text, spans, collapse=False):
    """Text outside the regions: [before, between..., after]. With collapse only [before, after] (a legacy region becomes three blocks)."""
    parts=[]; pos=0
    for s, e in spans: parts.append(text[pos:s]); pos=e
    parts.append(text[pos:])
    return [parts[0], parts[-1]] if collapse else parts

def _build(text, regions, rendered):
    """New text: a lone legacy region becomes the three blocks; three current regions are each replaced in place."""
    if regions[0][0]=='legacy':
        _, s, e, _ = regions[0]
        return text[:s]+'\n'.join(t for _, t in rendered)+text[e:]
    out=[]; pos=0
    for (name, s, e, _), (_, block) in zip(regions, rendered):
        out.append(text[pos:s]); out.append(block); pos=e
    out.append(text[pos:])
    return ''.join(out)

def _line_counts(a, b):
    la=a.splitlines(); lb=b.splitlines(); added=removed=0
    for d in difflib.unified_diff(la, lb, lineterm='', n=0):
        if d.startswith(('+++', '---', '@@')): continue
        if d.startswith('+'): added+=1
        elif d.startswith('-'): removed+=1
    return {'lines_before':len(la), 'lines_after':len(lb), 'lines_added':added, 'lines_removed':removed}

def _e(s): return s.encode('utf-8')

def _region(text, s, e):
    """A region's text, newline-terminated (the end marker may be the last line of a file that lacks a trailing newline)."""
    r=text[s:e]
    return r if r.endswith('\n') else r+'\n'

def analyze(raw, host, cfg=None, selected=None):
    cfg=cfg or load_config()
    selected=list(selected) if selected is not None else selected_blocks(host, cfg)
    text=_decode(raw)
    regions=scan(text, host, cfg)
    return text, regions, classify(regions, selected), cfg

# ---- check --------------------------------------------------------------------------------------------------------------------------------
def run_check(a):
    raw=_read_target(a.target, write=False)
    selected=selected_blocks(a.host, None, a.with_orca)
    text, regions, state, cfg=analyze(raw, a.host, None, selected)
    rendered=render_blocks(a.host, cfg, selected)
    blocks={n:{'present':False, 'up_to_date':False, 'version_expected':cfg[n]['version'], 'version_found':None} for n in selected}
    legacy={'present':False, 'known':None}
    for name, s, e, v in regions:
        if name=='legacy':
            h=digest(_e(_region(text, s, e))); legacy={'present':True, 'known':h in cfg['legacy'][a.host]['known_sha256'], 'sha256':h, 'version_found':v}
        else:
            st=block_status(name, a.host, cfg, _region(text, s, e), v, dict(rendered)[name])
            blocks[name].update(present=True, version_found=v, status=st, up_to_date=text[s:e]==dict(rendered)[name])
    if state=='legacy' and not legacy['known']: state='unrecognized'
    up=state=='current' and all(b['up_to_date'] for b in blocks.values())
    return {'schema':1, 'operation':'check', 'host':a.host, 'selected_blocks':selected, 'target':os.path.abspath(a.target), 'state':state, 'up_to_date':up,
            'blocks':blocks, 'legacy':legacy, 'target_sha256':digest(raw)}, (0 if up else 1)

# ---- sync plan ----------------------------------------------------------------------------------------------------------------------------
def plan_sync(raw, target, host, cfg, *, selected=None, overwrite_unrecognized=False):
    selected=list(selected) if selected is not None else selected_blocks(host, cfg)
    text, regions, state, cfg=analyze(raw, host, cfg, selected)
    if state=='none': raise PolicyError('no_managed_block')
    if state=='partial': raise PolicyError('partial_install')
    rendered=render_blocks(host, cfg, selected)
    legacy=None
    if state=='legacy':
        _, s, e, v = regions[0]
        h=digest(_e(_region(text, s, e))); known=h in cfg['legacy'][host]['known_sha256']
        if not known and not overwrite_unrecognized: raise PolicyError('unrecognized_block')
        legacy={'version_found':v, 'sha256':h, 'known':known, 'lines':_region(text, s, e).count('\n')}
    new_text=_build(text, regions, rendered)
    new_raw=_e(new_text)
    # Outside-bytes guard: everything outside the managed regions must be byte-identical after the rewrite.
    nregions=scan(new_text, host, cfg)
    collapse=state=='legacy'
    outside=_outside(text, [(s, e) for _, s, e, _ in regions], collapse)
    if classify(nregions, selected)!='current' or _outside(new_text, [(s, e) for _, s, e, _ in nregions], collapse)!=outside:
        raise PolicyError('outside_modified')
    if [new_text[s:e] for _, s, e, _ in nregions]!=[t for _, t in rendered]: raise PolicyError('render_mismatch')
    old_span=text[regions[0][1]:regions[-1][2]]
    new_span=new_text[nregions[0][1]:nregions[-1][2]]
    blocks=[]; statuses=[]
    for i, (name, block) in enumerate(rendered):
        if state=='legacy': action='add'; status='absent'
        else:
            _, s, e, v = regions[i]; status=block_status(name, host, cfg, _region(text, s, e), v, block); action='unchanged' if text[s:e]==block else 'update'
        statuses.append(status)
        blocks.append({'name':name, 'marker':marker_of(cfg, name, host), 'version':cfg[name]['version'], 'action':action, 'status':status, 'lines':block.count('\n')})
    if not overwrite_unrecognized:
        if 'newer' in statuses: raise PolicyError('downgrade_block')
        if 'unrecognized' in statuses: raise PolicyError('unrecognized_block')
    body={'schema':1, 'operation':'sync', 'host':host, 'target':os.path.abspath(target), 'selected_blocks':selected, 'state':state, 'overwrite_unrecognized':bool(overwrite_unrecognized),
          'legacy':legacy, 'blocks':blocks, 'changes':sum(b['action']!='unchanged' for b in blocks),
          'diff':_line_counts(old_span, new_span),
          'region_before_sha256':digest(_e(old_span)), 'region_after_sha256':digest(_e(new_span)),
          'file_before_sha256':digest(raw), 'file_after_sha256':digest(new_raw)}
    return {'body':body, 'plan_sha256':digest(encode(body)), 'new_raw':new_raw, 'new_text':new_text, 'rendered':rendered, 'cfg':cfg, 'host':host, 'selected':selected, 'outside':outside, 'collapse':collapse}

def _verify_hash(given, plan_sha256):
    if given is None: return
    if not isinstance(given, str) or not re.fullmatch('[0-9a-f]{64}', given): raise PolicyError('plan_sha256_invalid')
    if given!=plan_sha256: raise PolicyError('plan_sha256_mismatch')

def _result(body, plan_sha256, applied, **extra):
    out=dict(body); out.pop('target', None)
    out.update(plan_sha256=plan_sha256, dry_run=extra.pop('dry_run'), applied=applied)
    out.update(extra)
    if applied: out['note']=NOTE
    return out

# ---- state dir, backups, atomic write -----------------------------------------------------------------------------------------------------
def default_state_dir(target):
    """Per-user state and backup directory keyed by the target's absolute path; never inside a repository. Backups are full copies of the target
    and contain its private text."""
    xdg=os.environ.get('XDG_STATE_HOME')
    base=Path(xdg) if xdg and os.path.isabs(xdg) else Path.home()/'.local'/'state'
    return base/'ai-policy'/'global-blocks'/digest(os.path.abspath(target).encode('utf-8'))[:8]

def _state_dir(a): return Path(a.state_dir) if a.state_dir is not None else default_state_dir(a.target)

def _backup(state_dir, target, raw):
    """Private copy of the target bytes made before any write, plus a 0600 sidecar `<backup>.target` naming the target it belongs to (restore
    requires it to match). Never printed."""
    _private_dir(state_dir, 'state_dir_unsafe', create=True)
    b=Path(state_dir)/'backups'
    if not _private_dir(b, 'backups_dir_unsafe'): os.mkdir(b, 0o700); os.chmod(b, 0o700)
    path=b/('%s.%s.%s'%(Path(target).name, datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'), digest(raw)[:8]))
    owner=os.path.abspath(target).encode('utf-8'); side=Path(str(path)+'.target')
    try: fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        # same name means same second and same content: reusable only for the very same target
        if _read_nofollow(path, 'backup_exists')!=raw: raise PolicyError('backup_exists')
        try: owned=_read_nofollow(side, 'backup_exists')
        except PolicyError: owned=None
        if owned is not None and owned!=owner: raise PolicyError('backup_exists')
        if owned is None: _write_private(side, owner, b)
        return path
    try:
        with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fchmod(f.fileno(), 0o600); os.fsync(f.fileno())
        _write_private(side, owner, b)
    except BaseException:
        for x in (path, side):
            try: os.unlink(x)
            except OSError: pass
        raise
    return path

def _write_private(path, data, parent):
    fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f: f.write(data); f.flush(); os.fchmod(f.fileno(), 0o600); os.fsync(f.fileno())
    _sync_dir(parent)

def _before_replace(path):
    """Test seam: runs after the temp file is complete and before the final sha re-check."""

def _write_atomic(path, data, expected_sha256, mode):
    """Temp file in the same directory, fsync, mode, sha re-check of the target, os.replace. Leaves no temp file on any failure."""
    path=Path(path)
    if os.path.islink(path): raise PolicyError('target_symlink')
    tmp=path.parent/('.%s.%s.tmp'%(path.name, secrets.token_hex(6)))
    fd=os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fchmod(f.fileno(), mode); os.fsync(f.fileno())
        _before_replace(path)
        if digest(_read_target(path))!=expected_sha256: raise PolicyError('target_changed')
        os.replace(tmp, path); tmp=None
        _sync_dir(path.parent)
    finally:
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass

def _is_replaced(path, new_raw):
    try: return _read_target(path)==new_raw
    except PolicyError: return False

def _verify_written(path, plan):
    """Re-read the replaced file: it must equal the expected bytes, its regions must equal the rendered blocks and the outside must be the original."""
    after=_read_target(path)
    if after!=plan['new_raw']: raise PolicyError('post_write_verification_failed')
    text, regions, state, _ = analyze(after, plan['host'], plan['cfg'], plan['selected'])
    if state!='current' or [text[s:e] for _, s, e, _ in regions]!=[t for _, t in plan['rendered']] or \
            _outside(text, [(s, e) for _, s, e, _ in regions], plan['collapse'])!=plan['outside']:
        raise PolicyError('post_write_verification_failed')

def run_sync(a):
    cfg=load_config()
    raw=_read_target(a.target)
    plan=plan_sync(raw, a.target, a.host, cfg, selected=selected_blocks(a.host, cfg, a.with_orca), overwrite_unrecognized=a.overwrite_unrecognized)
    _verify_hash(a.plan_sha256, plan['plan_sha256'])
    body=plan['body']
    if a.plan_sha256 is None: return _result(body, plan['plan_sha256'], False, dry_run=True), 0
    if plan['new_raw']==raw: return _result(body, plan['plan_sha256'], False, dry_run=False), 0
    mode=stat.S_IMODE(os.stat(a.target).st_mode)
    backup=_backup(_state_dir(a), a.target, raw)
    try: _write_atomic(a.target, plan['new_raw'], digest(raw), mode)
    except (PolicyError, OSError):
        if not _is_replaced(a.target, plan['new_raw']): raise   # failed before the replace: a plain error, nothing changed
        raise_after=True
    else: raise_after=False
    # The target has been replaced: any failure from here on is reported with that fact and the backup.
    try:
        if raise_after: raise PolicyError('post_write_verification_failed')
        _verify_written(a.target, plan)
    except (PolicyError, OSError) as e:
        return _result(body, plan['plan_sha256'], True, dry_run=False, backup=str(backup),
                       error=str(e) if isinstance(e, PolicyError) else 'filesystem_error'), 2
    return _result(body, plan['plan_sha256'], True, dry_run=False, backup=str(backup)), 0

# ---- restore ------------------------------------------------------------------------------------------------------------------------------
def _resolve_backup(state_dir, arg, target):
    """Only a regular, correctly named, uncorrupted file directly inside <state-dir>/backups/ (no symlinks, no traversal)."""
    if not _private_dir(state_dir, 'state_dir_unsafe'): raise PolicyError('backup_outside_backups_dir')
    bdir=Path(state_dir)/'backups'
    if not _private_dir(bdir, 'backups_dir_unsafe'): raise PolicyError('backup_outside_backups_dir')
    cand=Path(os.path.abspath(arg))
    real=Path(os.path.realpath(bdir))
    if Path(os.path.realpath(cand.parent))!=real: raise PolicyError('backup_outside_backups_dir')
    m=BACKUP_NAME.fullmatch(cand.name)
    if not m or m.group(1)!=Path(target).name: raise PolicyError('backup_name_invalid')
    path=real/cand.name
    try: st=os.lstat(path)
    except OSError: raise PolicyError('backup_unavailable')
    if stat.S_ISLNK(st.st_mode): raise PolicyError('backup_symlink')
    if not stat.S_ISREG(st.st_mode): raise PolicyError('backup_not_regular')
    braw=_read_nofollow(path, 'backup_unavailable')
    if digest(braw)[:8]!=m.group(2): raise PolicyError('backup_corrupt')
    try: owner=_read_nofollow(Path(str(path)+'.target'), 'backup_target_missing')
    except PolicyError: raise PolicyError('backup_target_missing')
    if owner!=os.path.abspath(target).encode('utf-8'): raise PolicyError('backup_target_mismatch')   # a backup of another file never restores here
    return path, braw

def run_restore(a):
    path, braw=_resolve_backup(_state_dir(a), a.backup, a.target)
    raw=_read_target(a.target)   # the file being replaced may be broken; only its bytes matter
    body={'schema':1, 'operation':'restore', 'target':os.path.abspath(a.target), 'target_sha256':digest(raw), 'backup':path.name, 'backup_sha256':digest(braw), 'changes':int(raw!=braw)}
    plan_sha256=digest(encode(body))
    _verify_hash(a.plan_sha256, plan_sha256)
    if a.plan_sha256 is None: return _result(body, plan_sha256, False, dry_run=True), 0
    if raw==braw: return _result(body, plan_sha256, False, dry_run=False), 0
    mode=stat.S_IMODE(os.stat(a.target).st_mode)
    pre=_backup(_state_dir(a), a.target, raw)   # the file being replaced stays recoverable
    try: _write_atomic(a.target, braw, digest(raw), mode)
    except (PolicyError, OSError):
        if not _is_replaced(a.target, braw): raise
    try:
        if _read_target(a.target)!=braw: raise PolicyError('post_write_verification_failed')
    except PolicyError as e:
        return _result(body, plan_sha256, True, dry_run=False, pre_restore_backup=str(pre), error=str(e)), 2
    return _result(body, plan_sha256, True, dry_run=False, pre_restore_backup=str(pre)), 0

# ---- CLI ----------------------------------------------------------------------------------------------------------------------------------
def main(argv=None):
    p=argparse.ArgumentParser(prog='ai_policy.globalblocks'); sub=p.add_subparsers(dest='cmd', required=True)
    r=sub.add_parser('render', help='Print the three rendered blocks (core, orca, paseo) for a host')
    r.add_argument('--host', required=True, choices=HOSTS); r.add_argument('--with-orca', action='store_true', help='also render the orca block (not part of the default set)')
    h=sub.add_parser('hashes', help='Print the sha256 of every currently rendered block (to pin a release in blocks.json known_sha256)')
    h.add_argument('--host', required=True, choices=HOSTS)
    c=sub.add_parser('check', help='Read-only: report the managed-block state of a target file (exit 0 current, 1 needs change, 2 error)')
    c.add_argument('--host', required=True, choices=HOSTS); c.add_argument('--target', required=True, type=Path)
    c.add_argument('--with-orca', action='store_true', help='manage the orca block too (default set: core + paseo)')
    s=sub.add_parser('sync', help='Replace the legacy block by the three blocks, or update them in place. Dry run unless --plan-sha256 is given')
    s.add_argument('--host', required=True, choices=HOSTS); s.add_argument('--target', required=True, type=Path)
    s.add_argument('--with-orca', action='store_true', help='manage the orca block too (default set: core + paseo)')
    s.add_argument('--state-dir', type=Path, default=None, help='backups (default ${XDG_STATE_HOME:-~/.local/state}/ai-policy/global-blocks/<sha256(abs target path)[:8]>)')
    s.add_argument('--overwrite-unrecognized', action='store_true', help='replace a legacy block whose text is not a known release')
    s.add_argument('--plan-sha256', help='apply the plan whose hash a dry run printed; recomputed and refused on any difference')
    t=sub.add_parser('restore', help='Replace the target with a backup from <state-dir>/backups/. Dry run unless --plan-sha256 is given')
    t.add_argument('--target', required=True, type=Path); t.add_argument('--backup', required=True, type=Path)
    t.add_argument('--state-dir', type=Path, default=None, help='same default as sync')
    t.add_argument('--plan-sha256', help='apply the plan whose hash a dry run printed')
    a=p.parse_args(argv)
    try:
        if a.cmd=='render':
            print(render(a.host, None, selected_blocks(a.host, None, a.with_orca)), end=''); return 0
        if a.cmd=='hashes':
            print(json.dumps({'schema':1, 'host':a.host, 'blocks':{n:digest(_e(t)) for n, t in render_blocks(a.host, None, list(ORDER))}}, sort_keys=True, indent=2)); return 0
        value, code={'check':run_check, 'sync':run_sync, 'restore':run_restore}[a.cmd](a)
    except PolicyError as e:
        print(json.dumps({'schema':1, 'error':str(e)}, sort_keys=True)); return 1 if str(e) in HUMAN_REFUSALS else 2
    except OSError:
        print(json.dumps({'schema':1, 'error':'filesystem_error'}, sort_keys=True)); return 2
    print(json.dumps(value, sort_keys=True, indent=2))
    return code

if __name__=='__main__': raise SystemExit(main())
