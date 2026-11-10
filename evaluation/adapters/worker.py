"""Standalone worker: imports only copied runtime and local net_client.

Input: archive path, question/history, ordinary experiment configuration.
No gold, scenario spec, expected status or case category is accepted.
"""
from collections import Counter
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
import time
from psb_corpus import load_corpus
from psb_retrieval import Retriever, tokens, user_turns
from psb_policy import answer_question, approved
from net_client import Client

class TracedRetriever:
    def __init__(self,retriever):self.r=retriever;self.calls=[]
    def search(self,*args,**kwargs):
        t=time.perf_counter();hits=self.r.search(*args,**kwargs)
        self.calls.append(dict(expanded=kwargs.get('expanded',False),fragments=[dataclasses.asdict(f) for f in hits],seconds=time.perf_counter()-t))
        return hits
    def evidence(self,fragments):return self.r.evidence(fragments)

class NullClient:
    """Integration-only model stub; never reads truth or invents a fact answer."""
    def __init__(self):self.events=[];self.attempts=0;self.usage=[];self.errors=[]
    def complete(self,system,payload):
        self.attempts+=1
        if 'candidate' in payload:
            c=payload['candidate'];r=dict(approved=True,complete=False,status=c['status'],claim_checks=[])
        else:r=dict(status='insufficient',claims=[],missing=['document'],clarification='',requested_facts=['document'])
        self.events.append(dict(payload=payload,response=r));return r

def lexical_rank(r,question,k1=1.5,b=.75):
    # Experimental RAW BM25, without production boosts/context expansion.
    # For defaults calls the actual production _scores; preserves its token weighting.
    turns=user_turns(question);q=Counter(tokens(turns[-1]))
    for t in turns[:-1]:
        for token in tokens(t):q[token]+=.35
    if k1==1.5 and b==.75:scores=r._scores(q)
    else:
        scores=Counter()
        for word,weight in q.items():
            for i,tf in r.postings.get(word,()):
                scores[i]+=weight*r.idf[word]*tf*(k1+1)/(tf+k1*(1-b+b*r.lengths[i]/r.avg))
    order=sorted(scores,key=lambda i:(-scores[i],r.fragments[i].document,r.fragments[i].start))
    return [dataclasses.asdict(r.fragments[i]) for i in order[:10] if scores[i]>0]

def main():
    inp=json.loads(sys.stdin.read());config=inp['config'];started=time.perf_counter()
    deadline=time.monotonic()+config.get('case_seconds',240)
    client=None;traced=None;out={}
    try:
        if inp.get('probe'):
            client=Client(deadline,config);out=dict(status='probe',probe=client.probe())
        else:
            docs,frags=load_corpus(Path(inp['archive']),deadline)
            r=Retriever(docs,frags,deadline);traced=TracedRetriever(r)
            history=inp.get('history',[]);labels={'user':'Пользователь','assistant':'Ассистент'}
            question=inp['question']
            if history:question='\n'.join(labels[x['role']]+': '+x['content'] for x in history)+'\nПользователь: '+question
            rank=lexical_rank(r,question,config.get('bm25_k1',1.5),config.get('bm25_b',.75))
            out=dict(mode=config['engine'],raw_bm25=rank,documents=[dict(name=d.name,sha256=d.sha256,text=d.text,text_sha256=hashlib.sha256(d.text.encode()).hexdigest()) for d in docs])
            if config['engine']=='retrieval':
                traced.search(question,top_k=config['top_k']);out.update(status='not_run',answer='',candidate=None)
            else:
                client=Client(deadline,config) if config['engine']=='deepseek' else NullClient()
                answer,status=answer_question(question,traced,client,config['top_k'])
                out.update(answer=answer,status=status,candidate=None)
                if status=='technical_error' and hasattr(client,'last_error'):out['error']=client.last_error
                for e in client.events:
                    p=e['payload']
                    if 'candidate' in p and p['rendered_answer']==answer and approved(p['candidate'],e['response']):
                        out.update(candidate=p['candidate'],rendered_answer=p['rendered_answer'])
            out['searches']=traced.calls
            cited={c['fragment_id'] for claim in (out.get('candidate') or {}).get('claims',[]) for c in claim['sources']}
            out['fragments']=[dataclasses.asdict(f) for f in frags if f.id in cited]
            used={f['document'] for call in traced.calls for f in call['fragments']} | {f['document'] for f in rank}
            out['documents']=[d for d in out['documents'] if d['name'] in used]
    except Exception as exc:
        # No arbitrary exception body, source text, prompt or key in diagnostics.
        code=str(exc) if type(exc).__name__ in {'ProviderError','ValueError'} else type(exc).__name__
        if not __import__('re').fullmatch(r'[a-zA-Z_0-9]{1,80}',code):code='worker_error'
        out.update(status='technical_error',answer='',error=code,searches=traced.calls if traced else [])
    out.update(seconds=time.perf_counter()-started,requests=client.attempts if client else 0,
               usage=client.usage if client else [],api_errors=client.errors if client else [])
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main()
