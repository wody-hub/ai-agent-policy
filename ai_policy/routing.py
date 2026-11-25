"""Config-driven model routing: pick model/effort by task level, failures and availability."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from .bundle import PolicyError

DEFAULT_CONFIG=Path(__file__).resolve().parent.parent/'policy'/'model-routing.json'
REQUIRED=('models','codex_model_families','hosts','roles','levels','task_types','escalation','fallbacks','limits')
PRESERVE={'retry','escalate','handoff_to_lead','blocked_no_available_model','blocked_no_independent_reviewer','retry_same_model_preserve_state'}

def _bad():
    raise PolicyError('routing_config_invalid')

def _pick(config, entry):
    try: alias, effort=entry
    except (TypeError, ValueError): _bad()
    m=config['models'].get(alias) if isinstance(alias, str) else None
    if m is None or not (effort is None or effort in m.get('efforts', ())): _bad()

CODEX_ID=re.compile(r'gpt-\d+(?:\.\d+)*-([a-z0-9]+)')
FAMILIES=('claude','codex')

def _unique(pairs):
    keys=[k for k,_ in pairs]
    if len(keys)!=len(set(keys)): raise ValueError('duplicate_key')
    return dict(pairs)

def _check_paseo_roles(c):
    roles=c.get('paseo_roles', {})
    if not isinstance(roles, dict) or (roles and 'paseo' not in c['hosts']): _bad()
    tools=c['hosts'].get('paseo', {}).get('tools', ())
    for pid, e in roles.items():
        if not isinstance(pid, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', pid) or not isinstance(e, dict): _bad()
        if not all(k in e for k in ('model','effort','mode_id','provider','pinned_id','description')) or not isinstance(e.get('provisional', False), bool): _bad()
        if not all(isinstance(e[k], str) and e[k] for k in ('mode_id','pinned_id','description')) or not re.fullmatch(r'[a-z0-9-]+', e['mode_id']): _bad()
        _pick(c, (e['model'], e['effort']))
        m=c['models'][e['model']]
        if e['provider']!=m['tool'] or e['provider'] not in tools: _bad()
        if m['tool']=='codex':
            # A bare family name ("luna") is not an exact model id; the id must carry its generation and its own family.
            g=CODEX_ID.fullmatch(e['pinned_id'])
            if not g or g.group(1)!=m.get('codex_family'): _bad()
        elif e['pinned_id']!=m['id']: _bad()

def load_config(path=None):
    try:
        c=json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding='utf-8'), object_pairs_hook=_unique)
    except (OSError, ValueError): _bad()
    if not isinstance(c, dict) or c.get('schema')!=1 or any(not isinstance(c.get(k), dict) for k in REQUIRED): _bad()
    for m in c['models'].values():
        if not isinstance(m, dict) or not all(k in m for k in ('tool','id','tier','efforts','enabled')): _bad()
        family=m.get('codex_family')
        if family is not None and (m['tool']!='codex' or not isinstance(family, str) or not re.fullmatch(r'[a-z0-9]+', family) or c['codex_model_families'].get(family)!=m['id']): _bad()
    if any(not isinstance(k, str) or not re.fullmatch(r'[a-z0-9]+', k) or not isinstance(v, str) or not v for k,v in c['codex_model_families'].items()): _bad()
    hosts=c['hosts']
    for group in ('levels','roles'):
        for entry in c[group].values():
            if not isinstance(entry, dict): _bad()
            if group=='roles' and entry.get('level') not in (1,2,3,4): _bad()
            for h in hosts:
                if h not in entry: _bad()
                _pick(c, entry[h])
    for group in ('levels','roles'):
        for e in c[group].values():
            for k in ('orca_alternatives','paseo_alternatives'):
                for e2 in e.get(k, ()): _pick(c, e2)
    for e in c['levels'].values():
        lateral=e.get('lateral', {})
        if not isinstance(lateral, dict): _bad()
        for h, e2 in lateral.items():
            if h not in hosts: _bad()
            _pick(c, e2)
            if c['models'][e2[0]]['tier'] in c['limits'].get('premium_tiers', ()): _bad()
    _check_paseo_roles(c)
    review=c.get('cross_family_review', {})
    if not isinstance(review, dict) or not set(review.get('blocking_types', ()))<=set(review.get('task_types', ()))<=set(c['task_types']): _bad()
    task_routes = c.get('orca_task_routes', {})
    if not isinstance(task_routes, dict): _bad()
    for key, entries in task_routes.items():
        if key not in c['task_types'] or not isinstance(entries, list) or not entries: _bad()
        for entry in entries:
            _pick(c, entry)
            if c['models'][entry[0]]['tier'] in c['limits'].get('premium_tiers', ()): _bad()
    if not set(c['levels'])<={'1','2','3','4','5'} or '4' not in c['levels']: _bad()
    if any(t not in (1,2,3,4) for t in c['task_types'].values()): _bad()
    for a, fb in c['fallbacks'].items():
        if a not in c['models'] or any(x not in c['models'] for x in fb): _bad()
    if any(k not in c['escalation'] for k in ('reasoning_failures_before_escalation','counted_failure_kinds','immediate_failure_kinds','non_model_failure_kinds','handoff_fields')): _bad()
    return c

def _catalog_id(model, catalog):
    family=model.get('codex_family')
    if not family: return None
    if isinstance(catalog, dict):
        try:
            fetched=datetime.fromisoformat(catalog['fetched_at'].replace('Z','+00:00'))
            if fetched.tzinfo is None: fetched=fetched.replace(tzinfo=timezone.utc)
            age=datetime.now(timezone.utc)-fetched.astimezone(timezone.utc)
            if age>timedelta(days=30) or age<timedelta(minutes=-5): return None
        except (KeyError, TypeError, ValueError): return None
        catalog=catalog.get('models')
    if not isinstance(catalog, list): return None
    pattern=re.compile(r'^gpt-(\d+(?:\.\d+)*?)-'+re.escape(family)+r'$')
    candidates=[]
    for item in catalog:
        if not isinstance(item, dict) or item.get('visibility')!='list' or item.get('supported_in_api') is not True: continue
        slug=item.get('slug')
        match=pattern.fullmatch(slug) if isinstance(slug, str) else None
        if match:
            candidates.append((tuple(int(part) for part in match.group(1).split('.')), slug))
    return max(candidates)[1] if candidates else None

def load_codex_model_catalog(path=None):
    """Read Codex's installed model cache without fetching or updating it."""
    root=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
    p=Path(path) if path else root/'models_cache.json'
    try:
        if p.stat().st_size > 8*1024*1024: return None
        data=json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError): return None
    models=data.get('models') if isinstance(data, dict) else None
    return {'fetched_at':data.get('fetched_at'),'models':models} if isinstance(models, list) else None

def _resolved_model(model, catalog):
    selected=_catalog_id(model, catalog)
    if selected: return selected, 'codex_catalog'
    return model['id'], 'pinned_fallback' if model.get('codex_family') else 'pinned'

def resolve_codex_family(config, family, *, model_catalog=None, effort=None):
    """Resolve a project-selected Codex family to its current exact model id."""
    pinned=config['codex_model_families'].get(family)
    if pinned is None: raise PolicyError('unknown_model_family')
    if effort is not None and effort not in ('low','medium','high','xhigh','max','ultra'): raise PolicyError('unknown_effort')
    model_id, resolution=_resolved_model({'id':pinned,'codex_family':family}, model_catalog)
    return {'schema':1,'action':'run','alias':family,'tool':'codex','agent':'codex','model':model_id,'model_resolution':resolution,'effort':effort,
            'reasons':['model_resolution:'+resolution],
            'orca_worker_args':['--agent','codex','--model',model_id]+(['--effort',effort] if effort else [])}

def _usable(config, host, alias, available, model_id):
    m=config['models'][alias]
    return bool(m['enabled']) and m['tool'] in config['hosts'][host]['tools'] and (available is None or alias in available or model_id in available)

def _effort(m, want):
    ef=m['efforts']
    if not ef: return None
    if want in ef: return want
    return 'medium' if 'medium' in ef else ef[len(ef)//2]

def _families(value, error):
    if value is None: return set()
    items=[value] if isinstance(value, str) else value
    try: items=list(items)
    except TypeError: raise PolicyError(error)
    if any(x not in FAMILIES+('both',) for x in items): raise PolicyError(error)
    return set(FAMILIES) if 'both' in items else set(items)

def route(config, *, host, level=None, task_type=None, role=None, failures=0, failure_kind=None, available=None, resolved=False, model_catalog=None,
          failed_family=None, failed_models=(), implementer_family=None):
    """LEVEL 5 (exceptional tier) is reachable only by escalation from LEVEL 4, never as a starting level."""
    if host not in config['hosts']: raise PolicyError('unknown_host')
    if (role is not None)==(task_type is not None or level is not None): raise PolicyError('invalid_selector')
    esc, high_risk, reasons=config['escalation'], False, []
    if available is not None: available=set(available)
    failed_families=_families(failed_family, 'unknown_failed_family')
    if implementer_family is not None and implementer_family not in FAMILIES: raise PolicyError('unknown_implementer_family')
    failed_models=set([failed_models] if isinstance(failed_models, str) else failed_models or ())
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
    cur, action, escalated, lateral=base, 'run', False, None
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
        else:
            action='retry'; reasons.append('below_failure_threshold')
            # The last allowed attempt at a level with a lateral model goes to that standard-tier model; it has no fallbacks.
            entry_lateral=config['levels'].get(str(cur), {}).get('lateral', {}).get(host) if role is None and cur and failures==esc['reasoning_failures_before_escalation']-1 else None
            if entry_lateral and failure_kind in (None, *esc['counted_failure_kinds']) and entry_lateral[0]!=config['levels'][str(cur)][host][0]:
                model_id, _=_resolved_model(config['models'][entry_lateral[0]], model_catalog)
                if _usable(config, host, entry_lateral[0], available, model_id): lateral=tuple(entry_lateral); reasons.append('lateral_step')
                else: reasons.append('lateral_unavailable:'+entry_lateral[0]); up(cur+1)
    lv=config['levels'][str(cur)] if cur else None
    task_choices = ()
    if host == 'orca' and cur is not None and cur == base and not high_risk and cur < 4 and lateral is None and (level is None or level == config['task_types'].get(task_type)):
        task_choices = config.get('orca_task_routes', {}).get(task_type, ())
    selected = lv if lv else config['roles'][role]
    entry = task_choices[0] if task_choices else selected[host]
    alternatives = task_choices[1:] if task_choices else selected.get(host+'_alternatives') if host in ('orca', 'paseo') else None
    if lateral is not None: entry, alternatives=lateral, ()
    palias, peffort=entry
    cands, chosen, fallback_used, degraded=[], None, False, False
    if cur==top and top>4: reasons.append('last_resort')
    cands=[(palias, peffort)]
    if alternatives is not None:
        cands.extend(tuple(x) for x in alternatives)
    else:
        cands.extend((a, peffort) for a in config['fallbacks'].get(palias, ()))
    if cur==top and top>4 and len(failed_families)==1:
        # LEVEL 5 prefers the family that did not fail last at LEVEL 4 (soft preference; both/unknown keeps the host default).
        cands.sort(key=lambda c: config['models'][c[0]]['tool'] in failed_families)
        if cands[0][0]!=palias: reasons.append('l5_opposite_family:'+cands[0][0])
        palias, peffort=cands[0]
        if not any(config['models'][a]['tool'] not in failed_families and _usable(config, host, a, available, _resolved_model(config['models'][a], model_catalog)[0]) for a, _ in cands):
            reasons.append('l5_opposite_family_unavailable')
    def select(cs):
        seen=set()
        for a, e in cs:
            if a in seen or (config['models'][a]['tier']=='exceptional' and cur!=top): continue
            seen.add(a)
            if cur==4 and a=='sol' and ('sol' in failed_models or config['models']['sol']['id'] in failed_models):
                reasons.append('excluded_failed_model:sol'); continue
            model_id, model_resolution=_resolved_model(config['models'][a], model_catalog)
            if _usable(config, host, a, available, model_id):
                if a==palias or alternatives is not None:
                    return (a, e, model_id, model_resolution)
                # A fallback takes the effort that model is assigned at this level on another host, if any.
                same=[x[1] for x in (lv or {}).values() if isinstance(x, list) and x and x[0]==a]
                return (a, same[0] if same and (same[0] is None or same[0] in config['models'][a]['efforts']) else _effort(config['models'][a], e), model_id, model_resolution)
            if a==palias: reasons.append('model_unavailable:'+a)
    cfr=config.get('cross_family_review', {})
    if implementer_family is not None and role is None and task_type in cfr.get('task_types', ()):
        # Independent review: the reviewer family must differ from the implementer's; the fallback is flagged, or blocked for security/high-risk reviews.
        chosen=select([c for c in cands if config['models'][c[0]]['tool']!=implementer_family])
        if chosen is None and (high_risk or task_type in cfr.get('blocking_types', ())):
            action='blocked_no_independent_reviewer'; reasons.append('independent_reviewer_required')
        elif chosen is None:
            chosen=select([c for c in cands if config['models'][c[0]]['tool']==implementer_family])
            if chosen: degraded=True; reasons.append('degraded_independence')
    else: chosen=select(cands)
    if chosen and chosen[0]!=palias: fallback_used=True
    out={'schema':1,'host':host,'level':cur,'level_name':lv['name'] if lv else None,'task_type':task_type,'role':role,
         'alias':None,'tool':None,'agent':None,'model':None,'model_resolution':None,'effort':None,'tier':None,'action':action,'escalated':escalated,
         'fallback_used':fallback_used,'high_risk':high_risk,'human_gate':high_risk,'premium':False,'premium_requires_reason':False,'lateral':lateral is not None,'degraded_independence':degraded,'preserve_state':False,
         'attempts_reset':bool(esc.get('attempt_count_resets_on_model_change', False)),'reasons':reasons,'handoff_fields':[],'orca_worker_args':[]}
    if chosen is None:
        if action!='blocked_no_independent_reviewer': action='blocked_no_available_model'; reasons.append('no_available_model')
        out['action']=action
    else:
        a, e, model_id, model_resolution=chosen; m=config['models'][a]
        out.update(alias=a, tool=m['tool'], agent=m['agent'], model=model_id, model_resolution=model_resolution, effort=e, tier=m['tier'],
                   premium=m['tier'] in config['limits'].get('premium_tiers', ()),
                   orca_worker_args=[] if host=='paseo' else ['--agent', m['agent'], '--model', model_id]+(['--effort', e] if e else []))
        out['premium_requires_reason']=out['premium'] and bool(config['limits'].get('premium_requires_reason', True))
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
    p.add_argument('--failed-family', help='Comma-separated families (claude, codex, both) that failed at LEVEL 4, most recent last')
    p.add_argument('--failed-model', help='Comma-separated aliases or ids that already failed on this root problem')
    p.add_argument('--implementer-family', help='claude or codex: reviewer must be the other family')
    p.add_argument('--model-catalog', help='Codex model cache JSON; defaults to CODEX_HOME/models_cache.json')
    p.add_argument('--resolve-family', help='Resolve a project-selected Codex family without changing its tier or effort')
    p.add_argument('--effort', choices=('low','medium','high','xhigh','max','ultra'))
    p.add_argument('--config')
    a=p.parse_args(argv)
    try:
        config=load_config(a.config)
        model_catalog=load_codex_model_catalog(a.model_catalog)
        if a.resolve_family:
            if any((a.task_type,a.level,a.role,a.failures,a.failure_kind,a.resolved,a.available)):
                raise PolicyError('invalid_selector')
            if a.host not in config['hosts']: raise PolicyError('unknown_host')
            if 'codex' not in config['hosts'][a.host]['tools']: raise PolicyError('unsupported_host')
            result=resolve_codex_family(config,a.resolve_family,model_catalog=model_catalog,effort=a.effort)
            print(json.dumps(result, sort_keys=True)); return 0
        if a.effort is not None: raise PolicyError('invalid_selector')
        r=route(config, host=a.host, level=a.level, task_type=a.task_type, role=a.role, failures=a.failures,
                failure_kind=a.failure_kind, available=[x for x in a.available.split(',') if x] if a.available is not None else None,
                resolved=a.resolved, model_catalog=model_catalog,
                failed_family=[x for x in a.failed_family.split(',') if x] if a.failed_family is not None else None,
                failed_models=[x for x in a.failed_model.split(',') if x] if a.failed_model is not None else (),
                implementer_family=a.implementer_family)
    except PolicyError as e:
        print(json.dumps({'schema':1,'error':str(e)}, sort_keys=True)); return 30
    print(json.dumps(r, sort_keys=True))
    return {'blocked_no_available_model':40,'blocked_no_independent_reviewer':40,'handoff_to_lead':41}.get(r['action'], 0)

if __name__=='__main__': raise SystemExit(main())
