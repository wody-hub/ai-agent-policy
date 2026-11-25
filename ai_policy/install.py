"""Read-only planning and recoverable per-file installation (no multi-file atomicity).

Private backups contain exact bytes/modes/existence. Automatic startup does not
recover journals or remove locks. All public diagnostics are stable reason codes.
"""
from dataclasses import dataclass
from typing import NamedTuple
import base64
import ctypes
from contextvars import ContextVar
import errno
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from .bundle import PolicyError, adapter, digest, encode, load_bundle, read_regular, relative, safe_path

class Layout(NamedTuple):
    """Install paths and adapter markers of one bundle flavor; flavors never share a root or a marker."""
    flavor: str
    root: str
    state: str
    current: str
    entry: str
    runtime: str
    begin: bytes
    end: bytes
    marker: bytes

def layout(flavor='orca'):
    if flavor not in ('orca','paseo'):raise PolicyError('unsupported_flavor')
    root='.config/ai-agent-policy/'+flavor
    return Layout(flavor,root,root+'/installation.json',root+'/current.json',root+'/entrypoint.py',root+'/runtime.json',
                  ('<!-- ai-agent-policy:%s-adapter:begin schema=1 -->'%flavor).encode(),
                  ('<!-- ai-agent-policy:%s-adapter:end -->'%flavor).encode(),
                  ('ai-agent-policy:%s-adapter:'%flavor).encode())

# Module-level names keep the Orca layout (original import surface).
ORCA=layout('orca')
ROOT,STATE,CURRENT,ENTRY,RUNTIME,BEGIN,END=ORCA.root,ORCA.state,ORCA.current,ORCA.entry,ORCA.runtime,ORCA.begin,ORCA.end
TARGETS={'.codex/AGENTS.md':'codex','.claude/CLAUDE.md':'claude'}
ABSENT={'exists':False}

def raw(image):
    if not image.get('exists'): return b''
    try:
        data=base64.b64decode(image['data'],validate=True)
        if digest(data)!=image['sha256'] or type(image['mode']) is not int or image['mode'] & ~0o777 or image['mode'] & 0o022:
            raise ValueError()
        return data
    except (KeyError,TypeError,ValueError): raise PolicyError('image_corrupt')

def image(data,mode=0o600):
    if data is None:return dict(ABSENT)
    return {'exists':True,'mode':mode,'sha256':digest(data),'data':base64.b64encode(data).decode('ascii')}

def capture(home,name):
    relative(name);p=safe_path(home/name)
    if not p.exists():return dict(ABSENT)
    data=read_regular(p)
    return image(data,stat.S_IMODE(p.lstat().st_mode))

def parse_block(data,L=ORCA):
    marker=L.marker
    if marker not in data:return None
    if data.count(marker)!=2 or data.count(L.begin)!=1 or data.count(L.end)!=1:
        raise PolicyError('malformed_markers')
    start=data.index(L.begin);end=data.index(L.end)+len(L.end)
    if start>=end-len(L.end):raise PolicyError('malformed_markers')
    if data[end:end+2]==b'\r\n':end+=2
    elif data[end:end+1]==b'\n':end+=1
    return start,end,data[start:end]

def inverse_adapter(now,pre,post,L=ORCA):
    """Inverse a dedicated block, retaining every later unmanaged byte."""
    n=raw(now);a=raw(pre);b=raw(post)
    ns=parse_block(n,L);bs=parse_block(b,L);ass=parse_block(a,L)
    if (ns[2] if ns else None)!=(bs[2] if bs else None):raise PolicyError('managed_drift')
    if now.get('exists') and post.get('exists') and now['mode']!=post['mode']:raise PolicyError('mode_drift')
    if now['exists'] and not post['exists'] and pre['exists'] and now['mode']!=pre['mode']:
        raise PolicyError('mode_conflict')
    if now==post:return pre
    if bs:
        start=ns[0]
        # Invert only the exact separator recorded between original bytes and
        # the inserted block, when that prefix is still intact.
        if not ass and a and not a.endswith(b'\n') and b.startswith(a):
            sep=b[len(a):bs[0]]
            if sep in (b'\n',b'\r\n') and n[:start]==a+sep:start-=len(sep)
        out=n[:start]+(ass[2] if ass else b'')+n[ns[1]:]
    elif ass:
        sep=b'' if not n or n.endswith(b'\n') else b'\n'
        out=n+sep+ass[2]
    else:raise PolicyError('unmanaged_conflict')
    return image(out,now.get('mode',pre.get('mode',0o600)))

def home_path(home):
    if not Path(home).is_absolute():raise PolicyError('home_must_be_absolute')
    # The explicit home itself is canonicalized (macOS /var -> /private/var).
    # Every managed target and parent under it is still checked without following links.
    original=Path(home)
    if original.is_symlink():raise PolicyError('symlink')
    p=original.resolve()
    safe_path(p)
    if not p.is_dir():raise PolicyError('home_missing')
    return p

def read_json(path, *, private=False):
    try:
        value=json.loads(read_regular(path,private=private))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,TypeError):raise PolicyError('metadata_invalid')

def retained_runtime(home,L=ORCA):
    entry=capture(home,L.entry);runtime=capture(home,L.runtime)
    if not entry['exists'] and not runtime['exists']:return None
    if not entry['exists'] or not runtime['exists']:raise PolicyError('ownership_missing')
    safe_path(home/L.runtime,private=True)
    try:
        m=json.loads(raw(runtime));h=m['bundle_sha256']
        if m['schema']!=1 or not re.fullmatch('[0-9a-f]{64}',h) or m['entrypoint_sha256']!=entry['sha256'] or entry['mode']!=0o700:
            raise PolicyError('runtime_drift')
        bundle=load_bundle(home/L.root/'generations'/h/'policy/bundle.json')
        if bundle.sha256!=h or bundle.flavor!=L.flavor:raise PolicyError('runtime_drift')
        return m
    except (KeyError,TypeError,ValueError):raise PolicyError('runtime_drift')

def installed_state(home,L=ORCA):
    safe_path(home/L.root/'transaction.json')
    if (home/L.root/'transaction.json').exists():raise PolicyError('recovery_required')
    s=capture(home,L.state);c=capture(home,L.current)
    if not s['exists'] and not c['exists']:
        retained_runtime(home,L)
        for name in TARGETS:
            if parse_block(raw(capture(home,name)),L):raise PolicyError('adoption_required')
        return None
    if not s['exists'] or not c['exists']:raise PolicyError('partial_installation')
    safe_path(home/L.state,private=True);safe_path(home/L.current,private=True)
    try:
        selector=json.loads(raw(c));state=json.loads(raw(s))
        if selector['schema']!=1 or state['schema']!=1 or selector['installation_sha256']!=digest(raw(s)):
            raise PolicyError('manifest_drift')
        h=selector['bundle_sha256']
        if not re.fullmatch('[0-9a-f]{64}',h) or state['bundle_sha256']!=h:raise PolicyError('manifest_drift')
        generation=home/L.root/'generations'/h
        bundle=load_bundle(generation/'policy/bundle.json')
        if bundle.sha256!=h or bundle.flavor!=L.flavor:raise PolicyError('generation_drift')
        retained=retained_runtime(home,L)
        if retained is None or retained['bundle_sha256']!=h:raise PolicyError('runtime_drift')
        records=state['targets']
        if not isinstance(records,dict) or set(records)!={*TARGETS,L.entry,L.runtime}:raise PolicyError('manifest_drift')
        for name,r in records.items():
            now=capture(home,name);raw(r['before']);raw(r['after'])
            if name in TARGETS:
                expected=parse_block(raw(r['after']),L);actual=parse_block(raw(now),L)
                if expected is None or actual is None or expected[2]!=actual[2]:raise PolicyError('managed_drift')
                if now.get('mode')!=r['after'].get('mode'):raise PolicyError('mode_drift')
            elif now!=r['after']:raise PolicyError('runtime_drift')
        return state
    except (KeyError,TypeError,ValueError):raise PolicyError('manifest_invalid')

def check(home,flavor='orca'):
    L=layout(flavor)
    result={'state':'absent','files_valid':False,'ownership_valid':False,'drift':False,'partial':False,
            'hook_configured':False,'load_verified':None,'origin_verified':None,'enforcement_verified':None,
            'codex_shadowed':False,'reason':'not_installed'}
    try:
        home=home_path(home)
        override=capture(home,'.codex/AGENTS.override.md')
        result['codex_shadowed']=bool(raw(override))
        state=installed_state(home,L)
        if state:
            result.update(state='installed',files_valid=True,ownership_valid=True,reason='files_verified')
    except PolicyError as e:
        reason=str(e);partial=reason in ('recovery_required','partial_installation')
        result.update(state='partial' if partial else 'invalid',partial=partial,drift=not partial,reason=reason)
    return result

# The bootstrap is the fixed entrypoint, with isolated Python before any imports.
# It verifies the complete selected bundle BEFORE adding its directory to sys.path.
def launcher(flavor='orca'):
    script='''import hashlib,json,os,pathlib,stat,sys
sys.dont_write_bytecode=True
root=pathlib.Path(__file__).absolute().parent
try:
 def secure(p):
  for q in reversed((p,*p.parents)):
   s=q.lstat()
   if stat.S_ISLNK(s.st_mode) or s.st_uid not in (0,os.getuid()) or (s.st_mode & 0o022 and not (stat.S_ISDIR(s.st_mode) and s.st_mode & stat.S_ISVTX)): raise ValueError()
  if not stat.S_ISREG(p.lstat().st_mode): raise ValueError()
 def read(p):
  secure(p)
  if p.stat().st_size>8388608: raise ValueError()
  return p.read_bytes()
 if (root/'transaction.json').is_symlink() or (root/'transaction.json').exists(): raise ValueError()
 retained=json.loads(read(root/'runtime.json'))
 h=retained['bundle_sha256']
 if retained['schema']!=1 or hashlib.sha256(read(root/'entrypoint.py')).hexdigest()!=retained['entrypoint_sha256']:raise ValueError()
 if len(h)!=64 or any(c not in '0123456789abcdef' for c in h): raise ValueError()
 gen=root/'generations'/h
 data=read(gen/'policy/bundle.json')
 if hashlib.sha256(data).hexdigest()!=h: raise ValueError()
 m=json.loads(data)
 if m['schema']!=1 or m['installer_schema']!=1:raise ValueError()
 sources={}
 for name,want in m['files'].items():
  p=pathlib.PurePosixPath(name)
  if p.is_absolute() or '..' in p.parts or str(p)!=name:raise ValueError()
  source=read(gen/name)
  if hashlib.sha256(source).hexdigest()!=want:raise ValueError()
  sources[name]=source
except (OSError,ValueError,KeyError,TypeError):
 print('installed_runtime_invalid',file=sys.stderr);sys.exit(30)
import importlib.abc,importlib.util
class VerifiedSource(importlib.abc.MetaPathFinder,importlib.abc.Loader):
 def filename(self,fullname):
  return 'ai_policy/__init__.py' if fullname=='ai_policy' else fullname.replace('.', '/')+'.py'
 def find_spec(self,fullname,path=None,target=None):
  if fullname!='ai_policy' and not fullname.startswith('ai_policy.'):return None
  if self.filename(fullname) not in sources:raise ImportError('unmanifested_module')
  return importlib.util.spec_from_loader(fullname,self,is_package=fullname=='ai_policy')
 def create_module(self,spec):return None
 def exec_module(self,module):
  name=self.filename(module.__name__);module.__file__=str(gen/name);module.__cached__=None
  exec(compile(sources[name],module.__file__,'exec',dont_inherit=True),module.__dict__)
sys.meta_path.insert(0,VerifiedSource())
from ai_policy.__main__ import main
raise SystemExit(main(installed_home=root.parents[2]))
'''
    # The Orca launcher bytes are unchanged; a Paseo launcher selects its flavor explicitly.
    if flavor=='paseo':script=script.replace('main(installed_home=root.parents[2])',"main(installed_home=root.parents[2],flavor='paseo')")
    elif flavor!='orca':raise PolicyError('unsupported_flavor')
    return ('#!'+sys.executable+' -I\n'+script).encode()

@dataclass
class Plan:
    operation: str
    home: Path
    changes: list
    guards: dict
    bundle_path: Path | None=None
    backup_id: str | None=None
    bundle_sha256: str | None=None
    flavor: str='orca'

    @property
    def sha256(self):
        body={'schema':1,'operation':self.operation,'home':str(self.home),
              'changes':self.changes,'guards':self.guards,'bundle_sha256':self.bundle_sha256,
              'backup_id':self.backup_id}
        if self.flavor!='orca':body['flavor']=self.flavor  # Orca plan digests keep their original shape
        return digest(encode(body))

    def public(self):
        return {'schema':1,'operation':self.operation,'changed':bool(self.changes),
                **({'flavor':self.flavor} if self.flavor!='orca' else {}),
                'changes':[{'path':x['path'],'action':'replace' if x['post']['exists'] else 'delete',
                            'before_sha256':x['pre'].get('sha256'),'after_sha256':x['post'].get('sha256')}
                           for x in self.changes],
                'plan_sha256':self.sha256}

def backup_read(home,ident,L=ORCA):
    if not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{32}',ident):raise PolicyError('backup_id_invalid')
    base=home/L.root/'backups'/ident;safe_path(base,private=True)
    data=read_regular(base/'backup.json',private=True)
    checksum=read_regular(base/'sha256',private=True)
    if checksum!=digest(data).encode()+b'\n':raise PolicyError('backup_corrupt')
    try:
        b=json.loads(data)
        if b['schema']!=1 or b['id']!=ident or b['home']!=str(home) or not isinstance(b['changes'],list):raise ValueError()
        names=set()
        for c in b['changes']:
            name=relative(c['path'])
            common='orca-common' if L.flavor=='orca' else 'paseo-common'
            adapters='(?:codex|claude)' if L.flavor=='orca' else 'paseo-(?:codex|claude)'
            allowed=name in TARGETS or name in (L.entry,L.runtime,L.state,L.current) or re.fullmatch(re.escape(L.root)+r'/generations/[0-9a-f]{64}/(?:policy/(?:bundle.json|'+common+r'.md|adapters/'+adapters+r'.md)|ai_policy/(?:__init__|__main__|bundle|context|install).py)',name)
            if not allowed or name in names:raise ValueError()
            names.add(name);raw(c['pre']);raw(c['post'])
        return b
    except (ValueError,TypeError,KeyError):raise PolicyError('backup_corrupt')

def plan(operation,home,bundle=None,backup_id=None,flavor='orca'):
    L=layout(flavor)
    home=home_path(home)
    state=installed_state(home,L)
    guards={};changes=[];bundle_hash=None
    def observe(name):
        if name not in guards:guards[name]=capture(home,name)
        return guards[name]
    def put(name,post,kind='full'):
        pre=observe(name)
        if pre!=post:changes.append({'path':name,'pre':pre,'post':post,'kind':kind})
    for name in (*TARGETS,L.entry,L.runtime,L.state,L.current):observe(name)
    if operation=='install':
        if bundle is None:raise PolicyError('bundle_required')
        b=load_bundle(Path(bundle))
        if b.flavor!=flavor:raise PolicyError('bundle_flavor_mismatch')
        bundle_hash=b.sha256
        gen=L.root+'/generations/'+b.sha256
        files={**b.files,'policy/bundle.json':read_regular(bundle)}
        for name,data in sorted(files.items()):
            existing=observe(gen+'/'+name)
            post=image(data)
            if existing['exists'] and existing!=post:raise PolicyError('generation_conflict')
            put(gen+'/'+name,post,'generation')
        records={}
        for name,host in TARGETS.items():
            before=observe(name);data=raw(before);parsed=parse_block(data,L)
            if parsed and state is None:raise PolicyError('adoption_required')
            body=adapter(b,host,home)
            nl=b'\r\n' if b'\r\n' in data else b'\n'
            block=L.begin+nl+body.replace(b'\r\n',b'\n').replace(b'\n',nl)+L.end+nl
            if parsed:out=data[:parsed[0]]+block+data[parsed[1]:]
            else:out=data+(b'' if not data or data.endswith(b'\n') else nl)+block
            post=image(out,before.get('mode',0o600))
            records[name]={'before':state['targets'][name]['before'] if state else before,'after':post}
            put(name,post,'adapter')
        before=observe(L.entry);post=image(launcher(flavor),0o700)
        if before['exists'] and state is None and retained_runtime(home,L) is None:raise PolicyError('adoption_required')
        records[L.entry]={'before':state['targets'][L.entry]['before'] if state else before,'after':post}
        put(L.entry,post)
        before=observe(L.runtime)
        post=image(encode({'schema':1,'bundle_sha256':b.sha256,'entrypoint_sha256':digest(launcher(flavor))}))
        records[L.runtime]={'before':state['targets'][L.runtime]['before'] if state else before,'after':post}
        put(L.runtime,post)
        newstate={'schema':1,'component_version':b.manifest['version'],'bundle_sha256':b.sha256,
                  'source_commit':b.manifest['source_commit'],'targets':records}
        # Keep original postimage records on a same-bundle no-op, even if new
        # unmanaged text was appended. It is deliberately not adopted as owned.
        if state and state['bundle_sha256']==b.sha256:
            newstate=state
        data=encode(newstate);put(L.state,image(data))
        put(L.current,image(encode({'schema':1,'bundle_sha256':b.sha256,'installation_sha256':digest(data)})))
    elif operation=='remove':
        if state:
            bundle_hash=state['bundle_sha256']
            for name,record in state['targets'].items():
                if name in (L.entry,L.runtime):continue # retained offline installer, no active selector
                now=observe(name)
                post=inverse_adapter(now,record['before'],record['after'],L) if name in TARGETS else record['before']
                put(name,post,'adapter' if name in TARGETS else 'full')
            put(L.state,dict(ABSENT));put(L.current,dict(ABSENT))
    elif operation=='restore':
        b=backup_read(home,backup_id,L)
        for suffix in ('backup.json','sha256'):observe(L.root+'/backups/'+backup_id+'/'+suffix)
        for c in b['changes']:
            if c['kind']=='generation':continue # immutable history retained
            now=observe(c['path'])
            if c['path'] in TARGETS:post=inverse_adapter(now,c['pre'],c['post'],L)
            else:
                if now!=c['post']:raise PolicyError('restore_conflict')
                post=c['pre']
            put(c['path'],post,c['kind'])
    else:raise PolicyError('operation_invalid')
    # current selector always switches last; no multi-file atomicity claimed.
    changes.sort(key=lambda c:c['path']==L.current)
    if changes:
        _native_functions()
        def device(path):
            while not path.exists():path=path.parent
            return path.stat().st_dev
        component_device=device(home/L.root)
        if any(device(home/c['path'])!=component_device for c in changes):raise PolicyError('cross_device_unsupported')
    return Plan(operation,home,changes,guards,Path(bundle) if bundle else None,backup_id,bundle_hash,flavor)

_TRANSITION=ContextVar('ai_policy_kernel_transition',default=None)

def file_identity(path):
    try:s=path.lstat();return (s.st_dev,s.st_ino)
    except FileNotFoundError:return None

def _native_functions():
    """No fallback to lossy rename. Symbol inspection is read-only at plan time."""
    lib=ctypes.CDLL(None,use_errno=True)
    if getattr(lib,'link',None) is None:raise PolicyError('atomic_mutation_unsupported')
    if sys.platform=='darwin':
        fn=getattr(lib,'renamex_np',None)
        if fn is None:raise PolicyError('atomic_mutation_unsupported')
        fn.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
        return fn,'darwin'
    if sys.platform.startswith('linux'):
        fn=getattr(lib,'renameat2',None)
        if fn is None:raise PolicyError('atomic_mutation_unsupported')
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
        return fn,'linux'
    raise PolicyError('atomic_mutation_unsupported')

def _native_rename(src,dst,exchange):
    fn,platform=_native_functions()
    if platform=='darwin':rc=fn(os.fsencode(src),os.fsencode(dst),2 if exchange else 4)
    else:rc=fn(-100,os.fsencode(src),-100,os.fsencode(dst),2 if exchange else 1)
    if rc:
        err=ctypes.get_errno()
        if err in (errno.ENOSYS,errno.ENOTSUP,errno.EXDEV,errno.EINVAL):raise PolicyError('atomic_mutation_unsupported')
        if err==errno.EEXIST:raise FileExistsError(err,'destination_exists')
        raise OSError(err,'atomic_mutation_failed')
    callback=_TRANSITION.get()
    if callback is not None:callback('exchange' if exchange else 'move',Path(src),Path(dst))

def atomic_create(src,dst):
    fn=ctypes.CDLL(None,use_errno=True).link
    fn.argtypes=[ctypes.c_char_p,ctypes.c_char_p];fn.restype=ctypes.c_int
    if fn(os.fsencode(src),os.fsencode(dst)):
        err=ctypes.get_errno()
        if err==errno.EEXIST:raise FileExistsError(err,'destination_exists')
        raise OSError(err,'atomic_creation_failed')
    callback=_TRANSITION.get()
    if callback is not None:callback('create',Path(src),Path(dst))

def atomic_exchange(src,dst):
    _native_rename(src,dst,True)

def atomic_move(src,dst):
    _native_rename(src,dst,False)

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)

def mkdirs(path):
    if path.exists():safe_path(path);return
    mkdirs(path.parent)
    path.mkdir(mode=0o700);sync_dir(path.parent)

def exclusive_file(path,data,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),mode)
    with os.fdopen(fd,'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    sync_dir(path.parent)

def replace_image(home,name,post,event=lambda *a:None,expected=None,retained=None,receipt=None,owned_identity=None,root=ROOT):
    """Guarded atomic transition with a proven kernel receipt, not image ownership."""
    p=safe_path(home/name);mkdirs(p.parent)
    if expected is None:expected=capture(home,name)
    before_identity=file_identity(p)
    if owned_identity is not None and before_identity!=owned_identity:raise PolicyError('concurrent_change')
    retained=retained or home/root/'retained'/uuid.uuid4().hex
    slot=retained/uuid.uuid4().hex;mkdirs(slot)
    exclusive_file(slot/'metadata.json',encode({'schema':1,'target':name,'expected':expected,'intended':post,
                                               'pre_identity':before_identity}))
    new=slot/'version';displaced=slot/'displaced'
    if post['exists']:
        fd=os.open(new,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(raw(post));f.flush();os.fchmod(f.fileno(),post['mode'])
            event('before_fsync',name);os.fsync(f.fileno())
        sync_dir(slot)
    published_identity=file_identity(new) if post['exists'] else None
    event('before_replace',name)
    if capture(home,name)!=expected or file_identity(p)!=before_identity:raise PolicyError('concurrent_change')
    if receipt is None:receipt={}
    receipt.setdefault('performed',False);receipt.setdefault('transitions',[])
    def transition(kind,src,dst):
        # Called by the innermost native wrapper immediately after kernel rc=0,
        # before caller wrappers, validation, events or fsync can throw.
        if (kind in ('exchange','create') and src==new and dst==p) or (kind=='move' and src==p and dst==displaced):
            receipt['performed']=True
            if len(receipt['transitions'])==0:
                receipt.update(kind=kind,published_identity=published_identity,pre_identity=before_identity,
                               retained_path=str((displaced if kind=='move' else new).relative_to(home)))
            receipt['transitions'].append(kind)
    def observed(path):return capture(home,str(path.relative_to(home)))
    token=_TRANSITION.set(transition)
    try:
        if not post['exists']:
            if not expected['exists']:return
            atomic_move(p,displaced)
            try:matched=observed(displaced)==expected and file_identity(displaced)==before_identity
            except PolicyError:matched=False
            if not matched:
                try:os.link(displaced,p,follow_symlinks=False)
                except OSError:pass
                sync_dir(slot);sync_dir(p.parent)
                raise PolicyError('recovery_required')
        elif expected['exists']:
            atomic_exchange(new,p)
            try:
                matched=(observed(new)==expected and file_identity(new)==before_identity and
                         capture(home,name)==post and file_identity(p)==published_identity)
            except PolicyError:matched=False
            if not matched:
                try:
                    if capture(home,name)==post and file_identity(p)==published_identity:atomic_exchange(new,p)
                except (OSError,PolicyError):pass
                sync_dir(slot);sync_dir(p.parent)
                raise PolicyError('recovery_required')
        else:
            try:atomic_create(new,p)
            except FileExistsError:raise PolicyError('recovery_required')
            if capture(home,name)!=post or file_identity(p)!=published_identity:raise PolicyError('recovery_required')
        # This durable note is supplemental: the in-memory receipt already exists
        # if writing the note or a later fsync/event fails. Startup never replays it.
        exclusive_file(slot/'receipt.json',encode(receipt))
        event('after_replace',name)
        event('before_dir_fsync',name);sync_dir(p.parent);sync_dir(slot)
    finally:_TRANSITION.reset(token)

def apply(p,expected_digest,*,fs_event=lambda *a:None):
    if expected_digest!=p.sha256:raise PolicyError('plan_digest_mismatch')
    fresh=plan(p.operation,p.home,p.bundle_path,p.backup_id,p.flavor)
    if fresh.sha256!=p.sha256:raise PolicyError('stale_plan')
    if not p.changes:return {'changed':False,'backup_id':None,'plan_sha256':p.sha256}
    L=layout(p.flavor)
    root=p.home/L.root;mkdirs(root)
    lock=root/'writer.lock';safe_path(lock)
    try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    except FileExistsError:raise PolicyError('writer_locked')
    ident=uuid.uuid4().hex
    with os.fdopen(fd,'wb') as f:f.write(ident.encode());f.flush();os.fsync(f.fileno())
    sync_dir(root)
    retained=root/'retained'/ident;mkdirs(retained)
    lockimage=capture(p.home,L.root+'/writer.lock')
    journal=root/'transaction.json';anchor=retained/'journal-anchor'
    started=False;phase='prepare';journalimage=None;receipts={}
    def mutate(name,post,expected=None,event=lambda *a:None,receipt=None,owned_identity=None):
        replace_image(p.home,name,post,event,expected=expected,retained=retained,receipt=receipt,owned_identity=owned_identity)
    def gate():
        # No destructive overwrite during recovery. Retained anchor is already
        # fsynced; linking it back can recover a gate even after journal removal.
        if not journal.exists():
            if anchor.exists():
                try:os.link(anchor,journal,follow_symlinks=False)
                except FileExistsError:pass
                sync_dir(root)
            elif journalimage is not None:
                mutate(L.root+'/transaction.json',journalimage,dict(ABSENT))
    def release_lock():
        fs_event('before_lock_cleanup',L.root+'/writer.lock')
        mutate(L.root+'/writer.lock',dict(ABSENT),lockimage)
        fs_event('after_lock_cleanup',L.root+'/writer.lock');sync_dir(root)
    try:
        for name,pre in p.guards.items():
            if capture(p.home,name)!=pre:raise PolicyError('stale_plan')
        b={'schema':1,'id':ident,'home':str(p.home),'operation':p.operation,'changes':p.changes,
           'retained_root':str(retained.relative_to(p.home))}
        bdir=root/'backups'/ident;mkdirs(bdir);data=encode(b)
        mutate(L.root+'/backups/'+ident+'/backup.json',image(data))
        mutate(L.root+'/backups/'+ident+'/sha256',image(digest(data).encode()+b'\n'))
        journalimage=image(encode({'schema':1,'backup_id':ident,'plan_sha256':p.sha256,'changes':p.changes,
                                  'retained_root':str(retained.relative_to(p.home))}))
        started=True
        mutate(L.root+'/transaction.json',journalimage,dict(ABSENT))
        os.link(journal,anchor,follow_symlinks=False);sync_dir(retained)
        phase='mutating'
        for index,c in enumerate(p.changes):
            if capture(p.home,c['path'])!=c['pre']:raise PolicyError('concurrent_change')
            receipts[index]={'performed':False,'transitions':[]}
            mutate(c['path'],c['post'],c['pre'],fs_event,receipt=receipts[index])
        phase='commit'
        fs_event('before_journal_remove',L.root+'/transaction.json')
        mutate(L.root+'/transaction.json',dict(ABSENT),journalimage)
        fs_event('after_journal_remove',L.root+'/transaction.json');sync_dir(root)
        release_lock()
        return {'changed':True,'backup_id':ident,'plan_sha256':p.sha256}
    except Exception as exc:
        conflict=isinstance(exc,PolicyError) and str(exc)=='recovery_required'
        # Commit/cleanup uncertainty always remains gated; never begin a new
        # rollback after the commit's journal was removed without a durable gate.
        if phase=='commit':conflict=True
        if started and phase!='commit':
            try:gate()
            except Exception:conflict=True
            for index in reversed(range(len(p.changes))):
                c=p.changes[index]
                try:
                    now=capture(p.home,c['path']);r=receipts.get(index)
                    if not r or not r['performed']:
                        # An externally produced postimage, including absence,
                        # is never evidence that we performed this operation.
                        if now!=c['pre']:conflict=True
                        continue
                    if r['kind'] in ('exchange','move'):
                        retained_path=p.home/r['retained_path']
                        if (capture(p.home,r['retained_path'])!=c['pre'] or
                            file_identity(retained_path)!=r['pre_identity']):
                            conflict=True;continue
                    identity=file_identity(p.home/c['path'])
                    if now==c['post'] and identity==r['published_identity']:
                        mutate(c['path'],c['pre'],c['post'],owned_identity=r['published_identity'])
                    else:conflict=True
                except Exception:conflict=True
            if not conflict:
                try:
                    if journal.exists():mutate(L.root+'/transaction.json',dict(ABSENT),journalimage)
                    sync_dir(root)
                except Exception:conflict=True
        if conflict:
            try:gate()
            except Exception:pass # Retained fsynced anchor/versions are never deleted.
            raise PolicyError('recovery_required') from exc
        try:release_lock()
        except Exception as cleanup:
            try:gate()
            except Exception:pass
            raise PolicyError('recovery_required') from cleanup
        if isinstance(exc,PolicyError) and str(exc) in ('stale_plan','atomic_mutation_unsupported'):raise
        raise PolicyError('operation_failed') from exc
