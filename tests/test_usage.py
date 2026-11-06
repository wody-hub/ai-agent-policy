import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from ai_policy import routing, usage
from ai_policy.bundle import PolicyError

SECRET='TOPSECRET-CONTENT'

def ev(mid, model, i, o, cr=0, cw=0, sid='s1', ts='2026-11-02T10:00:00Z', typ='assistant'):
    return json.dumps({'type':typ,'sessionId':sid,'timestamp':ts,'requestId':'r'+mid,
        'message':{'id':mid,'model':model,'content':[{'type':'text','text':SECRET}],
                   'usage':{'input_tokens':i,'output_tokens':o,'cache_read_input_tokens':cr,'cache_creation_input_tokens':cw}}})

class Base(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.tmp=Path(t.name)
    def cli(self, *a):
        b=io.StringIO()
        with contextlib.redirect_stdout(b): code=usage.main(list(a))
        return code, b.getvalue()

class CollectTests(Base):
    def test_claude(self):
        d=self.tmp/'proj'/'sub'; d.mkdir(parents=True)
        (d/'a.jsonl').write_text('\n'.join([
            ev('m1','claude-sonnet-5-5',10,5,100,20), ev('m1','claude-sonnet-5-5',10,5,100,20),
            ev('m2','claude-sonnet-5-5',1,2,sid='s2'), ev('m3','<synthetic>',9,9),
            '{"usage": broken', ev('m4','claude-sonnet-5-5',5,5,typ='user'), ev('m5','claude-opus-5-5',7,3,ts='2026-10-01T00:00:00Z'), 'no usage here'])+'\n')
        r=usage.collect_claude(self.tmp)
        self.assertEqual(r['models']['claude-sonnet-5-5'], {'input':11,'output':7,'cache_read':100,'cache_write':20,'messages':2,'sessions':2})
        self.assertNotIn('<synthetic>', r['models']); self.assertEqual(r['skipped_lines'], 1)
        self.assertNotIn(SECRET, json.dumps(r))
        r=usage.collect_claude(self.tmp, '2026-11-01'); self.assertNotIn('claude-opus-5-5', r['models'])
        self.assertIn('claude-opus-5-5', usage.collect_claude(self.tmp)['models'])
        self.assertEqual(usage.collect_claude(self.tmp/'missing')['models'], {})

    def test_codex(self):
        d=self.tmp/'2026'/'11'; d.mkdir(parents=True)
        tc=lambda m: json.dumps({'timestamp':'2026-11-03T00:00:00Z','type':'turn_context','payload':{'model':m,'effort':'high','user_instructions':SECRET}})
        tk=lambda i,c,o,rr: json.dumps({'timestamp':'2026-11-03T00:00:01Z','type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':i,'cached_input_tokens':c,'output_tokens':o,'reasoning_output_tokens':rr}}}})
        nul=json.dumps({'type':'event_msg','payload':{'type':'token_count','info':None}})
        (d/'rollout-1.jsonl').write_text('\n'.join([tc('gpt-6-luna'), tk(10,1,2,1), tk(100,40,20,5), nul, 'garbage "token_count"'])+'\n')
        (d/'rollout-2.jsonl').write_text('\n'.join([tc('gpt-6-luna'), tk(1,0,1,0)])+'\n')
        (d/'other.jsonl').write_text(tc('x')+'\n'+tk(1,1,1,1)+'\n')
        r=usage.collect_codex(self.tmp)
        self.assertEqual(r['models'], {'gpt-6-luna':{'input':101,'cached_input':40,'output':21,'reasoning_output':5,'sessions':2}})
        self.assertEqual(r['skipped_lines'], 1); self.assertNotIn(SECRET, json.dumps(r))
        self.assertEqual(usage.collect_codex(self.tmp, '2026-12-01')['models'], {})
        # a mid-session model switch splits the cumulative totals by increment
        (d/'rollout-3.jsonl').write_text('\n'.join([tc('gpt-6-luna'), tk(100,0,10,0), tc('gpt-6.1-sol'), tk(120,0,15,0)])+'\n')
        r=usage.collect_codex(self.tmp)['models']
        self.assertEqual((r['gpt-6-luna']['input'], r['gpt-6.1-sol']['input'], r['gpt-6.1-sol']['output']), (201, 20, 5))

class RecordTests(Base):
    def test_modes_and_fields(self):
        p=self.tmp/'a'/'b'/'o.jsonl'
        row=usage.record(p, task_id='T1', model='m', task_type='docs', success=True, retries=1)
        usage.record(p, task_id='T2', model='m', task_type='docs', success=False)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        for d in (p.parent, p.parent.parent): self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
        rows=usage.load_outcomes(p); self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]['cost_usd']); self.assertTrue(row['ts'].endswith('Z'))

    def test_validation(self):
        p=self.tmp/'o.jsonl'
        for kw in ({'model':'m','task_type':'t','success':True}, {'task_id':'x','task_type':'t','success':True},
                   {'task_id':'x','model':'m','success':True}, {'task_id':'x','model':'m','task_type':'t'},
                   {'task_id':'x','model':'m','task_type':'t','success':'yes'}, {'task_id':'x','model':'m','task_type':'t','success':True,'retries':-1},
                   {'task_id':'x','model':'m','task_type':'t','success':True,'content':'no'}):
            with self.assertRaises(PolicyError): usage.record(p, **kw)
        self.assertFalse(p.exists())

class ReportTests(Base):
    C=routing.load_config()
    def outs(self, model, n, ok, **k):
        return [dict(task_id=str(i), model=model, task_type='docs', success=i<ok, **k) for i in range(n)]
    def test_no_pricing_token_recommendation(self):
        o=self.outs('luna', 5, 5, input_tokens=100, output_tokens=50)+self.outs('sonnet', 5, 5, input_tokens=300, output_tokens=50)+self.outs('opus', 2, 2, input_tokens=1, output_tokens=1)
        cl={'models':{'claude-sonnet-5-5':{'input':1,'output':1,'cache_read':0,'cache_write':0,'messages':1,'sessions':1}},'skipped_lines':0,'files':1}
        x=usage.report(self.C, cl, None, o)
        self.assertEqual(x['models']['claude-sonnet-5-5']['estimated_cost_usd'], 'not_collected')
        self.assertEqual(x['recommendations']['docs'], {'model':'luna','metric':'tokens_per_successful_task','value':150.0,'n':5})
        self.assertIn('pricing', x['not_collected']); self.assertIn('codex_logs', x['not_collected']); self.assertEqual(x['collected']['codex'], 'not_collected')
        self.assertEqual(x['outcomes_by_type']['docs']['luna']['avg_tokens'], 150.0)
        self.assertEqual(x['outcomes_by_type']['docs']['luna']['avg_retries'], 'not_collected')

    def test_premium_never_recommended(self):
        o=self.outs('gpt-6-astra', 5, 5, input_tokens=1)+self.outs('opus', 5, 5, input_tokens=1)+self.outs('luna', 5, 5, input_tokens=100)
        self.assertEqual(usage.report(self.C, outcomes=o)['recommendations']['docs']['model'], 'luna')
        self.assertEqual(usage.report(self.C, outcomes=self.outs('gpt-6-astra', 5, 5, input_tokens=1))['recommendations']['docs'], 'insufficient_data')

    def test_insufficient(self):
        x=usage.report(self.C, outcomes=self.outs('luna', 4, 4, input_tokens=1))
        self.assertEqual(x['recommendations']['docs'], 'insufficient_data')
        x=usage.report(self.C, outcomes=self.outs('luna', 5, 0, input_tokens=1)); self.assertEqual(x['recommendations']['docs'], 'insufficient_data')

    def test_cost_with_pricing(self):
        c=json.loads(json.dumps(self.C)); c['pricing_usd_per_million_tokens']['models']={'m':{'input':1,'output':2,'cache_read':0.5,'cache_write':3}}
        x=usage.report(c, {'models':{'m':{'input':1000000,'output':1000000,'cache_read':1000000,'cache_write':1000000,'messages':1,'sessions':1}},'skipped_lines':0,'files':1})
        self.assertEqual(x['models']['m']['estimated_cost_usd'], 6.5)
        o=self.outs('a', 5, 5, cost_usd=2.0)+self.outs('b', 5, 5, cost_usd=1.0)
        self.assertEqual(usage.report(c, outcomes=o)['recommendations']['docs']['metric'], 'cost_per_successful_task')

    def test_cli(self):
        p=self.tmp/'o.jsonl'
        code, out=self.cli('record','--task-id','T','--model','luna','--task-type','docs','--success','true','--verified','true','--retries','1','--input-tokens','10','--outcomes',str(p))
        self.assertEqual((code, json.loads(out)), (0, {'schema':1,'recorded':True}))
        code, out=self.cli('record','--task-id','T','--model','luna','--task-type','docs','--success','true','--duration-s','-1','--outcomes',str(p))
        self.assertEqual((code, json.loads(out)['error']), (30, 'outcome_invalid_duration_s'))
        code, out=self.cli('report','--no-logs','--outcomes',str(p),'--since','2000-01-01')
        x=json.loads(out); self.assertEqual(code, 0)
        self.assertEqual((x['collected']['outcomes'], x['collected']['claude']), (1, 'not_collected'))
        self.assertEqual(x['outcomes_by_type']['docs']['luna']['verified_rate'], 1.0)
        code, out=self.cli('report','--claude-dir',str(self.tmp/'none'),'--codex-dir',str(self.tmp/'none'),'--outcomes',str(self.tmp/'none.jsonl'))
        self.assertEqual(json.loads(out)['collected']['codex'], 'not_collected')

if __name__=='__main__': unittest.main()
