"""Delta-debug an observed retrieval exception; never invoke LLM or change RAG."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import tempfile
import zipfile
from evaluation.common import EVAL,ROOT,read,write,archive,question_text
sys.path.insert(0,str(ROOT/'prototype'))
from psb_corpus import load_corpus
from psb_retrieval import Retriever

def reproduce(files,question,top_k,path,telemetry=None):
    archive(path,files)
    try:
        d,f=load_corpus(path);r=Retriever(d,f)
        def trace(frame,event,arg):
            if telemetry is not None and event=='exception' and frame.f_code.co_name=='search' and str(arg[1])=='evidence_size_limit':
                result=frame.f_locals.get('result',[])
                telemetry.update(context_fragments=len(result),context_characters=sum(len(x.text) for x in result),context_documents=len({x.document for x in result}),
                                 seed_hits=len(frame.f_locals.get('hits',[])),connected_documents=len(frame.f_locals.get('connected',[])))
            return trace
        previous=sys.gettrace()
        try:
            if telemetry is not None:sys.settrace(trace)
            r.search(question,top_k=top_k)
        finally:sys.settrace(previous)
        return None
    except ValueError as e:return str(e)

def minimize(run_id,case_id,corpus):
    report=read(EVAL/'reports'/run_id/'cases'/f'{case_id}.json');target=report['observed_error']
    question=next(q for q in read(EVAL/'questions'/f'{corpus}.json') if q['case_id']==case_id)
    text=question_text(question['question'],question['history']);top_k=read(EVAL/'reports'/run_id/'manifest.json')['config']['top_k']
    with zipfile.ZipFile(EVAL/'generated_corpora'/corpus/'knowledge-base.zip') as z:files={n:z.read(n) for n in z.namelist()}
    original=len(files);checks=0
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'candidate.zip'
        def fails(values):
            nonlocal checks
            checks+=1
            return bool(values) and reproduce(values,text,top_k,path)==target
        if not fails(files):raise ValueError('reported failure did not reproduce')
        size=2
        while len(files)>1:
            names=list(files);chunk=max(1,(len(names)+size-1)//size);changed=False
            for i in range(0,len(names),chunk):
                remove=set(names[i:i+chunk]);candidate={n:b for n,b in files.items() if n not in remove}
                if fails(candidate):files=candidate;size=max(2,size-1);changed=True;break
            if not changed:
                if size>=len(files):break
                size=min(len(files),size*2)
        # Explicit one-deletion verification establishes 1-minimality, not global minimum.
        one_minimal=all(not fails({n:b for n,b in files.items() if n!=removed}) for removed in files)
    out=EVAL/'reports'/run_id/'reproduction';out.mkdir(exist_ok=True)
    sha=archive(out/f'{case_id}-minimal.zip',files)
    result=dict(case_id=case_id,original_documents=original,remaining_documents=len(files),files=sorted(files),
        expected_exception=target,question=text,top_k=top_k,checks=checks,one_deletion_minimal=one_minimal,
        sha256=sha,scope='1-minimal observed exception under deterministic replay, not global cardinality minimum')
    write(out/f'{case_id}-minimal.json',result);print(result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--case-id',required=True);p.add_argument('--corpus',default='synthetic');a=p.parse_args();minimize(a.run,a.case_id,a.corpus)
