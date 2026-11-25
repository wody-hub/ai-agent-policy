import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

from ai_policy import paseo, routing
from ai_policy.bundle import PolicyError

BASE=json.loads(routing.DEFAULT_CONFIG.read_text())
# Independent literal copy of the live profile values (id, provider, model, modeId, thinkingOptionId).
LIVE=[('root-orchestrator','claude','claude-sonnet-5-5','auto','high'),('project-coordinator','claude','claude-sonnet-5-5','auto','high'),
      ('dev-l1-simple','codex','gpt-6-luna','auto','medium'),('dev-l2-general','codex','gpt-6-luna','auto','high'),
      ('dev-l3-complex','claude','claude-sonnet-5-5','auto','high'),('l4-critical','claude','claude-opus-5-5','auto','high'),
      ('l5-last-resort','claude','claude-fable-5-1','auto','high'),('review-codex-work','claude','claude-sonnet-5-5','plan','medium'),
      ('review-claude-work','codex','gpt-6.1-terra','auto','high'),('lookup','codex','gpt-6-luna','auto','medium')]

def fixture(mutate=None):
    profiles=[{'id':i,'name':i,'provider':p,'model':m,'modeId':mode,'thinkingOptionId':t,'notes':BASE['paseo_roles'][i]['description']} for i,p,m,mode,t in LIVE]
    if mutate: mutate(profiles)
    return {'version':1,'daemon':{'agentProfiles':profiles}}

def fresh(models): return {'fetched_at':datetime.now(timezone.utc).isoformat(),'models':models}

def run(cfg, catalog=None, models=None, raw_models=None):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'config.json'; p.write_text(json.dumps(cfg)); args=['check','--config',str(p),'--model-catalog',str(Path(d)/'none.json')]
        if models is not None or raw_models is not None:
            m=Path(d)/'models.json'; m.write_text(raw_models if raw_models is not None else json.dumps(models)); args+=['--paseo-models',str(m)]
        if catalog is not None:
            (Path(d)/'cat.json').write_text(json.dumps(catalog)); args[-1]=str(Path(d)/'cat.json')
        b=io.StringIO()
        with contextlib.redirect_stdout(b): code=paseo.main(args)
        return code, json.loads(b.getvalue())

class PaseoRoleConfigTests(unittest.TestCase):
    def bad(self, mut, raw=None):
        c=json.loads(json.dumps(BASE)); mut(c)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.json'; p.write_text(raw(json.dumps(c)) if raw else json.dumps(c))
            with self.assertRaises(PolicyError) as cm: routing.load_config(p)
            self.assertEqual(str(cm.exception), 'routing_config_invalid')

    def test_default_config_loads_with_paseo_host(self):
        c=routing.load_config()
        self.assertEqual(c['hosts']['paseo']['tools'], ['claude','codex'])
        for entry in list(c['levels'].values())+list(c['roles'].values()): self.assertIn('paseo', entry)
        for pid in ('root-orchestrator','project-coordinator'):
            self.assertEqual((c['paseo_roles'][pid]['model'], c['paseo_roles'][pid]['effort']), ('sonnet','high'))
            self.assertNotIn('provisional', c['paseo_roles'][pid])
        for pid in ('scout','ui-verify','l5-alt-astra'): self.assertTrue(c['paseo_roles'][pid]['provisional'])
        self.assertFalse(any(e['model']=='sol' for e in c['paseo_roles'].values()))
        self.assertEqual(c['paseo_roles']['l5-last-resort']['pinned_id'], 'claude-fable-5-1')

    def test_rejects_bad_paseo_roles(self):
        r='paseo_roles'
        self.bad(lambda c: c[r]['lookup'].update(model='ghost'))
        self.bad(lambda c: c[r]['lookup'].update(effort='ultra'))
        self.bad(lambda c: c[r]['scout'].update(effort='ultra'))
        self.bad(lambda c: c[r]['lookup'].update(pinned_id='luna'))              # bare Codex name
        self.bad(lambda c: c[r]['lookup'].update(pinned_id='gpt-6.1-terra'))      # id of another family
        self.bad(lambda c: c[r]['lookup'].update(provider='claude'))              # provider/tool mismatch
        self.bad(lambda c: c[r]['l4-critical'].update(provider='codex'))
        self.bad(lambda c: c[r]['l4-critical'].update(pinned_id='opus'))          # bare Claude alias, not the pinned id
        self.bad(lambda c: c[r]['lookup'].update(provisional='yes'))
        self.bad(lambda c: c[r].update({'Bad_Id':dict(c[r]['lookup'])}))
        self.bad(lambda c: c['hosts'].pop('paseo'))
        self.bad(lambda c: c['levels']['2']['lateral'].update(orca=['sol','high']))   # lateral must not be premium
        self.bad(lambda c: c['levels']['2']['lateral'].update(nope=['terra','high']))
        # duplicate profile ids are rejected at the JSON level (a dict silently keeps the last one)
        self.bad(lambda c: None, raw=lambda t: t.replace('"lookup": {', '"dev-l1-simple": {"model": "luna"}, "lookup": {', 1))

class PaseoCheckTests(unittest.TestCase):
    def test_live_values_have_no_drift_and_orchestrators_are_not_flagged(self):
        code, x=run(fixture())
        self.assertEqual((code, x['drift']), (0, False))
        for pid in ('root-orchestrator','project-coordinator'): self.assertEqual((x['profiles'][pid]['status'], x['profiles'][pid]['differences']), ('ok', []))
        self.assertEqual(x['profiles']['scout']['status'], 'missing_provisional')
        self.assertTrue(any('newer_alias_observed:claude-fable-5-2' in i for i in x['profiles']['l5-last-resort']['info']))
        self.assertTrue(any('pinned:claude-fable-5-1' in i for i in x['profiles']['l5-last-resort']['info']))

    def test_modified_field_is_flagged(self):
        def mut(ps): next(p for p in ps if p['id']=='root-orchestrator')['thinkingOptionId']='medium'
        code, x=run(fixture(mut))
        self.assertEqual((code, x['drift']), (1, True))
        self.assertEqual(x['profiles']['root-orchestrator']['differences'], [{'field':'thinkingOptionId','expected':'high','actual':'medium'}])
        self.assertEqual(x['profiles']['project-coordinator']['status'], 'ok')
        def mut2(ps): next(p for p in ps if p['id']=='l5-last-resort')['model']='claude-fable-5-2'
        self.assertEqual(run(fixture(mut2))[1]['profiles']['l5-last-resort']['differences'][0]['field'], 'model')

    def test_missing_extra_notes_and_duplicates(self):
        code, x=run(fixture(lambda ps: ps.pop(0)))
        self.assertEqual((code, x['profiles']['root-orchestrator']['status']), (1, 'missing'))
        code, x=run(fixture(lambda ps: ps.append({'id':'custom','provider':'claude','model':'m'})))
        self.assertEqual((code, x['unmanaged_profiles']), (0, ['custom']))
        def notes(ps): ps[0]['notes']='edited'
        code, x=run(fixture(notes))
        self.assertEqual((code, x['profiles']['root-orchestrator']['notes_differ'], x['drift']), (0, True, False))
        self.assertEqual(run(fixture(lambda ps: ps.append(dict(ps[0]))))[0], 1)

    def test_stale_or_missing_catalog_never_suggests_lower_generation(self):
        code, x=run(fixture())   # missing catalog file
        row=x['profiles']['dev-l1-simple']
        self.assertEqual(row['codex_resolution']['resolution'], 'pinned_fallback')
        self.assertIn('catalog_stale_or_missing: pinned id kept, no upgrade suggested', row['info'])
        stale={'fetched_at':'2000-01-01T00:00:00Z','models':[{'slug':'gpt-5-luna','visibility':'list','supported_in_api':True}]}
        code, x=run(fixture(), stale)
        self.assertEqual(x['profiles']['dev-l1-simple']['codex_resolution']['resolved'], 'gpt-6-luna')
        older=fresh([{'slug':'gpt-5-luna','visibility':'list','supported_in_api':True}])
        x=run(fixture(), older)[1]['profiles']['dev-l1-simple']
        self.assertEqual(x['codex_resolution']['resolved'], 'gpt-5-luna')
        self.assertEqual(x['info'], ['catalog_not_newer_than_pinned: no change suggested'])
        newer=fresh([{'slug':'gpt-7-luna','visibility':'list','supported_in_api':True}])
        self.assertEqual(run(fixture(), newer)[1]['profiles']['dev-l1-simple']['info'], ['newer_generation_available:gpt-7-luna'])
        self.assertEqual(run(fixture(), newer)[0], 0)   # a newer catalog id is informational, not drift

    def test_check_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text(json.dumps(fixture())); os.utime(p, (1_000_000_000, 1_000_000_000))
            before=(p.read_bytes(), p.stat().st_mtime_ns, sorted(x.name for x in Path(d).iterdir()))
            with contextlib.redirect_stdout(io.StringIO()): paseo.main(['check','--config',str(p),'--model-catalog',str(Path(d)/'none.json')])
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns, sorted(x.name for x in Path(d).iterdir())), before)

    def test_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            for content in (None, '{not json', '[]', '{"daemon":{"agentProfiles":"x"}}'):
                p=Path(d)/'c.json'
                if content is None: p.unlink(missing_ok=True)
                else: p.write_text(content)
                b=io.StringIO()
                with contextlib.redirect_stdout(b): code=paseo.main(['check','--config',str(p)])
                self.assertEqual(code, 2); self.assertIn('error', json.loads(b.getvalue()))

def ids(*xs): return {'models':[{'id':x,'label':x} for x in xs]}

class PaseoModelsTests(unittest.TestCase):
    def test_newer_same_family_id_is_reported_and_is_not_drift(self):
        code, x=run(fixture(), models=ids('claude-fable-5-1','claude-fable-5-2'))
        self.assertEqual((code, x['drift']), (0, False))
        self.assertEqual(x['profiles']['l5-last-resort']['newer_available'], ['claude-fable-5-2'])
        self.assertEqual(x['info'], [])   # the offline-only alias note is dropped when the list is given
        self.assertNotIn('newer_available', run(fixture())[1]['profiles']['l5-last-resort'])
        self.assertEqual(run(fixture())[1]['info'], [paseo.ALIAS_NOTE])

    def test_same_older_and_other_family_not_reported(self):
        code, x=run(fixture(), models=ids('claude-fable-5-1','claude-fable-5','claude-fable-4-9','claude-opus-5-5','claude-sonnet-5-4','claude-haiku-5-5'))
        self.assertEqual(code, 0)
        for pid in ('l5-last-resort','l4-critical','dev-l3-complex','root-orchestrator'): self.assertEqual(x['profiles'][pid]['newer_available'], [])
        self.assertNotIn('newer_available', x['profiles']['dev-l1-simple'])   # codex profiles are not touched

    def test_versions_compare_numerically_and_are_sorted(self):
        x=run(fixture(), models=ids('claude-opus-5-10','claude-opus-5-6','claude-opus-6','claude-opus-5-5'))[1]
        self.assertEqual(x['profiles']['l4-critical']['newer_available'], ['claude-opus-5-6','claude-opus-5-10','claude-opus-6'])

    def test_suffixed_dated_alias_and_unparseable_ids_are_ignored(self):
        junk=['claude-fable-5-2[1m]','claude-fable-5-3-20260101','claude-opus-5-20260101','fable','sonnet','default','claude-fable','claude-fable-x','claude-3-5-sonnet','claude-fable-5-2-preview','']
        x=run(fixture(), models=ids(*junk))[1]
        for pid in ('l5-last-resort','l4-critical','dev-l3-complex'): self.assertEqual(x['profiles'][pid]['newer_available'], [])

    def test_bare_list_shape_is_accepted(self):
        code, x=run(fixture(), models=[{'id':'claude-fable-5-2'},{'id':'claude-haiku-5-5'}])
        self.assertEqual((code, x['profiles']['l5-last-resort']['newer_available']), (0, ['claude-fable-5-2']))

    def test_bad_models_file_exits_2(self):
        for raw in ('{not json','"x"','{"models":"x"}','{"models":[1]}','{"models":[{"name":"a"}]}','{"other":[]}','[{"id":5}]'):
            code, x=run(fixture(), raw_models=raw)
            self.assertEqual((code, x), (2, {'schema':1,'error':'paseo_models_invalid'}), raw)
        self.assertEqual(run(fixture(), raw_models=' '*(1024*1024+1))[1]['error'], 'paseo_models_too_large')
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'c.json'; c.write_text(json.dumps(fixture())); b=io.StringIO()
            with contextlib.redirect_stdout(b): code=paseo.main(['check','--config',str(c),'--paseo-models',str(Path(d)/'missing.json')])
            self.assertEqual((code, json.loads(b.getvalue())['error']), (2, 'paseo_models_unavailable'))

    def test_models_option_keeps_drift_exit_code_and_writes_nothing(self):
        def mut(ps): ps[0]['thinkingOptionId']='medium'
        self.assertEqual(run(fixture(mut), models=ids('claude-fable-5-2'))[0], 1)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text(json.dumps(fixture())); os.utime(p, (1_000_000_000, 1_000_000_000))
            m=Path(d)/'models.json'; m.write_text(json.dumps(ids('claude-fable-5-2')))
            before=(p.read_bytes(), p.stat().st_mtime_ns, m.read_bytes(), sorted(x.name for x in Path(d).iterdir()))
            with contextlib.redirect_stdout(io.StringIO()): code=paseo.main(['check','--config',str(p),'--paseo-models',str(m),'--model-catalog',str(Path(d)/'none.json')])
            self.assertEqual(code, 0)
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns, m.read_bytes(), sorted(x.name for x in Path(d).iterdir())), before)

if __name__=='__main__': unittest.main()
