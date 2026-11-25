"""Paseo sync/--restore tests. Temp dirs only: the real ~/.paseo is never read or written here."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from ai_policy import paseo
from ai_policy.bundle import PolicyError
from tests.test_paseo import BASE, fixture, fresh

LUNA={'slug':'gpt-6-luna','visibility':'list','supported_in_api':True}
TERRA={'slug':'gpt-6.1-terra','visibility':'list','supported_in_api':True}
FRESH_CATALOG=lambda: fresh([LUNA, TERRA])

def sha(b): return hashlib.sha256(b).hexdigest()

def dump(cfg): return json.dumps(cfg, indent=2, ensure_ascii=False)+'\n'

def live_like(mutate=None):
    """fixture() plus the shape of the real file: other top-level keys, an unmanaged profile with unicode and options, readable names."""
    def mut(ps):
        for p in ps: p['name']=p['id'].upper()+' 한글'
        ps.insert(0, {'id':'custom-x','name':'Custom','provider':'claude','model':'claude-haiku-5-5','modeId':'auto','thinkingOptionId':None,'options':{'a':[1,2]},'notes':'mine'})
        ps.append({'id':'custom-y','name':'Y','provider':'codex','model':'gpt-5-luna','modeId':'auto','thinkingOptionId':'low','notes':'n'})
        if mutate: mutate(ps)
    cfg=fixture(mut)
    d=cfg['daemon']; cfg={'version':1,'daemon':{'listen':'127.0.0.1:1','agentProfiles':d['agentProfiles'],'cors':['x']},'app':{'z':1,'a':2},'agents':{},'log':{'level':'info'}}
    return cfg

def profile(cfg, pid): return next(p for p in cfg['daemon']['agentProfiles'] if p['id']==pid)

class Env:
    def __init__(self, test, cfg=None, text=None, catalog=None):
        self.d=Path(tempfile.mkdtemp(prefix='paseo-sync-test-')); test.addCleanup(self.cleanup)
        self.cfg=self.d/'config.json'; self.state=self.d/'state'
        self.cfg.write_text(text if text is not None else dump(cfg or live_like())); os.chmod(self.cfg, 0o600)
        os.utime(self.cfg, (1_000_000_000, 1_000_000_000))
        self.catalog=self.d/'cat.json'
        if catalog is not None: self.catalog.write_text(json.dumps(catalog))
    def cleanup(self):
        import shutil; shutil.rmtree(self.d, ignore_errors=True)
    def args(self, *extra, plan=None):
        a=['sync','--config',str(self.cfg),'--state-dir',str(self.state),'--model-catalog',str(self.catalog)]+list(extra)
        return a+(['--plan-sha256',plan] if plan else [])
    def run(self, *extra, plan=None, argv=None):
        b=io.StringIO()
        with contextlib.redirect_stdout(b): code=paseo.main(argv if argv is not None else self.args(*extra, plan=plan))
        return code, json.loads(b.getvalue())
    def dry(self, *extra):
        code, out=self.run(*extra); return code, out
    def apply(self, *extra):
        code, out=self.run(*extra)
        if 'plan_sha256' not in out: return code, out
        return self.run(*extra, plan=out['plan_sha256'])
    def seed(self, profiles):
        self.state.mkdir(mode=0o700, exist_ok=True)
        (self.state/'state.json').write_text(json.dumps({'schema':1,'profiles':profiles}))
        os.chmod(self.state/'state.json', 0o600)
    def snap(self): return (self.cfg.read_bytes(), self.cfg.stat().st_mtime_ns, sorted(x.name for x in self.d.iterdir()))
    def loaded(self): return json.loads(self.cfg.read_text())
    def backups(self):
        b=self.state/'backups'; return sorted(b.iterdir()) if b.exists() else []

def edited(pid, **kw):
    def m(ps): profile({'daemon':{'agentProfiles':ps}}, pid).update(kw)
    return m

class SyncPlanTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        e=Env(self, live_like(edited('l4-critical', modeId='plan')))
        e.seed({'l4-critical':{'modeId':'plan'}}); seeded=(e.state/'state.json').read_bytes()
        before=e.snap()
        code, out=e.dry()
        self.assertEqual((code, out['changes'], out['dry_run']), (0, 1, True))
        self.assertRegex(out['plan_sha256'], '^[0-9a-f]{64}$')
        self.assertEqual(out['profiles']['l4-critical']['fields'], [{'field':'modeId','current':'plan','desired':'auto'}])
        self.assertEqual(e.snap(), before)
        self.assertEqual(sorted(x.name for x in e.state.iterdir()), ['state.json'])   # no backups dir, state untouched
        self.assertEqual((e.state/'state.json').read_bytes(), seeded)
        # fresh state dir is not created by a dry run either
        e2=Env(self); e2.dry(); self.assertFalse(e2.state.exists())

    def test_noop_plan_applies_nothing(self):
        e=Env(self); before=e.snap()
        code, out=e.dry(); self.assertEqual((code, out['changes']), (0, 0))
        code, out=e.run(plan=out['plan_sha256'])
        self.assertEqual((code, out['changes'], out['applied']), (0, 0, False))
        self.assertEqual(e.snap(), before); self.assertFalse(e.state.exists())
        self.assertFalse(out['daemon_reload_required'])

    def test_wrong_or_malformed_plan_hash_is_refused(self):
        e=Env(self, live_like(edited('l4-critical', modeId='plan'))); e.seed({'l4-critical':{'modeId':'plan'}}); before=e.snap()
        for h in ('0'*64, 'abc', 'Z'*64):
            code, out=e.run(plan=h); self.assertEqual(code, 2); self.assertIn('error', out)
            self.assertEqual(e.snap(), before); self.assertEqual(e.backups(), [])
        self.assertEqual(e.run(plan='0'*64)[1]['error'], 'plan_sha256_mismatch')

    def test_hash_changes_with_config_flags_and_catalog(self):
        e=Env(self, live_like(lambda ps: ps.pop(-2)), catalog=FRESH_CATALOG())   # lookup missing
        h0=e.dry()[1]['plan_sha256']; self.assertEqual(h0, e.dry()[1]['plan_sha256'])
        e.cfg.write_text(dump(live_like(lambda ps: (ps.pop(-2), ps[0].update(notes='z')))))
        self.assertNotEqual(h0, e.dry()[1]['plan_sha256'])
        out=e.dry('--include-provisional')[1]; self.assertNotEqual(h0, out['plan_sha256'])
        # a hash from another flag set cannot be applied
        before=e.snap(); self.assertEqual(e.run(plan=h0)[0], 2); self.assertEqual(e.snap(), before)

    def test_new_profile_shape_and_unknown_overwrite_id(self):
        e=Env(self, live_like(lambda ps: ps.pop(-2)), catalog=FRESH_CATALOG())
        code, out=e.dry(); row=out['profiles']['lookup']
        self.assertEqual((code, row['action']), (0, 'create'))
        self.assertEqual((row['new_profile']['options'], row['new_profile']['model'], row['new_profile']['notes']), (None, 'gpt-6-luna', BASE['paseo_profiles']['lookup']['description']))
        code, out=e.apply(); self.assertEqual(code, 0)   # on-disk key order of the appended profile
        self.assertEqual(list(profile(e.loaded(), 'lookup')), ['id','name','provider','model','modeId','thinkingOptionId','options','notes'])
        code, out=e.dry('--overwrite','nope'); self.assertEqual((code, out['error']), (2, 'overwrite_unknown_id'))
        code, out=e.dry('--overwrite','lookup,custom-x'); self.assertEqual((code, out['error']), (2, 'overwrite_unknown_id'))

class SyncApplyTests(unittest.TestCase):
    def setUp(self):
        def mut(ps):
            profile({'daemon':{'agentProfiles':ps}}, 'l4-critical').update(modeId='plan')
            ps.pop(-2)   # lookup missing -> will be created
        self.e=Env(self, live_like(mut), catalog=FRESH_CATALOG()); self.e.seed({'l4-critical':{'modeId':'plan'}})
        self.orig=self.e.cfg.read_bytes(); self.origcfg=json.loads(self.orig)

    def test_apply_changes_only_managed_fields_and_keeps_everything_else(self):
        e=self.e; code, out=e.apply()
        self.assertEqual((code, out['applied'], out['changes']), (0, True, 2))
        self.assertIs(out['daemon_reload_required'], True)
        self.assertIn('restart', out['note'].lower()); self.assertIn('overwrite', out['note'].lower())
        new=e.loaded(); exp=json.loads(self.orig)
        profile(exp, 'l4-critical')['modeId']='auto'
        exp['daemon']['agentProfiles'].append({'id':'lookup','name':'lookup','provider':'codex','model':'gpt-6-luna','modeId':'auto','thinkingOptionId':'medium','options':None,'notes':BASE['paseo_profiles']['lookup']['description']})
        self.assertEqual(new, exp)
        self.assertEqual(e.cfg.read_text(), dump(exp))             # byte-level: order, indent, unicode preserved
        self.assertEqual(list(new), list(self.origcfg)); self.assertEqual(list(new['daemon']), list(self.origcfg['daemon']))
        for pid in ('custom-x','custom-y','root-orchestrator'): self.assertEqual(profile(new, pid), profile(self.origcfg, pid))
        for p in new['daemon']['agentProfiles']:
            if p['id']!='lookup': self.assertEqual((p['name'], p['notes']), (profile(self.origcfg, p['id'])['name'], profile(self.origcfg, p['id'])['notes']))
        self.assertIn('한글', e.cfg.read_text())     # unicode kept literally, not escaped

    def test_backup_state_and_modes(self):
        e=self.e; code, out=e.apply()
        b=e.backups(); self.assertEqual(len(b), 1)
        self.assertEqual(b[0].read_bytes(), self.orig)
        self.assertRegex(b[0].name, r'^config\.\d{8}T\d{6}Z\.%s\.json$'%sha(self.orig)[:8])
        self.assertEqual(stat.S_IMODE(b[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((e.state/'backups').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(e.state.stat().st_mode), 0o700)
        st=json.loads((e.state/'state.json').read_text())
        self.assertEqual(stat.S_IMODE((e.state/'state.json').stat().st_mode), 0o600)
        self.assertEqual(st['profiles']['l4-critical'], {'provider':'claude','model':'claude-opus-5-5','modeId':'auto','thinkingOptionId':'high'})
        self.assertEqual(st['profiles']['lookup']['model'], 'gpt-6-luna'); self.assertNotIn('root-orchestrator', st['profiles'])
        self.assertNotIn(b[0].read_text(), json.dumps(out))   # backup content is never printed
        # second run is a no-op and leaves the file alone
        snap=e.snap(); code, out=e.apply(); self.assertEqual((code, out['changes']), (0, 0)); self.assertEqual(e.snap(), snap)
        self.assertEqual(len(e.backups()), 1)

    def test_file_changed_before_replace_aborts_without_write_or_temp(self):
        e=self.e; code, out=e.dry(); h=out['plan_sha256']
        other=dump(live_like(edited('root-orchestrator', notes='someone else')))
        def hook(*a, **k): e.cfg.write_text(other)
        with mock.patch.object(paseo, '_before_replace', side_effect=hook):
            code, out=e.run(plan=h)
        self.assertEqual((code, out['error']), (2, 'config_changed'))
        self.assertEqual(e.cfg.read_text(), other)                     # the foreign edit survives
        self.assertEqual([x.name for x in e.d.iterdir() if x.name.endswith('.tmp')], [])
        self.assertEqual(json.loads((e.state/'state.json').read_text())['profiles'], {'l4-critical':{'modeId':'plan'}})   # state not advanced

    def test_file_changed_between_plan_and_apply_changes_hash(self):
        e=self.e; h=e.dry()[1]['plan_sha256']
        e.cfg.write_text(dump(live_like(edited('root-orchestrator', notes='x'))))
        before=e.snap(); code, out=e.run(plan=h); self.assertEqual((code, out['error']), (2, 'plan_sha256_mismatch')); self.assertEqual(e.snap(), before)

    def test_result_mode_and_no_stray_temp(self):
        e=self.e; os.chmod(e.cfg, 0o640); e.apply()
        self.assertEqual(stat.S_IMODE(e.cfg.stat().st_mode), 0o640)
        self.assertEqual([x.name for x in e.d.iterdir() if x.name.startswith('.config.') or x.name.endswith('.tmp')], [])
        e2=Env(self, live_like(edited('l4-critical', modeId='plan'))); e2.seed({'l4-critical':{'modeId':'plan'}}); e2.apply()
        self.assertEqual(stat.S_IMODE(e2.cfg.stat().st_mode), 0o600)
        self.assertEqual(sorted(x.name for x in e2.d.iterdir()), ['config.json','state'])

    def test_format_drift_guard(self):
        for text in (json.dumps(self.origcfg, indent=4, ensure_ascii=False)+'\n', json.dumps(self.origcfg, indent=2)+'\n', json.dumps(self.origcfg, indent=2, ensure_ascii=False)):
            e=Env(self, text=text, catalog=FRESH_CATALOG()); e.seed({'l4-critical':{'modeId':'plan'}}); before=e.snap()
            code, out=e.run(); self.assertEqual((code, out.get('error')), (2, 'config_format_drift'))
            code, out=e.run(plan='0'*64); self.assertEqual(code, 2)
            self.assertEqual(e.snap(), before); self.assertEqual(e.backups(), [])
        # a drifted file with nothing to write is not an error
        e=Env(self, text=json.dumps(live_like(), indent=4)); self.assertEqual(e.run()[0], 0)

    def test_post_write_verification_failure_is_reported_and_state_not_updated(self):
        e=self.e; h=e.dry()[1]['plan_sha256']
        real=paseo._read_bytes
        calls=[]
        def flaky(path):
            data=real(path); calls.append(1)
            return data.replace(b'"auto"', b'"AUTO"') if len(calls)>=3 else data
        with mock.patch.object(paseo, '_read_bytes', side_effect=flaky): code, out=e.run(plan=h)
        self.assertEqual((code, out['error']), (2, 'post_write_verification_failed'))
        self.assertEqual(json.loads((e.state/'state.json').read_text())['profiles'], {'l4-critical':{'modeId':'plan'}})

class SyncRuleTests(unittest.TestCase):
    def test_hand_edited_profile_is_conflict_and_overwrite_writes_it(self):
        e=Env(self, live_like(edited('l4-critical', modeId='plan'))); before=e.snap()
        code, out=e.apply()                       # no state record at all
        self.assertEqual((code, out['profiles']['l4-critical']['action'], out['conflicts']), (1, 'conflict', ['l4-critical']))
        self.assertEqual(e.snap(), before)
        e.seed({'l4-critical':{'modeId':'auto'}})  # state says we wrote 'auto', file says 'plan': hand edit
        code, out=e.apply(); self.assertEqual((code, out['changes']), (1, 0)); self.assertEqual(e.snap()[:2], before[:2])
        code, out=e.apply('--overwrite','l4-critical')
        self.assertEqual((code, out['changes'], out['applied']), (0, 1, True)); self.assertEqual(profile(e.loaded(),'l4-critical')['modeId'], 'auto')
        self.assertTrue(out['profiles']['l4-critical']['overwritten'])
        self.assertEqual(json.loads((e.state/'state.json').read_text())['profiles']['l4-critical']['modeId'], 'auto')

    def test_conflict_does_not_block_other_confirmed_changes(self):
        def mut(ps): edited('l4-critical', modeId='plan')(ps); edited('l5-last-resort', modeId='plan')(ps)
        e=Env(self, live_like(mut)); e.seed({'l5-last-resort':{'modeId':'plan'}})
        code, out=e.apply()
        self.assertEqual((code, out['changes'], out['conflicts']), (1, 1, ['l4-critical']))
        new=e.loaded(); self.assertEqual((profile(new,'l4-critical')['modeId'], profile(new,'l5-last-resort')['modeId']), ('plan','auto'))
        e.cfg.write_text(dump(new))   # multiple-field edits, comma list
        code, out=e.apply('--overwrite','l4-critical,l5-last-resort'); self.assertEqual(code, 0)

    def test_stale_or_missing_catalog_never_changes_codex_model(self):
        for catalog in (None, fresh([]), {'fetched_at':'2000-01-01T00:00:00Z','models':[LUNA,TERRA]}):
            for current in ('gpt-5-luna', 'gpt-7-luna'):
                e=Env(self, live_like(edited('dev-l1-simple', model=current)), catalog=catalog)
                e.seed({'dev-l1-simple':{'model':current}}); before=e.snap()
                code, out=e.apply('--overwrite','dev-l1-simple')
                self.assertEqual((code, out['profiles']['dev-l1-simple']['action']), (1, 'refused:pinned_fallback'), (catalog, current))
                self.assertEqual((out['refusals'], out['changes']), (['dev-l1-simple'], 0))
                self.assertEqual(e.snap(), before)

    def test_never_downgrade_and_overwrite_does_not_override_refusal(self):
        e=Env(self, live_like(lambda ps: (edited('dev-l1-simple', model='gpt-7-luna')(ps), edited('l5-last-resort', model='claude-fable-5-2')(ps),
                                          edited('l4-critical', model='claude-opus-5-4')(ps))), catalog=FRESH_CATALOG())
        e.seed({'dev-l1-simple':{'model':'gpt-7-luna'},'l5-last-resort':{'model':'claude-fable-5-2'},'l4-critical':{'model':'claude-opus-5-4'}})
        code, out=e.apply('--overwrite','dev-l1-simple,l5-last-resort')
        self.assertEqual(code, 1)
        self.assertEqual(out['profiles']['dev-l1-simple']['action'], 'refused:downgrade')
        self.assertEqual(out['profiles']['l5-last-resort']['action'], 'refused:downgrade')
        self.assertEqual(out['profiles']['l4-critical']['action'], 'update')      # upgrade to the pinned id is fine
        new=e.loaded(); self.assertEqual((profile(new,'dev-l1-simple')['model'], profile(new,'l5-last-resort')['model'], profile(new,'l4-critical')['model']),
                                         ('gpt-7-luna','claude-fable-5-2','claude-opus-5-5'))

    def test_cross_family_codex_change_is_not_a_downgrade_but_same_family_is(self):
        for pid, current, want in (('dev-l1-simple','gpt-6.1-terra','gpt-6-luna'), ('review-claude-work','gpt-6.2-sol','gpt-6.1-terra')):
            e=Env(self, live_like(edited(pid, model=current)), catalog=FRESH_CATALOG()); e.seed({pid:{'model':current}})
            code, out=e.apply()
            self.assertEqual((code, out['profiles'][pid]['action'], out['refusals']), (0, 'update', []), pid)
            self.assertEqual(profile(e.loaded(), pid)['model'], want)
            e=Env(self, live_like(edited(pid, model=current)), catalog=FRESH_CATALOG())      # a hand edit: conflict, but --overwrite may fix it
            self.assertEqual(e.dry()[1]['profiles'][pid]['action'], 'conflict')
            code, out=e.apply('--overwrite', pid); self.assertEqual((code, out['profiles'][pid]['action']), (0, 'update'))
        # same family, lower generation stays refused and cannot be overridden
        e=Env(self, live_like(edited('review-claude-work', model='gpt-7-terra')), catalog=FRESH_CATALOG()); e.seed({'review-claude-work':{'model':'gpt-7-terra'}})
        code, out=e.apply('--overwrite','review-claude-work'); self.assertEqual((code, out['profiles']['review-claude-work']['action']), (1, 'refused:downgrade'))

    def test_codex_change_with_fresh_catalog_is_written_to_pinned_id_only(self):
        e=Env(self, live_like(edited('dev-l1-simple', model='gpt-5-luna')), catalog=FRESH_CATALOG()); e.seed({'dev-l1-simple':{'model':'gpt-5-luna'}})
        code, out=e.apply(); self.assertEqual((code, out['changes']), (0, 1)); self.assertEqual(profile(e.loaded(),'dev-l1-simple')['model'], 'gpt-6-luna')

    def test_claude_profiles_keep_pinned_id_despite_newer_alias(self):
        e=Env(self)                      # fixture already at the pinned ids; policy records a newer observed alias for fable
        code, out=e.apply(); self.assertEqual((code, out['changes']), (0, 0))
        e=Env(self, live_like(edited('l5-last-resort', model='claude-fable-5-0'))); e.seed({'l5-last-resort':{'model':'claude-fable-5-0'}})
        code, out=e.apply(); self.assertEqual(profile(e.loaded(),'l5-last-resort')['model'], 'claude-fable-5-1')

    def test_provisional_only_created_with_flag(self):
        e=Env(self, catalog=FRESH_CATALOG())
        code, out=e.apply(); self.assertEqual((code, out['changes']), (0, 0))
        self.assertEqual({pid for pid,r in out['profiles'].items() if r['action']=='skip_provisional'}, {'scout','ui-verify','l5-alt-astra'})
        self.assertEqual(e.loaded(), json.loads(e.cfg.read_text()))
        ids=lambda: [p['id'] for p in e.loaded()['daemon']['agentProfiles']]
        self.assertNotIn('scout', ids())
        code, out=e.apply('--include-provisional'); self.assertEqual((code, out['changes']), (0, 3))
        self.assertEqual(ids()[-3:], ['scout','ui-verify','l5-alt-astra'])
        scout=profile(e.loaded(),'scout'); self.assertEqual((scout['modeId'], 'thinkingOptionId' in scout, scout['model']), ('plan', False, 'claude-haiku-5-5'))
        self.assertEqual(profile(e.loaded(),'l5-alt-astra')['model'], 'gpt-6.2-astra')

    def test_duplicate_managed_id_is_an_error(self):
        e=Env(self, live_like(lambda ps: ps.append(dict(ps[1])))); before=e.snap()
        code, out=e.run(); self.assertEqual((code, out['error']), (2, 'duplicate_profile_id')); self.assertEqual(e.snap(), before)

    def test_corrupt_or_unsafe_state_is_an_error(self):
        e=Env(self, live_like(edited('l4-critical', modeId='plan'))); e.state.mkdir(mode=0o700); (e.state/'state.json').write_text('{nope')
        self.assertEqual(e.run()[1]['error'], 'state_invalid')
        (e.state/'state.json').write_text('{"schema":1,"profiles":{"l4-critical":{"modeId":"plan"}}}'); os.chmod(e.state, 0o755)
        self.assertEqual(e.run()[1]['error'], 'state_dir_unsafe')

    def test_default_state_dir_is_per_user_keyed_by_config_path_and_never_in_the_repo(self):
        repo=Path(paseo.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'XDG_STATE_HOME': d}):
            c1, c2=Path(d)/'a'/'config.json', Path(d)/'b'/'config.json'
            s1, s2=paseo.default_state_dir(c1), paseo.default_state_dir(c2)
            self.assertEqual(s1, Path(d)/'ai-policy'/'paseo-sync'/sha(str(os.path.abspath(c1)).encode())[:8])
            self.assertNotEqual(s1, s2); self.assertEqual(s1, paseo.default_state_dir(str(c1)))
            self.assertNotIn(repo, s1.parents)
        with mock.patch.dict(os.environ, {'XDG_STATE_HOME': ''}):
            self.assertEqual(paseo.default_state_dir('/x/config.json').parent, Path.home()/'.local'/'state'/'ai-policy'/'paseo-sync')
        with mock.patch.dict(os.environ, {'XDG_STATE_HOME': 'relative/dir'}):   # a relative XDG path is ignored
            self.assertEqual(paseo.default_state_dir('/x/config.json').parent, Path.home()/'.local'/'state'/'ai-policy'/'paseo-sync')
        self.assertIn('.local-artifacts/', (repo/'.gitignore').read_text().split())

    def test_default_state_dir_is_used_without_state_dir_flag_and_created_private(self):
        e=Env(self, live_like(edited('l4-critical', modeId='plan')), catalog=FRESH_CATALOG())
        with tempfile.TemporaryDirectory() as xdg, mock.patch.dict(os.environ, {'XDG_STATE_HOME': xdg}):
            os.chmod(xdg, 0o755)
            base=['sync','--config',str(e.cfg),'--model-catalog',str(e.catalog)]
            b=io.StringIO()
            with contextlib.redirect_stdout(b): code=paseo.main(base)      # dry run creates nothing
            self.assertEqual(sorted(x.name for x in Path(xdg).iterdir()), [])
            b=io.StringIO()
            with contextlib.redirect_stdout(b): paseo.main(base+['--overwrite','l4-critical'])
            h=json.loads(b.getvalue())['plan_sha256']
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(paseo.main(base+['--overwrite','l4-critical','--plan-sha256',h]), 0)
            sd=paseo.default_state_dir(e.cfg)
            for d in (Path(xdg)/'ai-policy', Path(xdg)/'ai-policy'/'paseo-sync', sd, sd/'backups'): self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700, d)
            self.assertEqual(len(list((sd/'backups').iterdir())), 1); self.assertTrue((sd/'state.json').exists())

class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.e=Env(self, live_like(edited('l4-critical', modeId='plan'))); self.e.seed({'l4-critical':{'modeId':'plan'}})
        self.orig=self.e.cfg.read_bytes(); self.e.apply()
        self.assertNotEqual(self.e.cfg.read_bytes(), self.orig)
        self.backup=self.e.backups()[0]
    def rargs(self, path, plan=None):
        a=['sync','--config',str(self.e.cfg),'--state-dir',str(self.e.state),'--restore',str(path)]
        return a+(['--plan-sha256',plan] if plan else [])
    def rest(self, path, plan=None): return self.e.run(argv=self.rargs(path, plan))

    def test_dry_run_default_then_apply_restores_exact_bytes(self):
        e=self.e; before=e.snap(); nb=len(e.backups())
        code, out=self.rest(self.backup)
        self.assertEqual((code, out['dry_run'], out['changes']), (0, True, 1)); self.assertEqual(e.snap(), before); self.assertEqual(len(e.backups()), nb)
        code, out=self.rest(self.backup, out['plan_sha256'])
        self.assertEqual((code, out['applied']), (0, True)); self.assertIs(out['daemon_reload_required'], True); self.assertIn('restart', out['note'].lower())
        self.assertEqual(e.cfg.read_bytes(), self.orig); self.assertEqual(stat.S_IMODE(e.cfg.stat().st_mode), 0o600)
        self.assertEqual(self.backup.read_bytes(), self.orig)
        self.assertEqual(len(e.backups()), nb+1)      # pre-restore copy of the file being replaced
        self.assertEqual([x.name for x in e.d.iterdir() if x.name.endswith('.tmp')], [])
        # restoring what is already there is a no-op
        snap=e.snap(); code, out=self.rest(self.backup); code, out=self.rest(self.backup, out['plan_sha256'])
        self.assertEqual((code, out['changes'], out['applied']), (0, 0, False)); self.assertEqual(e.snap(), snap)

    def test_wrong_hash_refused_and_file_change_detected(self):
        e=self.e; before=e.snap()
        self.assertEqual(self.rest(self.backup, '1'*64)[1]['error'], 'plan_sha256_mismatch'); self.assertEqual(e.snap(), before)
        h=self.rest(self.backup)[1]['plan_sha256']
        with mock.patch.object(paseo, '_before_replace', side_effect=lambda *a, **k: e.cfg.write_text('{"x":1}\n')):
            code, out=self.rest(self.backup, h)
        self.assertEqual((code, out['error']), (2, 'config_changed')); self.assertEqual(e.cfg.read_text(), '{"x":1}\n')
        self.assertEqual([x.name for x in e.d.iterdir() if x.name.endswith('.tmp')], [])

    def test_refuses_outside_symlink_non_regular_and_bad_names(self):
        e=self.e; before=e.snap()
        outside=e.d/('config.20260101T000000Z.%s.json'%sha(self.orig)[:8]); outside.write_bytes(self.orig)
        link=e.state/'backups'/('config.20260101T000000Z.%s.json'%sha(self.orig)[:8]); link.symlink_to(self.backup)
        fifo_dir=e.state/'backups'/('config.20260102T000000Z.%s.json'%sha(self.orig)[:8]); fifo_dir.mkdir()
        sub=e.state/'backups'/'sub'; sub.mkdir(); (sub/self.backup.name).write_bytes(self.orig)
        bad_name=e.state/'backups'/'evil.json'; bad_name.write_bytes(self.orig)
        corrupt=e.state/'backups'/'config.20260103T000000Z.deadbeef.json'; corrupt.write_bytes(self.orig)
        notjson=e.state/'backups'/('config.20260104T000000Z.%s.json'%sha(b'{bad')[:8]); notjson.write_bytes(b'{bad')
        fifo=e.state/'backups'/('config.20260105T000000Z.%s.json'%sha(self.orig)[:8]); os.mkfifo(fifo)
        nbk=len(e.backups())
        for path in (outside, link, fifo_dir, fifo, sub/self.backup.name, bad_name, corrupt, notjson, e.state/'backups'/'..'/'..'/outside.name,
                     e.state/'state.json', e.state/'nope', e.state/'backups'/'missing.json', e.state/'backups'):
            code, out=self.rest(path); self.assertEqual(code, 2, path); self.assertIn('error', out, path)
            code, out=self.rest(path, '0'*64); self.assertEqual(code, 2, path)
        self.assertEqual(e.snap()[:2], before[:2]); self.assertEqual(len(e.backups()), nbk)   # no restore pre-backup was created
        # traversal that normalises back into backups/ is the same file and is fine; one that leaves it is refused
        (e.d/'x').mkdir(); self.assertEqual(self.rest(e.d/'x'/'..'/'state'/'backups'/self.backup.name)[0], 0)
        symdir=e.d/'linkdir'; symdir.symlink_to(e.state/'backups')
        self.assertEqual(self.rest(symdir/self.backup.name)[0], 0)   # same real directory: allowed (resolved before the check)

    def test_symlinked_backups_dir_is_refused(self):
        e=self.e; real=e.d/'real'; real.mkdir(mode=0o700); (real/self.backup.name).write_bytes(self.orig)
        import shutil; shutil.rmtree(e.state/'backups'); (e.state/'backups').symlink_to(real)
        code, out=self.rest(e.state/'backups'/self.backup.name); self.assertEqual((code, out['error']), (2, 'backups_dir_unsafe'))

    def test_restore_rejects_sync_only_flags(self):
        e=self.e; a=self.rargs(self.backup)+['--include-provisional']
        self.assertEqual(e.run(argv=a)[0], 2)
        self.assertEqual(e.run(argv=self.rargs(self.backup)+['--overwrite','lookup'])[0], 2)

if __name__=='__main__': unittest.main()
