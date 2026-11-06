"""Usage measurement: token metadata from Claude/Codex logs plus an outcomes log. Never reads or prints message content."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from .bundle import PolicyError
from .routing import load_config

OUTCOMES=Path('~/.config/ai-agent-policy/usage/outcomes.jsonl')
CLAUDE_DIR=Path('~/.claude/projects'); CODEX_DIR=Path('~/.codex/sessions')
STR=('task_id','host','tool','model','effort','task_type')
INTS=('level','retries','escalations','input_tokens','output_tokens','cache_tokens')
FLOATS=('duration_s','cost_usd')

def _lines(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            yield from f
    except OSError: return

def _files(root, pattern):
    root=Path(root)
    return sorted(p for p in root.rglob(pattern) if p.is_file() and not p.is_symlink()) if root.is_dir() else []

def _int(v): return v if isinstance(v, int) and not isinstance(v, bool) and v>=0 else 0

def _day_ok(ts, since): return not since or (isinstance(ts, str) and ts[:10]>=since)

def collect_claude(root, since=None):
    models, seen, skipped, files={}, set(), 0, 0
    for f in _files(root, '*.jsonl'):
        files+=1
        for line in _lines(f):
            if '"usage"' not in line: continue
            try: d=json.loads(line)
            except ValueError: skipped+=1; continue
            m=d.get('message') if isinstance(d, dict) else None
            u=m.get('usage') if isinstance(m, dict) else None
            model=m.get('model') if isinstance(m, dict) else None
            if d.get('type')!='assistant' or not isinstance(u, dict) or not isinstance(model, str) or model=='<synthetic>': continue
            if not _day_ok(d.get('timestamp'), since): continue
            key=m.get('id') or d.get('requestId')
            if key:
                if key in seen: continue
                seen.add(key)
            r=models.setdefault(model, {'input':0,'output':0,'cache_read':0,'cache_write':0,'messages':0,'_s':set()})
            r['input']+=_int(u.get('input_tokens')); r['output']+=_int(u.get('output_tokens'))
            r['cache_read']+=_int(u.get('cache_read_input_tokens')); r['cache_write']+=_int(u.get('cache_creation_input_tokens'))
            r['messages']+=1; r['_s'].add(d.get('sessionId') or f.stem)
    for r in models.values(): r['sessions']=len(r.pop('_s'))
    return {'models':models,'skipped_lines':skipped,'files':files}

def collect_codex(root, since=None):
    models, skipped, files={}, 0, 0
    for f in _files(root, 'rollout-*.jsonl'):
        files+=1; model=first=None; prev={}; per={}
        for line in _lines(f):
            tc='"turn_context"' in line
            if not (tc or '"token_count"' in line): continue
            try: d=json.loads(line)
            except ValueError: skipped+=1; continue
            if not isinstance(d, dict): continue
            first=first or d.get('timestamp')
            p=d.get('payload')
            if not isinstance(p, dict): continue
            if d.get('type')=='turn_context' and isinstance(p.get('model'), str): model=p['model']
            elif model and p.get('type')=='token_count' and isinstance(p.get('info'), dict) and isinstance(p['info'].get('total_token_usage'), dict):
                # Totals are cumulative per session: attribute each increment to the model active at that point.
                u=p['info']['total_token_usage']; acc=per.setdefault(model, {})
                for k in ('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens'):
                    acc[k]=acc.get(k, 0)+max(_int(u.get(k))-prev.get(k, 0), 0); prev[k]=_int(u.get(k))
        if not per or not _day_ok(first, since): continue
        for m, u in per.items():
            r=models.setdefault(m, {'input':0,'cached_input':0,'output':0,'reasoning_output':0,'sessions':0})
            r['input']+=u['input_tokens']; r['cached_input']+=u['cached_input_tokens']
            r['output']+=u['output_tokens']; r['reasoning_output']+=u['reasoning_output_tokens']; r['sessions']+=1
    return {'models':models,'skipped_lines':skipped,'files':files}

def _private_dirs(path):
    todo=[]
    p=path
    while not p.exists(): todo.append(p); p=p.parent
    for d in reversed(todo): d.mkdir(mode=0o700); os.chmod(d, 0o700)

def record(path=None, **fields):
    for k in ('task_id','model','task_type','success'):
        if fields.get(k) is None: raise PolicyError('outcome_missing_'+k)
    if set(fields)-set(STR)-set(INTS)-set(FLOATS)-{'success','verified','ts'}: raise PolicyError('outcome_unknown_field')
    row={'ts':fields.get('ts') or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    for k in STR:
        v=fields.get(k)
        if v is not None and not (isinstance(v, str) and 0<len(v)<=200): raise PolicyError('outcome_invalid_'+k)
        row[k]=v
    for k in ('success','verified'):
        v=fields.get(k)
        if not (isinstance(v, bool) or (k=='verified' and v is None)): raise PolicyError('outcome_invalid_'+k)
        row[k]=v
    for k in INTS+FLOATS:
        v=fields.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float) if k in FLOATS else int) or v<0): raise PolicyError('outcome_invalid_'+k)
        row[k]=v
    path=Path(path or OUTCOMES).expanduser()
    _private_dirs(path.parent)
    fd=os.open(path, os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600); os.write(fd, (json.dumps(row, sort_keys=True)+'\n').encode())
    finally: os.close(fd)
    return row

def load_outcomes(path=None, since=None):
    rows=[]
    for line in _lines(Path(path or OUTCOMES).expanduser()):
        try: d=json.loads(line)
        except ValueError: continue
        if isinstance(d, dict) and d.get('task_id') and d.get('model') and d.get('task_type') and isinstance(d.get('success'), bool) and _day_ok(d.get('ts'), since): rows.append(d)
    return rows

def _cost(price, r, codex):
    try:
        if codex: return ((r['input']-r['cached_input'])*price['input']+r['cached_input']*price['cache_read']+r['output']*price['output'])/1e6
        return (r['input']*price['input']+r['output']*price['output']+r['cache_read']*price['cache_read']+r['cache_write']*price['cache_write'])/1e6
    except (KeyError, TypeError): return 'not_collected'

def _tokens(o):
    v=[o.get(k) for k in ('input_tokens','output_tokens','cache_tokens')]
    return None if all(x is None for x in v) else sum(x or 0 for x in v)

def report(config, claude=None, codex=None, outcomes=()):
    prices=(config.get('pricing_usd_per_million_tokens') or {}).get('models') or {}
    models, nc, out=({}, [], list(outcomes))
    for src, data in (('claude', claude), ('codex', codex)):
        if data is None: nc.append(src+'_logs'); continue
        for m, r in data['models'].items():
            e=dict(r, source=src)
            e['estimated_cost_usd']=_cost(prices[m], r, src=='codex') if isinstance(prices.get(m), dict) else 'not_collected'
            models[m]=e
    if any(e['estimated_cost_usd']=='not_collected' for e in models.values()): nc.append('pricing')
    groups={}
    for o in out: groups.setdefault(o['task_type'], {}).setdefault(o['model'], []).append(o)
    by_type, stats={}, {}
    for t, ms in groups.items():
        for m, rows in ms.items():
            n=len(rows); ok=sum(r['success'] for r in rows); tk=[_tokens(r) for r in rows]; rt=[r['retries'] for r in rows if r.get('retries') is not None]
            cs=[r.get('cost_usd') for r in rows]
            by_type.setdefault(t, {})[m]={'n':n,'success_rate':round(ok/n, 4),'verified_rate':round(sum(r.get('verified') is True for r in rows)/n, 4),
                'avg_retries':round(sum(rt)/len(rt), 4) if rt else 'not_collected','escalations':sum(r.get('escalations') or 0 for r in rows),
                'avg_tokens':round(sum(x for x in tk if x is not None)/sum(x is not None for x in tk), 2) if any(x is not None for x in tk) else 'not_collected'}
            stats[t, m]=(n, ok, None if None in cs else sum(cs), None if None in tk else sum(tk))
    if any(_tokens(o) is None for o in out): nc.append('outcome_tokens')
    if any(o.get('cost_usd') is None for o in out): nc.append('outcome_cost')
    if not out: nc.append('outcomes')
    minn=(config.get('recommendation') or {}).get('min_samples', 5)
    # Recommendations tune default routes only; escalation/last-resort tiers stay governed by routing rules.
    gated={x for a, m in config['models'].items() if m['tier'] in config['limits'].get('premium_tiers', ()) for x in (a, m['id'])}
    recs={}
    for t, ms in by_type.items():
        cand=[(m, stats[t, m]) for m in sorted(ms) if m not in gated and stats[t, m][0]>=minn and stats[t, m][1]>0]
        recs[t]='insufficient_data'
        for metric, idx in (('cost_per_successful_task', 2), ('tokens_per_successful_task', 3)):
            if cand and all(s[idx] is not None for _, s in cand):
                m, s=min(cand, key=lambda c: c[1][idx]/c[1][1])
                recs[t]={'model':m,'metric':metric,'value':round(s[idx]/s[1], 6),'n':s[0]}; break
    return {'schema':1,'models':models,'outcomes_by_type':by_type,'recommendations':recs,'not_collected':sorted(set(nc)),
            'collected':{'claude':{k: claude[k] for k in ('files','skipped_lines')} if claude else 'not_collected',
                         'codex':{k: codex[k] for k in ('files','skipped_lines')} if codex else 'not_collected','outcomes':len(out)}}

def _bool(s):
    if s not in ('true','false'): raise argparse.ArgumentTypeError('expected true|false')
    return s=='true'

def main(argv=None):
    p=argparse.ArgumentParser(prog='ai_policy.usage'); sub=p.add_subparsers(dest='cmd', required=True)
    r=sub.add_parser('record')
    for k in ('task-id','model','task-type','host','tool','effort'): r.add_argument('--'+k, required=k in ('task-id','model','task-type'))
    r.add_argument('--success', type=_bool, required=True); r.add_argument('--verified', type=_bool)
    for k in ('level','retries','escalations','input-tokens','output-tokens','cache-tokens'): r.add_argument('--'+k, type=int)
    for k in ('duration-s','cost-usd'): r.add_argument('--'+k, type=float)
    r.add_argument('--outcomes')
    q=sub.add_parser('report'); q.add_argument('--since', type=lambda s: re.fullmatch(r'\d{4}-\d{2}-\d{2}', s) and s or p.error('--since must be YYYY-MM-DD'))
    q.add_argument('--claude-dir'); q.add_argument('--codex-dir'); q.add_argument('--outcomes'); q.add_argument('--no-logs', action='store_true'); q.add_argument('--config')
    a=p.parse_args(argv)
    try:
        if a.cmd=='record':
            kw={k: v for k, v in vars(a).items() if k not in ('cmd','outcomes')}
            record(a.outcomes, **kw); res={'schema':1,'recorded':True}
        else:
            claude=codex=None
            if not a.no_logs:
                cd, xd=Path(a.claude_dir or CLAUDE_DIR).expanduser(), Path(a.codex_dir or CODEX_DIR).expanduser()
                claude=collect_claude(cd, a.since) if cd.is_dir() else None
                codex=collect_codex(xd, a.since) if xd.is_dir() else None
            res=report(load_config(a.config), claude, codex, load_outcomes(a.outcomes, a.since))
    except PolicyError as e:
        print(json.dumps({'schema':1,'error':str(e)}, sort_keys=True)); return 30
    print(json.dumps(res, sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
