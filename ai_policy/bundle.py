"""Strict local bundle integrity and conditional adapter rendering."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

class PolicyError(Exception):
    """A stable, sanitized reason, never a response or file-content dump."""

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'))+'\n').encode()

def relative(name):
    p=PurePosixPath(name)
    if not isinstance(name, str) or not name or p.is_absolute() or '..' in p.parts or str(p)!=name:
        raise PolicyError('unsafe_path')
    return name

def safe_path(path, *, private=False):
    """Check every existing ancestor without following symlinks (sticky /tmp allowed)."""
    path=Path(os.path.abspath(path))
    for p in reversed((path, *path.parents)):
        try: s=p.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(s.st_mode): raise PolicyError('symlink')
        if s.st_uid not in (0, os.getuid()): raise PolicyError('foreign_owner')
        sticky=stat.S_ISDIR(s.st_mode) and bool(s.st_mode & stat.S_ISVTX)
        if s.st_mode & 0o022 and not sticky: raise PolicyError('unsafe_mode')
        if p == path and private and (s.st_uid!=os.getuid() or s.st_mode & 0o077):
            raise PolicyError('private_mode')
        if p != path and not stat.S_ISDIR(s.st_mode): raise PolicyError('non_directory')
    return path

def read_regular(path, *, private=False):
    p=safe_path(path, private=private)
    try:
        if not stat.S_ISREG(p.lstat().st_mode): raise PolicyError('non_regular')
        fd=os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as f:
            s=os.fstat(f.fileno())
            if not stat.S_ISREG(s.st_mode): raise PolicyError('non_regular')
            if s.st_size > 8*1024*1024: raise PolicyError('file_too_large')
            return f.read(8*1024*1024+1)
    except OSError as e: raise PolicyError('file_unavailable') from e

@dataclass(frozen=True)
class Bundle:
    manifest: dict
    files: dict
    sha256: str

REQUIRED={'policy/orca-common.md','policy/adapters/codex.md','policy/adapters/claude.md',
          'ai_policy/__init__.py','ai_policy/__main__.py','ai_policy/bundle.py',
          'ai_policy/context.py','ai_policy/install.py'}

def load_bundle(manifest_path):
    p=Path(manifest_path)
    raw=read_regular(p)
    try: m=json.loads(raw)
    except (ValueError, TypeError): raise PolicyError('manifest_invalid')
    if not isinstance(m,dict) or m.get('schema')!=1 or m.get('installer_schema')!=1 or not m.get('version') or not m.get('installer_version'):
        raise PolicyError('manifest_schema')
    if not re.fullmatch('[0-9a-f]{40}',str(m.get('source_commit',''))): raise PolicyError('source_provenance')
    sources=m.get('source_hashes')
    if not isinstance(sources,dict) or len(sources)!=5 or any(not re.fullmatch('[0-9a-f]{64}',str(v)) for v in sources.values()):
        raise PolicyError('source_provenance')
    hashes=m.get('files')
    if not isinstance(hashes,dict) or set(hashes)!=REQUIRED: raise PolicyError('manifest_files')
    files={}
    for name,h in hashes.items():
        relative(name)
        if not re.fullmatch('[0-9a-f]{64}',str(h)): raise PolicyError('manifest_hash')
        data=read_regular(p.parent.parent/name)
        if digest(data)!=h: raise PolicyError('bundle_drift')
        files[name]=data
    return Bundle(m,files,digest(raw))

def adapter(bundle, host, home):
    if host not in ('codex','claude'): raise PolicyError('unsupported_host')
    # JSON quoting makes the displayed path unambiguous; it is guidance, never shell.
    fixed=str(Path(home)/'.config/ai-agent-policy/orca/entrypoint.py')
    return bundle.files['policy/adapters/'+host+'.md'].replace(b'{{ENTRYPOINT}}',json.dumps(fixed,ensure_ascii=False).encode())
