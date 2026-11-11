from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import csv
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from evaluation.common import ROOT,EVAL,archive
sys.path[:0]=[str(ROOT/'prototype'),str(EVAL/'adapters')]
from psb_llm import ProviderError
from net_client import Budget,Client

def database(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE budget(id INTEGER PRIMARY KEY,requests INTEGER,tokens_reserved INTEGER,cost_reserved REAL)')
        db.execute('INSERT INTO budget VALUES(1,0,0,0)')

class AdapterTests(unittest.TestCase):
    def test_concurrent_request_budget_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'budget.sqlite');database(path)
            b=Budget(path,dict(max_requests=7,max_token_bound=100000))
            def reserve(_):
                try:b.reserve(100,100);return True
                except ProviderError:return False
            with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(30)))
            self.assertEqual(sum(results),7)
    def test_token_and_cost_limits(self):
        for config in [dict(max_requests=20,max_token_bound=199),dict(max_requests=20,max_token_bound=99999,max_cost=.0001,input_price_per_million=1,output_price_per_million=2)]:
            with tempfile.TemporaryDirectory() as tmp:
                p=str(Path(tmp)/'b.sqlite');database(p)
                with self.assertRaises(ProviderError):Budget(p,config).reserve(100,100)
    def test_deepseek_probe_retry_usage_and_no_gold(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"test-model"}]}')
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(body)
                if len(calls)==1:
                    self.send_response(429);self.send_header('Retry-After','0');self.end_headers();return
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps(dict(choices=[dict(finish_reason='stop',message=dict(content='{"ok":true}'))],usage=dict(prompt_tokens=12,completion_tokens=4,total_tokens=16))).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,dict(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',DEEPSEEK_API_KEY='SYNTHETIC_LOCAL_TOKEN',DEEPSEEK_MODEL='test-model')):
                p=str(Path(tmp)/'b.sqlite');database(p)
                c=Client(time.monotonic()+10,dict(budget_db=p,max_requests=9,max_token_bound=100000,timeout=2))
                self.assertTrue(c.probe()['listed']);self.assertEqual(c.attempts,3);self.assertEqual(c.usage[0]['total_tokens'],16)
                self.assertEqual(c.errors,['http_429'])
                self.assertNotIn('SYNTHETIC_LOCAL_TOKEN',json.dumps(calls))
                self.assertNotIn('gold',json.dumps(calls))
        finally:server.shutdown();server.server_close();thread.join(2)
    def test_runtime_generation_defaults_and_settled_budget(self):
        # Smoke d0a0658: the workbench forced MAX_TOKENS=2048 (runtime default
        # 8192) and kept byte-based token reservations as if they were spent.
        bodies=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps(dict(choices=[dict(finish_reason='stop',message=dict(content='{"ok":true}'))],usage=dict(prompt_tokens=30,completion_tokens=7,total_tokens=37))).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            env=dict(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',DEEPSEEK_API_KEY='SYNTHETIC_LOCAL_TOKEN',DEEPSEEK_MODEL='test-model',MAX_TOKENS='2048',TEMPERATURE='1.3')
            with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,env):
                p=str(Path(tmp)/'b.sqlite');database(p)
                c=Client(time.monotonic()+10,dict(budget_db=p,max_requests=9,max_token_bound=10**7,timeout=None,max_tokens=None,temperature=None))
                self.assertEqual(c.complete('Return JSON.',{'x':1}),{'ok':True})
                self.assertEqual(bodies[-1]['max_tokens'],8192);self.assertEqual(bodies[-1]['temperature'],0)
                with closing(sqlite3.connect(p)) as db:
                    self.assertEqual(db.execute('SELECT requests,tokens_reserved FROM budget').fetchone(),(1,37))
                self.assertNotIn('reasoning_effort',bodies[-1])
                c=Client(time.monotonic()+10,dict(budget_db=p,max_requests=9,max_token_bound=10**7,max_tokens=512,temperature=0.5,reasoning_effort='low'))
                c.complete('Return JSON.',{'x':2})
                self.assertEqual((bodies[-1]['max_tokens'],bodies[-1]['temperature'],bodies[-1]['reasoning_effort']),(512,0.5,'low'))
        finally:server.shutdown();server.server_close();thread.join(2)
    def test_budget_keeps_reservation_without_valid_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=str(Path(tmp)/'b.sqlite');database(p);b=Budget(p,dict(max_requests=9,max_token_bound=10**6))
            reserved=b.reserve(1000,500)
            for actual in (None,'37',-1,reserved+1):b.settle(reserved,actual)
            with closing(sqlite3.connect(p)) as db:
                self.assertEqual(db.execute('SELECT tokens_reserved FROM budget').fetchone()[0],1500)
    def test_smoke_gate_blocks_api_failures_not_solution_errors(self):
        from evaluation.run_benchmark import compatible_smoke
        ok=lambda:dict(validation=dict(outcome='pass'),api_errors=[],observed_error=None)
        err=lambda code,api=():dict(validation=dict(outcome='system_error'),api_errors=list(api),observed_error=code)
        self.assertTrue(compatible_smoke([ok()]*10+[err('evidence_size_limit')]*2))
        for bad in [err('truncated_model_output'),err('worker_timeout'),err('benchmark_budget_exhausted'),err(None),err('evidence_size_limit',['http_500'])]:
            self.assertFalse(compatible_smoke([ok()]*11+[bad]),bad)
        self.assertFalse(compatible_smoke([ok()]*9))
    def test_solution_uses_synthetic_archive_and_preserves_contract(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));p=json.loads(body['messages'][1]['content']);captured.append(p)
                if 'candidate' in p:
                    value=dict(approved=True,complete=True,status='answer',claim_checks=[dict(index=0,supported=True,applicable=True)])
                else:
                    f=next(f for f in p['evidence'] if '73' in f['text'])
                    value=dict(status='answer',claims=[dict(text=f['text'],sources=[dict(fragment_id=f['id'],quote=f['text'])])],missing=[],clarification='')
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(value,ensure_ascii=False)))]),ensure_ascii=False).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);data=p/'data';data.mkdir();archive(data/'knowledge-base.zip',{'unique.txt':'Для вымышленного договора ZZ-991/2031 срок оплаты равен 73 рабочим дням после акта.'})
                (data/'questions.csv').write_text('id,question\n001,Срок оплаты ZZ-991/2031?\n',encoding='utf-8')
                env={**os.environ,'DATA_DIR':str(data),'LLM_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1','LLM_API_KEY':'SYNTHETIC_TEST','LLM_MODEL':'stub','PSB_RUN_SECONDS':'10','PYTHONIOENCODING':'utf-8'}
                proc=subprocess.run([sys.executable,str(ROOT/'prototype/solution.py')],cwd=p,env=env,capture_output=True,encoding='utf-8',timeout=15)
                self.assertEqual(proc.returncode,0,proc.stderr)
                with (p/'submission.csv').open(encoding='utf-8',newline='') as h:rows=list(csv.DictReader(h))
                self.assertEqual(rows[0]['id'],'001');self.assertIn('73',rows[0]['answer'])
                self.assertTrue(all(f['document']=='unique.txt' for payload in captured for f in payload['evidence']))
        finally:server.shutdown();server.server_close();thread.join(2)
    def test_invalid_question_and_missing_search_are_not_inferred_success(self):
        from psb_policy import answer_question
        self.assertEqual(answer_question(None,None,None)[1],'technical_error')
        self.assertEqual(answer_question('x'*32001,None,None)[1],'technical_error')

if __name__=='__main__':unittest.main()
