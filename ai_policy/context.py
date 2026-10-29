"""Fail-closed evidence core and bounded, read-only Orca metadata provider.

The installed runtime never uses PATH to locate Orca. This reviewed candidate is
specific to the current Mac layout; another layout is unsupported until reviewed.
No currently supported query attests the calling invocation.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time
from .bundle import PolicyError, safe_path

ALLOWLIST=('ORCA_TERMINAL_HANDLE','ORCA_WORKSPACE_ID','ORCA_WORKTREE_ID',
           'ORCA_RUNTIME_SOURCE_ID','ORCA_RUNTIME_SOURCE_INCARNATION','ORCA_TAB_ID')
SELECTED_ORCA='/Applications/Orca.app/Contents/Resources/bin/orca'

@dataclass(frozen=True)
class Evidence:
    hints_present: bool=False
    registered: bool=False
    runtime_reachable: bool | None=None
    terminal_live: bool | None=None
    workspace_match: bool | None=None
    runtime_match: bool | None=None
    host_match: bool | None=None
    invocation_bound: bool=False
    error: str | None=None

def environment_hints(env):
    return {k:v for k in ALLOWLIST if (v:=env.get(k)) is not None}

def contains(root, cwd):
    try: Path(cwd).resolve().relative_to(Path(root).resolve()); return True
    except (ValueError,OSError): return False

def decide(evidence, bundle_valid, bundle_sha256=None):
    e=evidence
    decision,reason='ambiguous','origin_unverified'
    if e.error: reason=e.error
    elif not e.hints_present and not e.registered: decision,reason='inactive','not_managed'
    elif not bundle_valid: reason='bundle_invalid'
    elif e.runtime_reachable is False: reason='runtime_unavailable'
    elif e.runtime_match is False: reason='runtime_changed'
    elif e.workspace_match is False: reason='workspace_mismatch'
    elif e.host_match is False: reason='host_mismatch'
    elif e.terminal_live is False: reason='terminal_not_live'
    elif all(x is True for x in (e.registered,e.runtime_reachable,e.terminal_live,
              e.workspace_match,e.runtime_match,e.host_match,e.invocation_bound)):
        decision,reason='active','verified'
    return {'schema':1,'decision':decision,'reason':reason,
            'checks':{'runtime_reachable':e.runtime_reachable,'terminal_live':e.terminal_live,
                      'workspace_match':e.workspace_match,'invocation_bound':e.invocation_bound},
            'provenance':{'bundle_sha256':bundle_sha256},'policy_emitted':decision=='active'}

def render_context(decision, verified_policy_bytes):
    return verified_policy_bytes if decision['decision']=='active' else b''

def bounded_query(argv, cwd, timeout):
    """Bound stdout AND stderr in aggregate; kill/reap on overflow or deadline."""
    if not isinstance(argv,list) or not argv or not Path(argv[0]).is_absolute():
        raise PolicyError('executable_unsupported')
    deadline=time.monotonic()+min(timeout,5.0)
    try:
        p=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,shell=False,env=environment_hints(os.environ))
    except OSError as e: raise PolicyError('runtime_unavailable') from e
    count=0; out=bytearray()
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ,True)
            sel.register(p.stderr,selectors.EVENT_READ,False)
            while sel.get_map():
                left=deadline-time.monotonic()
                if left<=0: raise PolicyError('query_timeout')
                for key,_ in sel.select(left):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk: sel.unregister(key.fileobj);continue
                    count+=len(chunk)
                    if count>1024*1024: raise PolicyError('query_overflow')
                    if key.data: out.extend(chunk)
            try: code=p.wait(timeout=max(0.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired: raise PolicyError('query_timeout')
        try: data=json.loads(out)
        except (ValueError,UnicodeError): raise PolicyError('query_invalid_json')
        if not isinstance(data,dict): raise PolicyError('schema_invalid')
        if code and not (data.get('ok') is False and isinstance(data.get('error'),dict) and data['error'].get('code')=='selector_not_found'):
            raise PolicyError('runtime_unavailable')
        return data
    finally:
        if p.poll() is None: p.kill();p.wait()
        p.stdout.close();p.stderr.close()

def collect_runtime(cwd, hints, runner=bounded_query, *, orca=SELECTED_ORCA):
    """Private runner boundary permits host fixtures, never production CLI proof."""
    present=bool(hints)
    # Even absent hints may map a registered folder; no tracking endpoints are used.
    base=dict(hints_present=present)
    if runner is bounded_query:
        try:
            p=safe_path(orca)
            if not p.is_file() or not os.access(p,os.X_OK): raise PolicyError('executable_unsupported')
        except (PolicyError,OSError): return Evidence(**base,error='executable_unsupported')
    deadline=time.monotonic()+15.0
    def query(args):
        left=deadline-time.monotonic()
        if left<=0: raise PolicyError('query_timeout')
        data=runner([str(orca),*args],cwd,min(5.0,left))
        if isinstance(data,dict) and data.get('ok') is False and isinstance(data.get('error'),dict) and data['error'].get('code')=='selector_not_found' and args==['worktree','current','--json']:
            raise PolicyError('workspace_unregistered')
        if not isinstance(data,dict) or data.get('ok') is not True or not isinstance(data.get('result'),dict):
            raise PolicyError('schema_invalid')
        meta=data.get('_meta')
        if not isinstance(meta,dict) or not isinstance(meta.get('runtimeId'),str): raise PolicyError('schema_invalid')
        return data['result'],meta['runtimeId']
    try:
        status,r1=query(['status','--json'])
        current,r2=query(['worktree','current','--json'])
        base.update(runtime_reachable=True,runtime_match=r1==r2)
        if r1!=r2: return Evidence(**base)
        # Supported response may wrap the current worktree. Unknown shapes deny.
        worktree=current.get('worktree',current)
        if not isinstance(worktree,dict): raise PolicyError('schema_invalid')
        path=worktree.get('path'); workspace=worktree.get('workspaceId'); tree=worktree.get('worktreeId',worktree.get('id'))
        if not all(isinstance(x,str) and x for x in (path,tree)): raise PolicyError('schema_invalid')
        base.update(registered=True,workspace_match=contains(path,cwd))
        handle=hints.get('ORCA_TERMINAL_HANDLE')
        if not handle: return Evidence(**base)
        terminal,r3=query(['terminal','show','--terminal',handle,'--json'])
        base['runtime_match']=r1==r3
        terminal=terminal.get('terminal',terminal)
        if not isinstance(terminal,dict): raise PolicyError('schema_invalid')
        connected=terminal.get('connected');orphaned=terminal.get('orphaned')
        if type(connected) is not bool or type(orphaned) is not bool: raise PolicyError('schema_invalid')
        base['terminal_live']=connected and not orphaned
        tw=terminal.get('workspaceId');tt=terminal.get('worktreeId')
        if not isinstance(tt,str) or not tt: raise PolicyError('schema_invalid')
        comparisons=[base['workspace_match'],tt==tree]
        if workspace is not None and tw is not None: comparisons.append(tw==workspace)
        if terminal.get('worktreePath') is not None: comparisons.append(Path(terminal['worktreePath']).resolve()==Path(path).resolve())
        host=worktree.get('hostId'); thost=terminal.get('executionHostId')
        if isinstance(host,str) and isinstance(thost,str): base['host_match']=host==thost
        for key,actual in [('ORCA_WORKSPACE_ID',workspace),('ORCA_WORKTREE_ID',tree),
                           ('ORCA_TERMINAL_HANDLE',terminal.get('handle')),('ORCA_TAB_ID',terminal.get('tabId'))]:
            if key in hints and actual is not None: comparisons.append(hints[key]==actual)
        base['workspace_match']=all(comparisons)
        # Host/incarnation binding has no validated contract. Never infer it from
        # candidate IDs, caller, title, agent identity, or generic runtime metadata.
        return Evidence(**base)
    except PolicyError as e:
        if str(e)=='workspace_unregistered' and not present:
            return Evidence(runtime_reachable=True)
        return Evidence(**base,error=str(e))
    except (OSError,ValueError,TypeError,KeyError):
        return Evidence(**base,error='runtime_unavailable')
