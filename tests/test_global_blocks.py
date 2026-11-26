"""Global instruction block tests (render, separation, sync/restore safety). Temp dirs only: the real ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md
are never read or written here. Surrounding text in every target is synthetic."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest

from ai_policy import globalblocks as gb
from ai_policy.bundle import PolicyError

REPO=Path(__file__).resolve().parent.parent
GLOBAL=REPO/'policy'/'global'
FIX=Path(__file__).resolve().parent/'fixtures'/'global-blocks'
HOSTS=('claude', 'codex')
PRE='# 개인 지침 ✓ — 합성 테스트\n\n| 항목 | 값 |\n| --- | --- |\n| a | b |\n\n'
POST='\n## 사용자 섹션\n\n한글 😀 text\n| x | y |\n| - | - |\n'

def sha(b): return hashlib.sha256(b).hexdigest()
def legacy(host): return (FIX/('legacy-%s-1.4.0.md'%host)).read_text(encoding='utf-8')
def cfg(): return gb.load_config()

def target(tmp_path, host='claude', mid=None, pre=PRE, post=POST, name=None):
    t=tmp_path/(name or ('CLAUDE.md' if host=='claude' else 'AGENTS.md'))
    t.write_text(pre+(legacy(host) if mid is None else mid)+post, encoding='utf-8', newline='')
    return t

def cli(*args):
    out=io.StringIO()
    with contextlib.redirect_stdout(out): code=gb.main([str(a) for a in args])
    text=out.getvalue()
    try: return code, json.loads(text)
    except ValueError: return code, text

def sync(host, t, *extra):
    return cli('sync', '--host', host, '--target', t, *extra)

def apply(host, t, sd, *extra):
    code, plan=sync(host, t, '--state-dir', sd, *extra)
    assert code==0 and plan['dry_run'] is True, plan
    return sync(host, t, '--state-dir', sd, '--plan-sha256', plan['plan_sha256'], *extra)

ALL=('core', 'orca', 'paseo')
HO=[(h, o) for h in HOSTS for o in (False, True)]
def R(host, orca=False): return gb.render(host, selected=gb.selected_blocks(host, cfg(), orca))
def OA(orca): return ('--with-orca',) if orca else ()

def files(d): return sorted(p.name for p in Path(d).iterdir())

# ---- render ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('host, orca', HO)
def test_render_is_deterministic_with_exact_envelope(host, orca):
    a=R(host, orca); assert a==R(host, orca)
    c=cfg(); parts=[]
    names=('core', 'orca', 'paseo') if orca else ('core', 'paseo')
    assert gb.selected_blocks(host, c, orca)==list(names)
    for n in names:
        mk=c[n]['markers'][host] if n=='core' else c[n]['marker']
        src=c[n]['sources'][host] if n=='core' else c[n]['source']
        body=(GLOBAL/src).read_text(encoding='utf-8').rstrip('\n')
        parts.append('<!-- %s:start version=%s -->\n%s\n<!-- %s:end -->\n'%(mk, c[n]['version'], body, mk))
    assert a=='\n'.join(parts)
    assert a.endswith('-->\n') and not a.endswith('\n\n')
    assert '\r' not in a
    assert re.findall(r'^<!-- ai-agent-policy:(\S+) ', a, re.M)==['core-%s:start'%host, 'core-%s:end'%host]+(['orca-policy:start', 'orca-policy:end'] if orca else [])+['paseo-policy:start', 'paseo-policy:end']
    assert (c['core']['version'], c['orca']['version'], c['paseo']['version'])==('1.5.0', '1.4.0', '0.1.1-draft')

def test_default_set_is_core_plus_paseo_and_orca_is_opt_in(capsys):
    c=cfg()
    for h in HOSTS:
        assert c['hosts'][h]['default_blocks']==['core', 'paseo'] and gb.selected_blocks(h, c)==['core', 'paseo'] and gb.selected_blocks(h, c, True)==['core', 'orca', 'paseo']
        assert 'orca-policy' not in gb.render(h) and 'orca-policy' in R(h, True)
        assert gb.main(['render', '--host', h])==0 and capsys.readouterr().out==gb.render(h)
        assert gb.main(['render', '--host', h, '--with-orca'])==0 and capsys.readouterr().out==R(h, True)
    assert len(R('claude', True).encode())>len(gb.render('claude').encode())

@pytest.mark.parametrize('host', HOSTS)
def test_default_set_stays_within_the_size_budget_versus_the_legacy_block(host):
    delta=len(gb.render(host).encode('utf-8'))-len(legacy(host).encode('utf-8'))
    assert delta<=2000, delta   # the always-loaded text grows by at most ~2 KB per host with the default core + paseo set
    assert len(R(host, True).encode('utf-8'))-len(legacy(host).encode('utf-8'))>delta

def test_render_strips_trailing_newlines_of_body():
    assert gb.render_block('m:x', '1', 'a\nb\n\n\n')=='<!-- m:x:start version=1 -->\na\nb\n<!-- m:x:end -->\n'

def test_render_cli_matches_function_and_rejects_bad_host(capsys):
    assert gb.main(['render', '--host', 'codex'])==0
    assert capsys.readouterr().out==gb.render('codex')
    with pytest.raises(SystemExit): gb.main(['render', '--host', 'other'])

def test_module_runs_as_script():
    r=subprocess.run([sys.executable, '-B', '-m', 'ai_policy.globalblocks', 'render', '--host', 'claude'], cwd=REPO, capture_output=True, text=True)
    assert r.returncode==0 and r.stdout==gb.render('claude')

# ---- separation -----------------------------------------------------------------------------------------------------------------------------
GATING='Paseo 프로젝트 정책이 설치되고 Paseo 업무 context가 확인되면(부모 에이전트의 배정 메시지와 부모 라벨 `paseo.parent-agent-id`가 증거이며, `PASEO_AGENT_ID` 환경 변수·Paseo CLI 설치·Paseo MCP 도구 존재만으로는 Paseo 업무로 판정하지 않는다) 실행 위치·Root/Coordinator/Worker 역할·모델 선택·정산·최소 Task 등록 부트스트랩은 그 정책을 따른다.'

def test_orca_and_paseo_sources_are_separated():
    orca=(GLOBAL/'orca.md').read_text(encoding='utf-8'); paseo=(GLOBAL/'paseo.md').read_text(encoding='utf-8')
    assert 'paseo' not in orca.lower() and 'orca' not in paseo.lower()
    assert '병행기' in orca and orca.count('병행기·보관')==1 and '병행기' not in paseo
    assert 'orca-worker-lifecycle.md' in orca
    bullets=[l for l in paseo.splitlines() if l.startswith('- ')]
    assert len(bullets)==3 and len(paseo.encode())<=1400
    assert GATING in bullets[0] and '설치된 Paseo 스킬과 해당 프로젝트 지침' in bullets[0]
    assert 'Worker는 재위임하지 않으며 Owner가 자식 목록을 점검한다' in bullets[0] and 'Codex는 Worker로만' in bullets[0]
    assert all(x in bullets[1] for x in ('턴 종료 신호', 'archive_agent', 'Human Gate'))
    for ref in ('paseo-agent-lifecycle.md', 'paseo-model-routing.md', 'policy/paseo-common.md'): assert ref in bullets[2]
    # profile mechanics live in docs/paseo-model-routing.md, not in the always-loaded block
    assert 'paseo_profiles' not in paseo and 'daemon reload' not in paseo and 'paseo_create_agent' not in paseo
    doc=(REPO/'docs'/'paseo-model-routing.md').read_text(encoding='utf-8')
    for fact in ('--host paseo', 'paseo_create_agent', 'paseo_profile', 'plan_mode', 'ai_policy.paseo sync', 'daemon reload'): assert fact in doc

def test_orca_keeps_the_production_release_rule_and_does_not_misattribute_it():
    orca=(GLOBAL/'orca.md').read_text(encoding='utf-8')
    for phrase in ('완료 조건과 운영 반영 필요 여부를 정한다', '실제 대상 환경, 반영된 릴리스 식별자, 반영 후 정상 동작 확인 결과와 근거를 모두 확인한 뒤 완료로 보고한다',
                   '배포 대기·실패·미확인은 남은 조치와 함께 기록한다', '운영 반영이 없는 업무는 합의한 완료 조건과 필수 검증 결과로 닫는다'):
        assert phrase in orca
    pointer=next(l for l in orca.splitlines() if 'Controller resume and handoff' in l)
    assert '운영 반영' not in pointer and 'Worker 결과' in pointer

@pytest.mark.parametrize('host', HOSTS)
def test_core_mentions_environments_only_in_orchestration_paragraph(host):
    body=(GLOBAL/('core.%s.md'%host)).read_text(encoding='utf-8')
    assert body.count('## Orchestration environments')==1
    i=body.index('## Orchestration environments'); j=body.find('\n## ', i+5)
    para=body[i:j if j!=-1 else len(body)]
    assert 'Orca' in para and 'Paseo' in para
    rest=body[:i]+(body[j:] if j!=-1 else '')
    assert not re.search('orca|paseo', rest, re.I)
    assert '병행기' not in body and '1.5.0' in body.splitlines()[0]
    body_para=para.split('\n', 2)[2].strip()
    assert '\n' not in body_para   # one short paragraph
    assert 'existing Orca' in body_para and '~/Project/ETC/ai-agent-policy/docs/orca-worker-lifecycle.md' in body_para and '`ai-agent-policy:paseo-policy`' in body_para
    assert 'not evidence' in body_para and 'this core policy applies unchanged' in body_para and len(body_para)<=700

@pytest.mark.parametrize('host', HOSTS)
def test_sources_contain_no_marker_tokens_and_no_cr(host):
    for n in ('core.%s.md'%host, 'orca.md', 'paseo.md'):
        t=(GLOBAL/n).read_text(encoding='utf-8')
        assert not gb.TOKEN.search(t) and '\r' not in t

# ---- golden / provenance ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('host', HOSTS)
def test_known_legacy_hash_pins_the_fixture(host):
    raw=(FIX/('legacy-%s-1.4.0.md'%host)).read_bytes()
    assert sha(raw) in cfg()['legacy'][host]['known_sha256']
    lines=raw.decode('utf-8').split('\n')
    assert lines[0].startswith('<!-- ai-agent-policy:%s:start version=1.4.0 -->'%host) and lines[-2]=='<!-- ai-agent-policy:%s:end -->'%host and lines[-1]==''
    assert b'\r' not in raw

def _sentences(par): return [x.strip() for x in re.split(r'(?<=\.)\s+', par.strip())]

@pytest.mark.parametrize('host', HOSTS)
def test_every_legacy_sentence_is_accounted_for_in_core_or_paseo(host):
    old=legacy(host).split('\n')[1:-2]
    core_text=(GLOBAL/('core.%s.md'%host)).read_text(encoding='utf-8'); core=core_text.rstrip('\n').split('\n')
    paseo=(GLOBAL/'paseo.md').read_text(encoding='utf-8')
    par=next(l for l in old if l.startswith('For confirmed Paseo-managed work'))
    # only the title, the date line, the Paseo heading and the Paseo paragraph may differ; everything else is verbatim
    assert set(old)-set(core)=={old[0], '## Paseo and project policies', par}|{l for l in old if l.startswith('Updated: ')}
    added=[l for l in core if l not in old and not l.startswith('Updated: ') and '1.5.0' not in l]
    assert added==[
        '## Project policies', 'Preserve user-owned work. Follow project Task IDs, branch mappings, documentation, and completion gates when applicable.',
        '## Orchestration environments', next(l for l in core if l.startswith('Orca-managed'))]
    s=_sentences(par); assert len(s)==4
    assert s[0]=='For confirmed Paseo-managed work, use the installed Paseo skill and applicable project instructions.' and '설치된 Paseo 스킬과 해당 프로젝트 지침' in paseo
    assert s[1]=='Paseo manages agents and workspaces; verify results and preserve user-owned work.' and 'Preserve user-owned work.' in core_text
    assert s[2]=='Follow project Task IDs, branch mappings, documentation, and completion gates when applicable.' and s[2] in core_text
    assert s[3]=='Do not infer a Paseo-managed task merely from the presence of the CLI.' and 'not evidence' in core_text

# ---- legacy -> three blocks ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('host, orca', HO)
def test_legacy_replaced_by_selected_blocks_preserving_outside_bytes(tmp_path, host, orca):
    n=3 if orca else 2
    t=target(tmp_path, host); before=t.read_bytes()
    code, plan=sync(host, t, '--state-dir', tmp_path/'st', *OA(orca))
    assert code==0 and plan['dry_run'] is True and plan['applied'] is False and plan['state']=='legacy'
    assert t.read_bytes()==before and not (tmp_path/'st').exists()
    assert plan['file_before_sha256']==sha(before) and plan['legacy']['known'] is True
    assert [b['action'] for b in plan['blocks']]==['add']*n and plan['changes']==n and plan['selected_blocks']==gb.selected_blocks(host, cfg(), orca)
    assert plan['diff']['lines_after']==sum(b['lines'] for b in plan['blocks'])+n-1
    assert 'content' not in json.dumps(plan) and '개인 지침' not in json.dumps(plan)
    code, res=apply(host, t, tmp_path/'st', *OA(orca))
    assert code==0 and res['applied'] is True and res['note']==gb.NOTE and res['file_after_sha256']==sha(t.read_bytes())
    after=t.read_bytes()
    assert after==(PRE+R(host, orca)+POST).encode('utf-8') and (b'orca-policy' in after)==orca
    assert after.startswith(PRE.encode('utf-8')) and after.endswith(POST.encode('utf-8'))
    c, chk=cli('check', '--host', host, '--target', t, *OA(orca))
    assert c==0 and chk['state']=='current' and chk['up_to_date'] is True and len(chk['blocks'])==n and all(b['present'] and b['up_to_date'] for b in chk['blocks'].values())

def test_check_reports_legacy_none_unrecognized_partial_and_errors(tmp_path):
    t=target(tmp_path)
    c, r=cli('check', '--host', 'claude', '--target', t); assert c==1 and r['state']=='legacy' and r['legacy']['known'] is True and r['up_to_date'] is False
    t2=tmp_path/'none.md'; t2.write_text('plain\n'); c, r=cli('check', '--host', 'claude', '--target', t2); assert c==1 and r['state']=='none'
    t3=target(tmp_path, mid=legacy('claude').replace('Sonnet', 'Sonnett', 1), name='x.md'); c, r=cli('check', '--host', 'claude', '--target', t3); assert c==1 and r['state']=='unrecognized'
    t4=tmp_path/'p.md'; t4.write_text(PRE+gb.render_blocks('claude')[0][1]); c, r=cli('check', '--host', 'claude', '--target', t4); assert c==1 and r['state']=='partial'
    t5=tmp_path/'d.md'; t5.write_text(legacy('claude')*2); c, r=cli('check', '--host', 'claude', '--target', t5); assert c==2 and r['error']=='duplicate_markers'
    c, r=cli('check', '--host', 'claude', '--target', tmp_path/'missing.md'); assert c==2 and r['error']=='target_unavailable'

@pytest.mark.parametrize('host, other', (('claude', 'codex'), ('codex', 'claude')))
def test_migrated_file_refuses_the_other_hosts_sync_and_check(tmp_path, host, other):
    t=target(tmp_path, host); apply(host, t, tmp_path/'st')
    migrated=t.read_bytes(); m=os.stat(t).st_mtime_ns; before=files(tmp_path)
    assert 'ai-agent-policy:core-%s:start'%host in migrated.decode() and 'ai-agent-policy:core-%s'%other not in migrated.decode()
    for extra in ((), ('--plan-sha256', '0'*64), ('--overwrite-unrecognized',)):
        code, r=sync(other, t, '--state-dir', tmp_path/'st2', *extra)
        assert code==2 and r['error']=='host_mismatch'
    code, r=cli('check', '--host', other, '--target', t); assert code==2 and r['error']=='host_mismatch'
    assert t.read_bytes()==migrated and os.stat(t).st_mtime_ns==m and files(tmp_path)==before and not (tmp_path/'st2').exists()
    assert sync(host, t)[0]==0   # the right host still sees it as current

def test_core_markers_are_per_host():
    c=cfg(); assert c['core']['markers']=={'claude':'ai-agent-policy:core-claude', 'codex':'ai-agent-policy:core-codex'}
    assert gb.render('claude')!=gb.render('codex') and 'core-codex' not in gb.render('claude') and 'core-claude' not in gb.render('codex')

def test_wrong_host_legacy_is_not_recognized(tmp_path):
    t=target(tmp_path, 'claude'); c, r=sync('codex', t)
    assert c==1 and r['error']=='no_managed_block'

# ---- outside guard ---------------------------------------------------------------------------------------------------------------------------
def test_outside_bytes_guard_blocks_a_corrupting_rewrite(tmp_path, monkeypatch):
    t=target(tmp_path); before=t.read_bytes()
    real=gb._build
    monkeypatch.setattr(gb, '_build', lambda text, regions, rendered: real(text, regions, rendered)+'tail')
    c, r=sync('claude', t)
    assert c==2 and r['error']=='outside_modified' and t.read_bytes()==before
    monkeypatch.setattr(gb, '_build', lambda text, regions, rendered: real(text, regions, rendered).replace('한글', 'X'))
    c, r=sync('claude', t, '--plan-sha256', '0'*64)
    assert c==2 and r['error']=='outside_modified' and t.read_bytes()==before

# ---- block sets --------------------------------------------------------------------------------------------------------------------------
def test_plan_hash_binds_the_selected_block_set(tmp_path):
    t=target(tmp_path); b=t.read_bytes()
    d=sync('claude', t)[1]; o=sync('claude', t, '--with-orca')[1]
    assert d['plan_sha256']!=o['plan_sha256'] and d['selected_blocks']==['core', 'paseo'] and o['selected_blocks']==['core', 'orca', 'paseo']
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--with-orca', '--plan-sha256', d['plan_sha256'])
    assert code==2 and r['error']=='plan_sha256_mismatch' and t.read_bytes()==b and not (tmp_path/'st').exists()

def test_switching_block_sets_is_refused_and_restore_recovers(tmp_path):
    t=target(tmp_path, name='a.md'); orig=t.read_bytes()
    # with-orca install, then a default sync would drop the orca block: refused
    code, res=apply('claude', t, tmp_path/'st', '--with-orca'); assert code==0 and b'orca-policy' in t.read_bytes()
    withorca=t.read_bytes(); m=os.stat(t).st_mtime_ns
    for extra in ((), ('--plan-sha256', '0'*64), ('--overwrite-unrecognized',)):
        code, r=sync('claude', t, '--state-dir', tmp_path/'st', *extra); assert code==1 and r['error']=='unexpected_block'
    code, r=cli('check', '--host', 'claude', '--target', t); assert code==1 and r['error']=='unexpected_block'
    assert t.read_bytes()==withorca and os.stat(t).st_mtime_ns==m
    # default install, then adding orca would insert a block into a managed install: refused as partial
    t2=target(tmp_path, name='b.md'); apply('claude', t2, tmp_path/'st2'); default=t2.read_bytes()
    code, r=sync('claude', t2, '--with-orca'); assert code==1 and r['error']=='partial_install'
    code, r=cli('check', '--host', 'claude', '--target', t2, '--with-orca'); assert code==1 and r['state']=='partial'
    assert t2.read_bytes()==default
    # the supported way back is restore
    code, plan=restore(t, Path(res['backup']), tmp_path/'st'); code, r=restore(t, Path(res['backup']), tmp_path/'st', '--plan-sha256', plan['plan_sha256'])
    assert code==0 and t.read_bytes()==orig
    code, r=apply('claude', t, tmp_path/'st'); assert code==0 and b'orca-policy' not in t.read_bytes()

def test_default_install_never_writes_the_orca_block(tmp_path):
    for host in HOSTS:
        t=target(tmp_path, host, name=host+'.md'); apply(host, t, tmp_path/('st'+host)); txt=t.read_text(encoding='utf-8')
        assert 'orca-policy' not in txt and 'ai-agent-policy:core-%s:start'%host in txt and 'ai-agent-policy:paseo-policy:start' in txt
        assert cli('check', '--host', host, '--target', t)[0]==0

# ---- known releases, hand edits, downgrades ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('host', HOSTS)
def test_known_sha256_pins_the_current_render_of_every_block(host):
    """Failing here means a source text changed without pinning the release: run `python3 -B -m ai_policy.globalblocks hashes --host <host>`
    and add the hash of the released block to blocks.json known_sha256."""
    c=cfg()
    for name, block in gb.render_blocks(host, c, list(gb.ORDER)):
        assert sha(block.encode('utf-8')) in c[name]['known_sha256'][host], (name, host)

def test_hashes_command_prints_current_block_hashes(capsys):
    assert gb.main(['hashes', '--host', 'codex'])==0
    out=json.loads(capsys.readouterr().out)
    assert out['blocks']=={n: sha(b.encode('utf-8')) for n, b in gb.render_blocks('codex', cfg(), list(gb.ORDER))}

def current_target(tmp_path, mutate, name='t.md'):
    blocks=[t for _, t in gb.render_blocks('claude')]
    t=tmp_path/name; t.write_text(PRE+'\n'.join(mutate(blocks))+POST, encoding='utf-8'); return t

def test_hand_edited_current_block_is_unrecognized(tmp_path):
    t=current_target(tmp_path, lambda b: [b[0].replace('Sonnet is the default', 'Sonnet is NOT the default'), b[1]]); before=t.read_bytes()
    c, r=cli('check', '--host', 'claude', '--target', t); assert c==1 and r['blocks']['core']['status']=='unrecognized' and r['blocks']['paseo']['status']=='current'
    for extra in ((), ('--plan-sha256', '0'*64)):
        code, r=sync('claude', t, '--state-dir', tmp_path/'st', *extra); assert code==1 and r['error']=='unrecognized_block'
    assert t.read_bytes()==before and not (tmp_path/'st').exists()
    code, plan=sync('claude', t, '--state-dir', tmp_path/'st', '--overwrite-unrecognized'); assert code==0 and plan['blocks'][0]['status']=='unrecognized' and plan['blocks'][0]['action']=='update'
    code, res=apply('claude', t, tmp_path/'st', '--overwrite-unrecognized'); assert code==0 and t.read_bytes()==(PRE+gb.render('claude')+POST).encode('utf-8')

def test_older_pinned_release_updates_but_older_unpinned_text_is_unrecognized(tmp_path, monkeypatch):
    old_core=lambda b: b[0].replace('version=1.5.0', 'version=1.4.5').replace('Sonnet is the default', 'Sonnet was the default')
    t=current_target(tmp_path, lambda b: [old_core(b), b[1]])
    code, r=sync('claude', t); assert code==1 and r['error']=='unrecognized_block'   # lower version, text not pinned
    know(monkeypatch, 'core', 'claude', old_core([gb.render_blocks('claude')[0][1]]))
    code, plan=sync('claude', t); assert code==0 and plan['blocks'][0]['status']=='known' and plan['blocks'][0]['action']=='update' and plan['blocks'][1]['action']=='unchanged'
    code, res=apply('claude', t, tmp_path/'st'); assert code==0 and t.read_bytes()==(PRE+gb.render('claude')+POST).encode('utf-8')

@pytest.mark.parametrize('mutation', ('text edit', 'same text'))
def test_newer_block_version_is_a_downgrade(tmp_path, mutation):
    def mut(b):
        newer=b[0].replace('version=1.5.0', 'version=1.6.0')
        return [newer.replace('Sonnet is the default', 'Sonnet is better') if mutation=='text edit' else newer, b[1]]
    t=current_target(tmp_path, mut); before=t.read_bytes()
    c, r=cli('check', '--host', 'claude', '--target', t); assert c==1 and r['blocks']['core']['status']=='newer'
    for extra in ((), ('--plan-sha256', '0'*64)):
        code, r=sync('claude', t, '--state-dir', tmp_path/'st', *extra); assert code==1 and r['error']=='downgrade_block'
    assert t.read_bytes()==before and not (tmp_path/'st').exists()
    code, plan=sync('claude', t, '--overwrite-unrecognized'); assert code==0 and plan['blocks'][0]['status']=='newer'
    code, res=apply('claude', t, tmp_path/'st', '--overwrite-unrecognized'); assert code==0 and t.read_bytes()==(PRE+gb.render('claude')+POST).encode('utf-8')

def test_unknown_version_string_with_unknown_text_is_unrecognized(tmp_path):
    t=current_target(tmp_path, lambda b: [b[0].replace('version=1.5.0', 'version=banana').replace('Sonnet is the default', 'x'), b[1]])
    code, r=sync('claude', t); assert code==1 and r['error']=='unrecognized_block'
    t2=current_target(tmp_path, lambda b: [b[0].replace('version=1.5.0', 'version=banana'), b[1]], 't2.md')   # text differs only in the version
    code, r=sync('claude', t2); assert code==1 and r['error']=='unrecognized_block'

def test_draft_suffix_sorts_before_the_plain_release():
    k=gb._version_key
    assert k('0.1.1-draft')<k('0.1.1')<k('0.2.0')<k('1.0.0') and k('1.4.0')<k('1.5.0') and k('banana') is None and k('1.5')is None

# ---- idempotence and in-place update ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('host', HOSTS)
def test_rerun_when_current_writes_nothing(tmp_path, host):
    t=target(tmp_path, host); apply(host, t, tmp_path/'st')
    os.utime(t, ns=(1_000_000_000, 1_000_000_000)); b=t.read_bytes(); m=os.stat(t).st_mtime_ns
    backups=files(tmp_path/'st'/'backups')
    code, plan=sync(host, t, '--state-dir', tmp_path/'st'); assert code==0 and plan['changes']==0 and [x['action'] for x in plan['blocks']]==['unchanged']*2
    code, res=sync(host, t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256'])
    assert code==0 and res['applied'] is False and res['dry_run'] is False
    assert t.read_bytes()==b and os.stat(t).st_mtime_ns==m and files(tmp_path/'st'/'backups')==backups and files(tmp_path)==sorted(['CLAUDE.md' if host=='claude' else 'AGENTS.md', 'st'])

def know(monkeypatch, name, host, text):
    """Pretend `text` is a pinned earlier release of a block (blocks.json known_sha256)."""
    real=gb.load_config
    def lc(*a):
        c=real(*a); c[name]['known_sha256'][host]=list(c[name]['known_sha256'][host])+[sha(text.encode('utf-8'))]; return c
    monkeypatch.setattr(gb, 'load_config', lc)

def test_current_blocks_update_in_place_keeping_text_between_and_around(tmp_path, monkeypatch):
    blocks=[t for _, t in gb.render_blocks('claude', selected=ALL)]
    core=blocks[0].replace('version=1.5.0', 'version=1.0.0').replace('Sonnet is the default', 'Sonnet was the default')
    orca=blocks[1].replace('version=1.4.0', 'version=0.9.0')
    know(monkeypatch, 'core', 'claude', core); know(monkeypatch, 'orca', 'claude', orca)
    mid=core+'\n사이 텍스트 ✓\n\n'+orca+'\n\n\n'+blocks[2]
    t=target(tmp_path, mid=mid); before=t.read_bytes()
    c, chk=cli('check', '--host', 'claude', '--target', t, '--with-orca')
    assert c==1 and chk['state']=='current' and chk['blocks']['core']['up_to_date'] is False and chk['blocks']['paseo']['up_to_date'] is True and chk['blocks']['core']['version_found']=='1.0.0'
    code, plan=sync('claude', t, '--with-orca'); assert [b['action'] for b in plan['blocks']]==['update', 'update', 'unchanged'] and plan['changes']==2
    code, res=apply('claude', t, tmp_path/'st', '--with-orca'); assert code==0
    assert t.read_bytes()==(PRE+blocks[0]+'\n사이 텍스트 ✓\n\n'+blocks[1]+'\n\n\n'+blocks[2]+POST).encode('utf-8')
    assert (tmp_path/'st'/'backups').exists() and any((tmp_path/'st'/'backups').iterdir())

# ---- refusals --------------------------------------------------------------------------------------------------------------------------------
def rb(i): return gb.render_blocks('claude', selected=ALL)[i][1]
L='<!-- ai-agent-policy:claude:start version=1.4.0 -->\ntext\n<!-- ai-agent-policy:claude:end -->\n'
CASES={
    'duplicate_legacy': (L+'\nmid\n'+L, 'duplicate_markers'),
    'duplicate_core': (rb(0)+rb(0), 'duplicate_markers'),
    'nested_legacy_in_core': ('<!-- ai-agent-policy:core-claude:start version=1 -->\n'+L+'<!-- ai-agent-policy:core-claude:end -->\n', 'nested_markers'),
    'block_containing_other_block_marker': (rb(0).replace('\n<!-- ai-agent-policy:core-claude:end -->', '\n<!-- ai-agent-policy:orca-policy:start version=1 -->\n<!-- ai-agent-policy:core:end -->'), 'nested_markers'),
    'foreign_marker_inside_block': ('<!-- ai-agent-policy:claude:start version=1 -->\n<!-- ai-agent-policy:other:start version=1 -->\n<!-- ai-agent-policy:claude:end -->\n', 'nested_markers'),
    'missing_end': (L.replace('<!-- ai-agent-policy:claude:end -->\n', ''), 'unbalanced_markers'),
    'end_without_start': ('x\n<!-- ai-agent-policy:claude:end -->\n', 'unbalanced_markers'),
    'mismatched_end': (L.replace('claude:end', 'core-claude:end'), 'unbalanced_markers'),
    'out_of_order': (rb(2)+'\n'+rb(0), 'out_of_order_markers'),
    'malformed_trailing_space': (L.replace('1.4.0 -->', '1.4.0 --> '), 'malformed_marker'),
    'malformed_inline': ('see <!-- ai-agent-policy:claude:start version=1.4.0 --> here\n', 'malformed_marker'),
    'malformed_end_with_version': (L.replace('claude:end', 'claude:end version=1'), 'malformed_marker'),
    'partial_legacy_plus_core': (L+'\n'+rb(0), 'partial_install'),
    'partial_core_only': (rb(0), 'partial_install'),
    'partial_two_new_with_orca': (rb(0)+'\n'+rb(1), 'partial_install', ('--with-orca',)),
    'orca_block_not_selected': (rb(0)+'\n'+rb(1)+'\n'+rb(2), 'unexpected_block'),
    'out_of_order_with_orca': (rb(0)+'\n'+rb(2)+'\n'+rb(1), 'out_of_order_markers', ('--with-orca',)),
    'partial_legacy_plus_three': (L+'\n'+gb.render('claude'), 'partial_install'),
    'no_managed_block': ('# nothing managed here\n', 'no_managed_block'),
}

@pytest.mark.parametrize('case', sorted(CASES))
def test_structural_refusals_write_nothing(tmp_path, case):
    mid, err, *rest=CASES[case]; extra=rest[0] if rest else ()
    t=target(tmp_path, mid=mid); before=t.read_bytes(); m=os.stat(t).st_mtime_ns
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', *extra)
    assert r['error']==err and code==(1 if err in gb.HUMAN_REFUSALS else 2)
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', '1'*64, *extra)
    assert r['error']==err and code in (1, 2)
    assert t.read_bytes()==before and os.stat(t).st_mtime_ns==m and files(tmp_path)==['CLAUDE.md'] and not (tmp_path/'st').exists()

def test_crlf_target_refused(tmp_path):
    t=tmp_path/'c.md'; t.write_bytes((PRE+legacy('claude')+POST).replace('\n', '\r\n').encode('utf-8'))
    before=t.read_bytes(); code, r=sync('claude', t)
    assert code==2 and r['error']=='target_has_cr' and t.read_bytes()==before

def test_non_utf8_target_refused(tmp_path):
    t=tmp_path/'n.md'; t.write_bytes(PRE.encode('utf-8')+b'\xff\xfe\n'+legacy('claude').encode('utf-8'))
    before=t.read_bytes(); code, r=sync('claude', t)
    assert code==2 and r['error']=='target_not_utf8' and t.read_bytes()==before

def test_symlink_target_refused(tmp_path):
    real=target(tmp_path, name='real.md'); link=tmp_path/'link.md'; link.symlink_to(real); before=real.read_bytes()
    for args in ((), ('--plan-sha256', '2'*64)):
        code, r=sync('claude', link, '--state-dir', tmp_path/'st', *args)
        assert code==2 and r['error']=='target_symlink'
    assert cli('check', '--host', 'claude', '--target', link)[1]['error']=='target_symlink'
    assert real.read_bytes()==before and not link.is_dir() and link.is_symlink() and not (tmp_path/'st').exists()

def test_non_regular_target_refused(tmp_path):
    d=tmp_path/'dir.md'; d.mkdir(); assert sync('claude', d)[1]['error']=='target_not_regular'
    f=tmp_path/'fifo.md'; os.mkfifo(f); assert sync('claude', f)[1]['error']=='target_not_regular'

def test_oversized_target_refused(tmp_path):
    t=tmp_path/'big.md'
    with open(t, 'wb') as f: f.truncate(gb.MAX_BYTES+1)
    code, r=sync('claude', t); assert code==2 and r['error']=='target_too_large'
    t2=tmp_path/'ok.md'
    with open(t2, 'wb') as f: f.truncate(gb.MAX_BYTES)
    assert sync('claude', t2)[1]['error']=='no_managed_block'   # exactly at the limit the file is read and judged on content, not size

# ---- unrecognized legacy ---------------------------------------------------------------------------------------------------------------------
def test_unrecognized_legacy_needs_explicit_overwrite(tmp_path):
    edited=legacy('claude').replace('Sonnet is the default', 'Sonnet is NOT the default', 1)
    t=target(tmp_path, mid=edited); before=t.read_bytes()
    code, r=sync('claude', t, '--state-dir', tmp_path/'st'); assert code==1 and r['error']=='unrecognized_block'
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', '3'*64); assert code==1 and r['error']=='unrecognized_block'
    assert t.read_bytes()==before and not (tmp_path/'st').exists()
    code, plan=sync('claude', t, '--state-dir', tmp_path/'st', '--overwrite-unrecognized')
    assert code==0 and plan['legacy']['known'] is False and plan['overwrite_unrecognized'] is True
    # the flag is bound into the plan hash
    code, plain=sync('claude', target(tmp_path, name='o.md'), '--state-dir', tmp_path/'st')
    assert plain['plan_sha256']!=plan['plan_sha256']
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256']); assert code==1 and r['error']=='unrecognized_block'   # no flag: refused
    known=target(tmp_path, name='k.md')   # on a known legacy block the flag still changes the plan hash (flags are bound)
    assert sync('claude', known, '--overwrite-unrecognized')[1]['plan_sha256']!=sync('claude', known)[1]['plan_sha256']
    code, res=sync('claude', t, '--state-dir', tmp_path/'st', '--overwrite-unrecognized', '--plan-sha256', plan['plan_sha256'])
    assert code==0 and res['applied'] is True and t.read_bytes()==(PRE+gb.render('claude')+POST).encode('utf-8')
    backup=Path(res['backup']); assert backup.read_bytes()==before

# ---- dry run, plan hash --------------------------------------------------------------------------------------------------------------------
def test_dry_run_writes_nothing_and_creates_no_state_dir(tmp_path, monkeypatch):
    xdg=tmp_path/'xdg'; monkeypatch.setenv('XDG_STATE_HOME', str(xdg))
    t=target(tmp_path); before=t.read_bytes(); m=os.stat(t).st_mtime_ns
    for host_args in ((), ('--state-dir', tmp_path/'explicit')):
        code, plan=sync('claude', t, *host_args); assert code==0 and plan['dry_run'] is True
    assert t.read_bytes()==before and os.stat(t).st_mtime_ns==m and not xdg.exists() and not (tmp_path/'explicit').exists() and files(tmp_path)==['CLAUDE.md']

def test_wrong_or_stale_plan_hash_refused(tmp_path):
    t=target(tmp_path); before=t.read_bytes()
    code, plan=sync('claude', t)
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', '0'*64); assert code==2 and r['error']=='plan_sha256_mismatch'
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', 'xyz'); assert code==2 and r['error']=='plan_sha256_invalid'
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256'].upper()); assert code==2 and r['error']=='plan_sha256_invalid'
    assert t.read_bytes()==before and not (tmp_path/'st').exists()
    t.write_bytes(before+b'extra\n')   # edited after the dry run: the plan no longer matches
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256']); assert code==2 and r['error']=='plan_sha256_mismatch'
    assert t.read_bytes()==before+b'extra\n' and not (tmp_path/'st').exists()
    # a plan for one host does not apply to the other host's file, nor to another path
    t2=target(tmp_path, name='other.md'); assert sync('claude', t2, '--plan-sha256', plan['plan_sha256'])[1]['error']=='plan_sha256_mismatch'

def test_target_changed_between_plan_and_replace_aborts(tmp_path, monkeypatch):
    t=target(tmp_path); code, plan=sync('claude', t)
    changed=t.read_bytes()+b'\n# concurrent edit\n'
    monkeypatch.setattr(gb, '_before_replace', lambda path: Path(path).write_bytes(changed))
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256'])
    assert code==2 and r['error']=='target_changed'
    assert t.read_bytes()==changed and files(tmp_path)==['CLAUDE.md', 'st']   # no temp file left, no write

# ---- backups and state dir ---------------------------------------------------------------------------------------------------------------------
def test_backup_is_private_complete_and_named_by_convention(tmp_path):
    t=target(tmp_path); t.chmod(0o640); before=t.read_bytes()
    code, res=apply('claude', t, tmp_path/'st')
    b=Path(res['backup']); assert b.parent==(tmp_path/'st'/'backups').resolve() or b.parent==tmp_path/'st'/'backups'
    assert stat.S_IMODE(os.stat(b).st_mode)==0o600 and stat.S_IMODE(os.stat(b.parent).st_mode)==0o700 and stat.S_IMODE(os.stat(tmp_path/'st').st_mode)==0o700
    assert b.read_bytes()==before and re.fullmatch(r'CLAUDE\.md\.\d{8}T\d{6}Z\.%s'%sha(before)[:8], b.name)
    assert stat.S_IMODE(os.stat(t).st_mode)==0o640   # original mode preserved
    assert str(before[:20]) not in json.dumps(res)

def test_default_state_dir_is_keyed_by_target_abspath(tmp_path, monkeypatch):
    xdg=tmp_path/'xdg'; monkeypatch.setenv('XDG_STATE_HOME', str(xdg))
    t=target(tmp_path); code, res=apply('claude', t, tmp_path/'unused')
    t2=target(tmp_path, name='B.md')
    code, plan=sync('claude', t2); assert code==0
    code, res=sync('claude', t2, '--plan-sha256', plan['plan_sha256'])
    key=sha(os.path.abspath(t2).encode())[:8]
    assert Path(res['backup']).parent==xdg/'ai-policy'/'global-blocks'/key/'backups'
    assert gb.default_state_dir(t2)==xdg/'ai-policy'/'global-blocks'/key
    assert gb.default_state_dir(t)!=gb.default_state_dir(t2)

def test_relative_xdg_state_home_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path/'home')); monkeypatch.setenv('XDG_STATE_HOME', 'relative/state')
    assert gb.default_state_dir(tmp_path/'f.md')==Path(str(tmp_path/'home'))/'.local'/'state'/'ai-policy'/'global-blocks'/sha(os.path.abspath(tmp_path/'f.md').encode())[:8]

def test_unsafe_state_dirs_are_refused_before_any_write(tmp_path):
    t=target(tmp_path); before=t.read_bytes(); code, plan=sync('claude', t)
    real=tmp_path/'real'; real.mkdir(mode=0o700); link=tmp_path/'link'; link.symlink_to(real)
    code, r=sync('claude', t, '--state-dir', link, '--plan-sha256', plan['plan_sha256']); assert code==2 and r['error']=='state_dir_unsafe'
    loose=tmp_path/'loose'; loose.mkdir(); loose.chmod(0o755)
    code, r=sync('claude', t, '--state-dir', loose, '--plan-sha256', plan['plan_sha256']); assert code==2 and r['error']=='state_dir_unsafe'
    assert t.read_bytes()==before and files(tmp_path)==['CLAUDE.md', 'link', 'loose', 'real'] and files(real)==[] and files(loose)==[]

# ---- post-replace verification -----------------------------------------------------------------------------------------------------------------
def test_post_replace_verification_failure_is_reported_with_backup(tmp_path, monkeypatch):
    t=target(tmp_path); before=t.read_bytes(); real=gb._write_atomic
    monkeypatch.setattr(gb, '_write_atomic', lambda path, data, sha_, mode: real(path, data+b'corrupt', sha_, mode))
    code, r=apply('claude', t, tmp_path/'st')
    assert code==2 and r['applied'] is True and r['error']=='post_write_verification_failed' and Path(r['backup']).read_bytes()==before

def test_post_replace_outside_mismatch_is_detected(tmp_path, monkeypatch):
    t=target(tmp_path); before=t.read_bytes(); real=gb._write_atomic
    monkeypatch.setattr(gb, '_write_atomic', lambda path, data, sha_, mode: real(path, data.replace('사용자'.encode(), b'USER'), sha_, mode))
    code, r=apply('claude', t, tmp_path/'st')
    assert code==2 and r['applied'] is True and r['error']=='post_write_verification_failed' and Path(r['backup']).read_bytes()==before

def test_failure_before_replace_is_a_plain_error(tmp_path, monkeypatch):
    t=target(tmp_path); before=t.read_bytes()
    def boom(path): raise OSError('disk')
    monkeypatch.setattr(gb, '_before_replace', boom)
    code, plan=sync('claude', t)
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', plan['plan_sha256'])
    assert code==2 and r=={'schema':1, 'error':'filesystem_error'}
    assert t.read_bytes()==before and files(tmp_path)==['CLAUDE.md', 'st']

# ---- restore ---------------------------------------------------------------------------------------------------------------------------------
def synced(tmp_path, host='claude'):
    t=target(tmp_path, host); t.chmod(0o640); orig=t.read_bytes(); code, res=apply(host, t, tmp_path/'st')
    return t, orig, Path(res['backup']), tmp_path/'st'

def restore(t, backup, sd, *extra): return cli('restore', '--target', t, '--backup', backup, '--state-dir', sd, *extra)

@pytest.mark.parametrize('host', HOSTS)
def test_restore_is_byte_identical_and_saves_current_first(tmp_path, host):
    t, orig, backup, sd=synced(tmp_path, host); new=t.read_bytes(); assert new!=orig
    code, plan=restore(t, backup, sd); assert code==0 and plan['dry_run'] is True and plan['changes']==1 and t.read_bytes()==new
    code, r=restore(t, backup, sd, '--plan-sha256', plan['plan_sha256'])
    assert code==0 and r['applied'] is True and r['note']==gb.NOTE and t.read_bytes()==orig
    assert Path(r['pre_restore_backup']).read_bytes()==new and stat.S_IMODE(os.stat(t).st_mode)==0o640
    assert not [f for f in files(tmp_path) if f.endswith('.tmp')]
    # restoring again is a no-op
    code, plan=restore(t, backup, sd); code, r=restore(t, backup, sd, '--plan-sha256', plan['plan_sha256']); assert r['applied'] is False and t.read_bytes()==orig

def test_restore_bad_plan_hash_and_changed_file(tmp_path, monkeypatch):
    t, orig, backup, sd=synced(tmp_path); new=t.read_bytes()
    code, r=restore(t, backup, sd, '--plan-sha256', '0'*64); assert code==2 and r['error']=='plan_sha256_mismatch' and t.read_bytes()==new
    code, plan=restore(t, backup, sd)
    changed=new+b'\nlater edit\n'
    monkeypatch.setattr(gb, '_before_replace', lambda path: Path(path).write_bytes(changed))
    code, r=restore(t, backup, sd, '--plan-sha256', plan['plan_sha256'])
    assert code==2 and r['error']=='target_changed' and t.read_bytes()==changed and not [f for f in files(tmp_path) if f.endswith('.tmp')]

def test_restore_refuses_paths_outside_backups_and_bad_names(tmp_path):
    t, orig, backup, sd=synced(tmp_path); new=t.read_bytes()
    outside=tmp_path/backup.name; outside.write_bytes(backup.read_bytes())
    assert restore(t, outside, sd)[1]['error']=='backup_outside_backups_dir'
    assert restore(t, backup.parent/'..'/backup.name, sd)[1]['error']=='backup_outside_backups_dir'
    other=tmp_path/'o'; other.mkdir(mode=0o700); (other/'backups').mkdir(mode=0o700); (other/'backups'/backup.name).write_bytes(backup.read_bytes())
    assert restore(t, other/'backups'/backup.name, sd)[1]['error']=='backup_outside_backups_dir'
    bad=backup.parent/'notes.txt'; bad.write_bytes(orig); assert restore(t, bad, sd)[1]['error']=='backup_name_invalid'
    wrongbase=backup.parent/('AGENTS.md'+backup.name[len('CLAUDE.md'):]); wrongbase.write_bytes(orig); assert restore(t, wrongbase, sd)[1]['error']=='backup_name_invalid'
    corrupt=backup.parent/('CLAUDE.md.20200101T000000Z.deadbeef'); corrupt.write_bytes(orig); assert restore(t, corrupt, sd)[1]['error']=='backup_corrupt'
    assert restore(t, backup.parent/'CLAUDE.md.20200101T000000Z.00000000', sd)[1]['error']=='backup_unavailable'
    assert t.read_bytes()==new

def test_restore_refuses_symlink_and_non_regular_backups(tmp_path):
    t, orig, backup, sd=synced(tmp_path); new=t.read_bytes()
    link=backup.parent/('CLAUDE.md.20210101T000000Z.%s'%sha(orig)[:8]); link.symlink_to(backup)
    assert restore(t, link, sd)[1]['error']=='backup_symlink'
    fifo=backup.parent/'CLAUDE.md.20210101T000001Z.abcdef01'; os.mkfifo(fifo)
    assert restore(t, fifo, sd)[1]['error']=='backup_not_regular'
    d=backup.parent/'CLAUDE.md.20210101T000002Z.abcdef02'; d.mkdir()
    assert restore(t, d, sd)[1]['error']=='backup_not_regular'
    assert t.read_bytes()==new

def test_restore_refuses_unsafe_state_dir_and_symlink_target(tmp_path):
    t, orig, backup, sd=synced(tmp_path)
    sd.chmod(0o755); assert restore(t, backup, sd)[1]['error']=='state_dir_unsafe'; sd.chmod(0o700)
    link=tmp_path/'tl.md'; link.symlink_to(t); assert restore(link, backup, sd)[1]['error'] in ('target_symlink', 'backup_name_invalid')
    assert restore(tmp_path/'nope.md', backup, sd)[1]['error'] in ('target_unavailable', 'backup_name_invalid')

def test_restore_works_for_a_broken_target_and_default_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path/'xdg'))
    t=target(tmp_path); orig=t.read_bytes()
    code, plan=sync('claude', t); code, res=sync('claude', t, '--plan-sha256', plan['plan_sha256'])
    t.write_bytes(b'\xff broken')   # restore only needs the bytes of the file being replaced
    code, plan=cli('restore', '--target', t, '--backup', res['backup']); assert code==0 and plan['dry_run'] is True
    code, r=cli('restore', '--target', t, '--backup', res['backup'], '--plan-sha256', plan['plan_sha256']); assert code==0 and t.read_bytes()==orig

def test_apply_then_restore_roundtrip_for_both_hosts(tmp_path):
    for host in HOSTS:
        d=tmp_path/host; d.mkdir(); t, orig, backup, sd=synced(d, host)
        code, plan=restore(t, backup, sd); restore(t, backup, sd, '--plan-sha256', plan['plan_sha256']); assert t.read_bytes()==orig

# ---- hardening: hard links, backup ownership sidecar, end of file ---------------------------------------------------------------------------
def test_hard_linked_target_is_refused_for_writes_but_checkable(tmp_path):
    t=target(tmp_path); twin=tmp_path/'twin.md'; os.link(t, twin); before=t.read_bytes()
    assert sync('claude', t, '--state-dir', tmp_path/'st')[1]['error']=='target_hardlinked'
    code, r=sync('claude', t, '--state-dir', tmp_path/'st', '--plan-sha256', '4'*64); assert code==2 and r['error']=='target_hardlinked'
    assert cli('check', '--host', 'claude', '--target', t)[1]['state']=='legacy'   # read-only check is fine
    assert t.read_bytes()==before and twin.read_bytes()==before and not (tmp_path/'st').exists()
    twin.unlink(); assert sync('claude', t)[0]==0   # back to a single link

def test_hard_linked_restore_target_is_refused(tmp_path):
    t, orig, backup, sd=synced(tmp_path); os.link(t, tmp_path/'twin.md'); new=t.read_bytes()
    assert restore(t, backup, sd)[1]['error']=='target_hardlinked' and t.read_bytes()==new

def test_backup_gets_a_private_sidecar_with_the_target_path(tmp_path):
    t, orig, backup, sd=synced(tmp_path); side=Path(str(backup)+'.target')
    assert side.read_bytes()==os.path.abspath(t).encode() and stat.S_IMODE(os.stat(side).st_mode)==0o600
    assert gb.BACKUP_NAME.fullmatch(side.name) is None   # never mistaken for a backup itself

def test_restore_requires_a_matching_sidecar(tmp_path):
    t, orig, backup, sd=synced(tmp_path); new=t.read_bytes(); side=Path(str(backup)+'.target')
    side.write_bytes(b'/somewhere/else.md'); assert restore(t, backup, sd)[1]['error']=='backup_target_mismatch'
    side.unlink(); assert restore(t, backup, sd)[1]['error']=='backup_target_missing'
    side.symlink_to(t); assert restore(t, backup, sd)[1]['error']=='backup_target_missing'; side.unlink()
    assert t.read_bytes()==new
    side.write_bytes(os.path.abspath(t).encode()); code, plan=restore(t, backup, sd); assert code==0 and plan['changes']==1

def test_shared_state_dir_with_same_basename_cannot_restore_the_wrong_target(tmp_path):
    d1=tmp_path/'one'; d2=tmp_path/'two'; d1.mkdir(); d2.mkdir(); sd=tmp_path/'shared'
    t1=target(d1, 'claude', pre='# one\n'); t2=target(d2, 'claude', pre='# two — 다른 파일\n'); o1=t1.read_bytes(); o2=t2.read_bytes()
    r1=apply('claude', t1, sd)[1]; r2=apply('claude', t2, sd)[1]
    n2=t2.read_bytes()
    code, r=restore(t2, Path(r1['backup']), sd); assert code==2 and r['error']=='backup_target_mismatch' and t2.read_bytes()==n2
    for t, res, o in ((t1, r1, o1), (t2, r2, o2)):
        code, plan=restore(t, Path(res['backup']), sd); code, r=restore(t, Path(res['backup']), sd, '--plan-sha256', plan['plan_sha256']); assert code==0 and t.read_bytes()==o

def test_identical_targets_in_one_state_dir_do_not_share_a_backup(tmp_path, monkeypatch):
    import datetime as dt
    class Fixed(dt.datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 11, 26, 12, 0, 0, tzinfo=tz)
    monkeypatch.setattr(gb, 'datetime', Fixed)
    d1=tmp_path/'one'; d2=tmp_path/'two'; d1.mkdir(); d2.mkdir(); sd=tmp_path/'shared'
    t1=target(d1); t2=target(d2); b2=t2.read_bytes()
    assert apply('claude', t1, sd)[0]==0
    code, plan=sync('claude', t2, '--state-dir', sd); code, r=sync('claude', t2, '--state-dir', sd, '--plan-sha256', plan['plan_sha256'])
    assert code==2 and r['error']=='backup_exists' and t2.read_bytes()==b2

@pytest.mark.parametrize('host', HOSTS)
def test_legacy_end_marker_as_last_line_without_newline(tmp_path, host):
    t=tmp_path/'e.md'; t.write_text(PRE+legacy(host).rstrip('\n'), encoding='utf-8'); assert not t.read_bytes().endswith(b'\n')
    code, plan=sync(host, t); assert code==0 and plan['state']=='legacy' and plan['legacy']['known'] is True
    code, res=apply(host, t, tmp_path/'st'); assert code==0
    assert t.read_bytes()==(PRE+R(host)).encode('utf-8') and cli('check', '--host', host, '--target', t)[0]==0
    assert Path(res['backup']).read_bytes()==(PRE+legacy(host).rstrip('\n')).encode('utf-8')

def test_current_blocks_at_end_of_file_without_newline_get_it_added(tmp_path):
    t=tmp_path/'e.md'; t.write_text(PRE+R('claude').rstrip('\n'), encoding='utf-8')
    code, plan=sync('claude', t); assert code==0 and [b['status'] for b in plan['blocks']]==['current', 'current'] and [b['action'] for b in plan['blocks']]==['unchanged', 'update']
    assert cli('check', '--host', 'claude', '--target', t)[0]==1
    apply('claude', t, tmp_path/'st'); assert t.read_bytes()==(PRE+R('claude')).encode('utf-8')

def test_documented_block_sizes_match_the_render():
    doc=(REPO/'docs'/'global-blocks.md').read_text(encoding='utf-8')
    for host in HOSTS:
        bl={n: len(t.encode('utf-8')) for n, t in gb.render_blocks(host, cfg(), list(gb.ORDER))}
        leg=len(legacy(host).encode('utf-8')); default=len(gb.render(host).encode('utf-8')); full=len(R(host, True).encode('utf-8'))
        row=next(l for l in doc.splitlines() if l.startswith('| %s |'%host))
        assert [c.strip() for c in row.strip('|').split('|')]==[host, str(bl['core']), str(bl['paseo']), str(bl['orca']), str(leg), str(default), '%+d'%(default-leg), str(full), '%+d'%(full-leg)]
