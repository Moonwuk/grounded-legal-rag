"""Budgeted transport wrapper around the UNMODIFIED production ProxyClient.

Copied into isolated worker directory. No evaluation/gold imports. Credentials
exist only in the worker environment and authorization headers.
"""
import json
from contextlib import closing
import os
import sqlite3
import time
from urllib.request import Request
from psb_llm import ProxyClient, ProviderError, strict_json

class Budget:
    def __init__(self,path,config):self.path=path;self.config=config

    def reserve(self,input_bytes,output_tokens):
        # UTF-8 bytes are a conservative token bound, not a billing estimate.
        tokens=input_bytes+output_tokens
        price=max(self.config.get('input_price_per_million',0),self.config.get('output_price_per_million',0))
        cost=tokens*price/1e6
        with closing(sqlite3.connect(self.path,timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            requests,reserved,spent=db.execute('SELECT requests,tokens_reserved,cost_reserved FROM budget WHERE id=1').fetchone()
            if requests+1>self.config['max_requests'] or reserved+tokens>self.config['max_token_bound']:
                raise ProviderError('benchmark_budget_exhausted')
            if self.config.get('max_cost') is not None and spent+cost>self.config['max_cost']:
                raise ProviderError('benchmark_cost_exhausted')
            db.execute('UPDATE budget SET requests=?,tokens_reserved=?,cost_reserved=? WHERE id=1',(requests+1,reserved+tokens,spent+cost))
        return tokens

class RecordingResponse:
    def __init__(self,response,owner):self.response=response;self.owner=owner;self.parts=[]
    def __enter__(self):self.response.__enter__();return self
    def read1(self,n):
        b=self.response.read1(n);self.parts.append(b);return b
    def __exit__(self,*args):
        try:
            data=json.loads(b''.join(self.parts));usage=data.get('usage',{})
            self.owner.usage.append({k:v for k,v in usage.items() if k in {'prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'} and type(v) is int})
        except (ValueError,TypeError): pass
        return self.response.__exit__(*args)

class RecordingOpener:
    def __init__(self,opener,owner,config):self.opener=opener;self.owner=owner;self.config=config
    def open(self,request,timeout):
        body=request.data or b''
        bound=json.loads(body).get('max_tokens',0) if body else 0
        self.owner.budget.reserve(len(body),bound)
        self.owner.attempts+=1
        try:
            r=self.opener.open(request,timeout=min(timeout,self.config['timeout']))
            return RecordingResponse(r,self.owner)
        except Exception as exc:
            self.owner.errors.append('http_'+str(exc.code) if hasattr(exc,'code') else type(exc).__name__)
            raise

class Client(ProxyClient):
    def __init__(self,deadline,config):
        # Explicit DeepSeek settings prevent accidental use of an unrelated account.
        for suffix in ('API_KEY','BASE_URL','MODEL'):
            value=os.getenv('DEEPSEEK_'+suffix,'')
            if suffix=='BASE_URL' and not value:value='https://api.deepseek.com/v1'
            os.environ['LLM_'+suffix]=value
        super().__init__(deadline)
        os.environ['MAX_TOKENS']=str(config.get('max_tokens',2048))
        os.environ['TEMPERATURE']=str(config.get('temperature',0))
        self.attempts=0;self.errors=[];self.usage=[];self.events=[]
        self.budget=Budget(config['budget_db'],config)
        self.opener=RecordingOpener(self.opener,self,config)
    def complete(self,system,payload):
        try:value=super().complete(system,payload)
        except ProviderError as exc:
            self.last_error=str(exc)
            raise
        self.events.append(dict(payload=payload,response=value))
        return value
    def probe(self):
        # Model catalogue + a real JSON completion in smoke, before any large run.
        request=Request(self.base+'/models',headers={'Authorization':'Bearer '+self.key})
        self.budget.reserve(0,0);self.attempts+=1
        with self.opener.opener.open(request,timeout=20) as r:
            raw=r.read(1000000)
        data=strict_json(raw)
        ids=[x['id'] for x in data.get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)]
        if self.model not in ids: raise ProviderError('configured_model_not_listed')
        result=self.complete('Return only a JSON object: {"ok":true}.',{'compatibility_probe':True})
        if result.get('ok') is not True:raise ProviderError('compatibility_probe_failed')
        return dict(model=self.model,listed=True,json_completion=True)
