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
from psb_policy import answer_question, approved, FOLLOWUPS, ISSUES
from net_client import Client

class TracedRetriever:
    """Transparent observer of the production Retriever.

    Only search() is recorded. Every other member (documents, evidence,
    complete_sources, reference_gaps, ...) is forwarded unchanged, because the
    policy enables code paths by hasattr/getattr. A partial interface would
    silently measure a different algorithm than the submitted one.
    """
    def __init__(self,retriever):self.r=retriever;self.calls=[]
    def search(self,*args,**kwargs):
        t=time.perf_counter();hits=self.r.search(*args,**kwargs)
        self.calls.append(dict(expanded=kwargs.get('expanded',False),fragments=[dataclasses.asdict(f) for f in hits],seconds=time.perf_counter()-t))
        return hits
    def __getattr__(self,name):
        if name in {'r','calls'}:raise AttributeError(name)
        return getattr(self.r,name)

def cited_fragments(calls,candidate):
    """Source addresses from the evidence the policy actually received.

    search() restores complete source blocks under new IDs, so the loader
    fragment list is not the address space of accepted citations.
    """
    seen={f['id']:f for call in calls for f in call['fragments']}
    cited=list(dict.fromkeys(c['fragment_id'] for claim in (candidate or {}).get('claims',[]) for c in claim['sources']))
    return [seen[i] for i in cited if i in seen],sorted(i for i in cited if i not in seen)

class NullClient:
    """Integration-only model stub; never reads truth or invents a fact answer."""
    def __init__(self):self.events=[];self.attempts=0;self.usage=[];self.errors=[]
    def complete(self,system,payload):
        self.attempts+=1
        if 'candidate' in payload:
            c=payload['candidate'];r=dict(approved=True,complete=False,status=c['status'],claim_checks=[])
        else:r=dict(status='insufficient',claims=[],missing=['document'],clarification='',requested_facts=['document'])
        self.events.append(dict(payload=payload,response=r));return r

def model_steps(events):
    """Typed per-call diagnostics: why a candidate was or was not accepted.

    Only statuses, flags and positions; no prompt, evidence, model prose or
    hidden reasoning is copied.
    """
    def code(value,allowed):return value if isinstance(value,str) and value in allowed else ('invalid' if value is not None else None)
    # Only application-owned codes: how the candidate named its gap or problem.
    def facts(value):return [code(x,FOLLOWUPS) for x in value[:8]] if isinstance(value,list) else None
    def issue(value):return code(value,ISSUES) if value else None
    statuses={'answer','partial','clarify','insufficient','out_of_scope','disallowed'}
    steps=[]
    for e in events:
        p,r=e.get('payload',{}),e.get('response')
        r=r if isinstance(r,dict) else {}
        if 'candidate' in p:
            c=p['candidate'];checks=r.get('claim_checks') if isinstance(r.get('claim_checks'),list) else []
            # Corpus file names of each selected provision (no text) to see which one was rejected.
            where={f.get('id'):f.get('document') for f in p.get('evidence',[]) if isinstance(f,dict)}
            documents=[sorted({where.get(x.get('fragment_id'),'?') for x in claim.get('sources',[]) if isinstance(x,dict)})
                       for claim in c.get('claims',[]) if isinstance(claim,dict)]
            steps.append(dict(stage='verify',expanded=p.get('expanded_search') is True,candidate_status=c.get('status'),
                prose=bool(c.get('answer')),approved=approved(c,r),verdict_status=code(r.get('status'),statuses),
                requested_facts=facts(c.get('requested_facts')),issue=issue(c.get('issue')),
                complete=r.get('complete') is True,answer_supported=r.get('answer_supported') is True,
                rejected_claims=[i for i,x in enumerate(checks[:12]) if not isinstance(x,dict) or x.get('supported') is not True or x.get('applicable') is not True],
                unsupported_claims=[i for i,x in enumerate(checks[:12]) if isinstance(x,dict) and x.get('supported') is not True],
                inapplicable_claims=[i for i,x in enumerate(checks[:12]) if isinstance(x,dict) and x.get('applicable') is not True],
                claim_documents=documents))
        elif 'compatibility_probe' not in p:
            ids=r.get('source_ids')
            steps.append(dict(stage='generate',expanded=p.get('expanded_search') is True,status=code(r.get('status'),statuses),
                selected=len(ids) if isinstance(ids,list) else None,prose=bool(r.get('answer')),
                requested_facts=facts(r.get('requested_facts')),issue=issue(r.get('issue')),
                retry_reason=p.get('retry_reason') if isinstance(p.get('retry_reason'),str) and len(p['retry_reason'])<=64 else None))
    return steps

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
                out['model_steps']=model_steps(client.events)
                for e in client.events:
                    p=e['payload']
                    if 'candidate' in p and p['rendered_answer']==answer and approved(p['candidate'],e['response']):
                        out.update(candidate=p['candidate'],rendered_answer=p['rendered_answer'])
            out['searches']=traced.calls
            out['fragments'],unobserved=cited_fragments(traced.calls,out.get('candidate'))
            if unobserved:out['unobserved_citations']=unobserved
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
