"""Config-driven model routing: pick model/effort by task level, failures and availability."""
import argparse
import json
from pathlib import Path

from .bundle import PolicyError

DEFAULT_CONFIG=Path(__file__).resolve().parent.parent/'policy'/'model-routing.json'
REQUIRED=('models','hosts','roles','levels','task_types','escalation','fallbacks','limits')
PRESERVE={'retry','escalate','handoff_to_lead','blocked_no_available_model','retry_same_model_preserve_state'}

def _bad():
    raise PolicyError('routing_config_invalid')

def _pick(config, entry):
    try: alias, effort=entry
    except (TypeError, ValueError): _bad()
    m=config['models'].get(alias) if isinstance(alias, str) else None
    if m is None or not (effort is None or effort in m.get('efforts', ())): _bad()

def load_config(path=None):
    try:
        c=json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding='utf-8'))
    except (OSError, ValueError): _bad()
    if not isinstance(c, dict) or c.get('schema')!=1 or any(not isinstance(c.get(k), dict) for k in REQUIRED): _bad()
    for m in c['models'].values():
        if not isinstance(m, dict) or not all(k in m for k in ('tool','id','tier','efforts','enabled')): _bad()
    hosts=c['hosts']
    for group in ('levels','roles'):
        for entry in c[group].values():
            if not isinstance(entry, dict): _bad()
            if group=='roles' and entry.get('level') not in (1,2,3,4): _bad()
            for h in hosts:
                if h not in entry: _bad()
                _pick(c, entry[h])
    for e in c['levels'].values():
        for e2 in e.get('orca_alternatives', ()): _pick(c, e2)
    if not set(c['levels'])<={'1','2','3','4','5'} or '4' not in c['levels']: _bad()
    if any(t not in (1,2,3,4) for t in c['task_types'].values()): _bad()
    for a, fb in c['fallbacks'].items():
        if a not in c['models'] or any(x not in c['models'] for x in fb): _bad()
    if any(k not in c['escalation'] for k in ('reasoning_failures_before_escalation','counted_failure_kinds','immediate_failure_kinds','non_model_failure_kinds','handoff_fields')): _bad()
    return c

def _usable(config, host, alias, available):
    m=config['models'][alias]
    return bool(m['enabled']) and m['tool'] in config['hosts'][host]['tools'] and (available is None or alias in available or m['id'] in available)

def _effort(m, want):
    ef=m['efforts']
    if not ef: return None
    if want in ef: return want
    return 'medium' if 'medium' in ef else ef[len(ef)//2]

def route(config, *, host, level=None, task_type=None, role=None, failures=0, failure_kind=None, available=None, resolved=False):
    """LEVEL 5 (exceptional tier) is reachable only by escalation from LEVEL 4, never as a starting level."""
    if host not in config['hosts']: raise PolicyError('unknown_host')
    if (role is not None)==(task_type is not None or level is not None): raise PolicyError('invalid_selector')
    esc, high_risk, reasons=config['escalation'], False, []
    if available is not None: available=set(available)
    kinds=set(esc['counted_failure_kinds'])|set(esc['immediate_failure_kinds'])|set(esc['non_model_failure_kinds'])
    if failure_kind is not None and failure_kind not in kinds: raise PolicyError('unknown_failure_kind')
    base=None
    if role is not None:
        if role not in config['roles']: raise PolicyError('unknown_role')
        reasons.append('role:'+role)
    else:
        risky=config.get('high_risk_types', [])
        if task_type is not None and task_type not in config['task_types'] and task_type not in risky: raise PolicyError('unknown_task_type')
        top=max(int(k) for k in config['levels'])
        if level is not None and not 1<=level<=top: raise PolicyError('invalid_level')
        # The last-resort level is only reachable by escalation; it may be passed back to report its own failures.
        if level is not None and level>4 and (resolved or (failures==0 and failure_kind is None)): raise PolicyError('last_resort_requires_escalation')
        if task_type is not None: reasons.append('task_type:'+task_type)
        if level is not None:
            base=level
            reasons.append('explicit_level_overrides_task_type' if task_type is not None else 'explicit_level')
        else: base=config['task_types'].get(task_type, 4)
        if task_type in risky:
            base, high_risk=4, True
            reasons.append('high_risk_type')
    cur, action, escalated=base, 'run', False
    top=max(int(k) for k in config['levels'])
    def up(target):
        nonlocal cur, action, escalated
        if cur and (cur>=target or cur==top): action='handoff_to_lead'; reasons.append('already_max_level')
        else: cur, action, escalated=target, 'escalate', True
    if resolved:
        action=('return_to_default'); reasons.append('resolved')
    elif failure_kind in esc['non_model_failure_kinds']:
        # Execution failures (tool/environment/worker) never escalate the model; after the run-attempt cap a person decides.
        if failures>=config['limits'].get('max_run_attempts_non_model', 3):
            action='handoff_to_lead'; reasons.append('run_attempts_exhausted')
        else: action='retry_same_model_preserve_state'; reasons.append('non_model_failure')
    elif failure_kind in esc['immediate_failure_kinds']:
        reasons.append('immediate_failure:'+failure_kind); up(4)
    elif failure_kind is not None or failures>0:
        if failures>=esc['reasoning_failures_before_escalation']:
            reasons.append('failure_threshold_reached'); up(min((cur or config['roles'][role]['level'])+1, top))
        else: action='retry'; reasons.append('below_failure_threshold')
    lv=config['levels'][str(cur)] if cur else None
    entry=lv[host] if lv else config['roles'][role][host]
    palias, peffort=entry
    cands, chosen, fallback_used=[], None, False
    if cur==top and top>4: reasons.append('last_resort')
    if chosen is None:
        cands=[(palias, peffort)]
        if cur and cur>=4 and host=='orca': cands+=[tuple(x) for x in lv.get('orca_alternatives', ())]
        cands+=[(a, peffort) for a in config['fallbacks'].get(palias, ())]
        seen=set()
        for a, e in cands:
            if a in seen or (config['models'][a]['tier']=='exceptional' and cur!=top): continue
            seen.add(a)
            if _usable(config, host, a, available):
                if a==palias: chosen=(a, e)
                else:
                    # A fallback takes the effort that model is assigned at this level on another host, if any.
                    same=[x[1] for x in (lv or {}).values() if isinstance(x, list) and x and x[0]==a]
                    chosen=(a, same[0] if same and (same[0] is None or same[0] in config['models'][a]['efforts']) else _effort(config['models'][a], e))
                break
            if a==palias: reasons.append('model_unavailable:'+a)
        if chosen and chosen[0]!=palias: fallback_used=True
    out={'schema':1,'host':host,'level':cur,'level_name':lv['name'] if lv else None,'task_type':task_type,'role':role,
         'alias':None,'tool':None,'agent':None,'model':None,'effort':None,'tier':None,'action':action,'escalated':escalated,
         'fallback_used':fallback_used,'high_risk':high_risk,'human_gate':high_risk,'premium':False,'preserve_state':False,
         'attempts_reset':bool(esc.get('attempt_count_resets_on_model_change', False)),'reasons':reasons,'handoff_fields':[],'orca_worker_args':[]}
    if chosen is None:
        out['action']=action='blocked_no_available_model'; reasons.append('no_available_model')
    else:
        a, e=chosen; m=config['models'][a]
        out.update(alias=a, tool=m['tool'], agent=m['agent'], model=m['id'], effort=e, tier=m['tier'],
                   premium=m['tier'] in config['limits'].get('premium_tiers', ()),
                   orca_worker_args=['--agent', m['agent'], '--model', m['id']]+(['--effort', e] if e else []))
    if action=='handoff_to_lead': out['orca_worker_args']=[]  # stop: nothing further to launch automatically
    out['preserve_state']=action in PRESERVE
    if action in ('escalate','handoff_to_lead'): out['handoff_fields']=list(esc['handoff_fields'])
    return out

def main(argv=None):
    p=argparse.ArgumentParser(prog='ai_policy.routing')
    p.add_argument('--host', required=True)
    p.add_argument('--task-type'); p.add_argument('--level', type=int); p.add_argument('--role')
    p.add_argument('--failures', type=int, default=0); p.add_argument('--failure-kind')
    p.add_argument('--available'); p.add_argument('--resolved', action='store_true')
    p.add_argument('--config')
    a=p.parse_args(argv)
    try:
        r=route(load_config(a.config), host=a.host, level=a.level, task_type=a.task_type, role=a.role, failures=a.failures,
                failure_kind=a.failure_kind, available=[x for x in a.available.split(',') if x] if a.available is not None else None,
                resolved=a.resolved)
    except PolicyError as e:
        print(json.dumps({'schema':1,'error':str(e)}, sort_keys=True)); return 30
    print(json.dumps(r, sort_keys=True))
    return {'blocked_no_available_model':40,'handoff_to_lead':41}.get(r['action'], 0)

if __name__=='__main__': raise SystemExit(main())
