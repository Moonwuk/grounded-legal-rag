"""Run the unmodified solution.py on a section-14 corpus and check its answers.

Corpus layout (see evaluation/corpora/README.md):
  <corpus>/corpus.json        identity, knowledge base path, tuning note
  <corpus>/data/questions.csv platform format: id,question
  <corpus>/gold/cases.json    elements per case; never given to the solution

The solution receives only a temporary DATA_DIR with knowledge-base.zip and
questions.csv, exactly as on the platform, and writes submission.csv.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from evaluation.common import ROOT,EVAL,canonical,commit,digest,read,write
from evaluation.validators.elements import check

def load(corpus):
    corpus=Path(corpus);meta=read(corpus/'corpus.json')
    kb=(ROOT/meta['knowledge_base']) if not (corpus/meta['knowledge_base']).exists() else corpus/meta['knowledge_base']
    questions=corpus/meta['questions'];gold=read(corpus/meta['gold'])
    for path,key in ((kb,'knowledge_base_sha256'),(questions,'questions_sha256')):
        if digest(path.read_bytes())!=meta[key]:raise ValueError('corpus checksum mismatch: '+key)
    with questions.open(encoding='utf-8-sig',newline='') as h:rows=list(csv.DictReader(h))
    ids=[r['id'] for r in rows];cases={c['case_id']:c for c in gold['cases']}
    if len(set(ids))!=len(ids) or set(ids)!=set(cases):raise ValueError('questions and gold case ids differ')
    return meta,kb,questions,rows,cases

def score(cases,answers):
    """Rows per case; a missing answer is a contract failure, not a refusal."""
    rows=[]
    for cid,case in cases.items():
        answer=answers.get(cid)
        result=check(case,answer) if isinstance(answer,str) and answer.strip() else dict(outcome='fail',status='missing',failures=['no_answer_row'],not_evaluated=[])
        rows.append(dict(case_id=cid,family=case.get('family'),checked_by_hand=case.get('checked_by_hand') is True,answer=answer,**result))
    return rows

def summarize(rows):
    answerable=[r for r in rows if r['status']!='technical_error']
    return dict(outcomes=dict(Counter(r['outcome'] for r in rows)),statuses=dict(Counter(r['status'] for r in rows)),
        passed=sum(r['outcome']=='pass' for r in rows),total=len(rows),
        false_refusals=sum('false_refusal' in r['failures'] for r in answerable),
        failures={r['case_id']:r['failures'] for r in rows if r['failures']},
        not_evaluated={r['case_id']:r['not_evaluated'] for r in rows if r['not_evaluated']},
        checked_by_hand=sum(r['checked_by_hand'] for r in rows))

def run(args):
    meta,kb,questions,rows,cases=load(args.corpus)
    out=EVAL/'reports'/args.run_id;out.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('LLM_','OPENAI_','GEN_'))}
    env.update(LLM_BASE_URL=os.environ.get('LLM_BASE_URL',''),LLM_API_KEY=os.environ.get('LLM_API_KEY',''),LLM_MODEL=os.environ.get('LLM_MODEL',''),PYTHONIOENCODING='utf-8')
    if not all(env[k] for k in ('LLM_BASE_URL','LLM_API_KEY','LLM_MODEL')):raise SystemExit('LLM_BASE_URL, LLM_API_KEY and LLM_MODEL are required')
    started=time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp);(work/'data').mkdir()
        shutil.copyfile(kb,work/'data/knowledge-base.zip');shutil.copyfile(questions,work/'data/questions.csv')
        env['DATA_DIR']=str(work/'data')
        proc=subprocess.run([sys.executable,str(ROOT/'prototype/solution.py')],cwd=work,env=env,capture_output=True,encoding='utf-8',timeout=1250)
        answers={}
        if (work/'submission.csv').exists():
            with (work/'submission.csv').open(encoding='utf-8',newline='') as h:answers={r['id']:r['answer'] for r in csv.DictReader(h)}
    scored=score(cases,answers)
    # stderr holds only application-owned event lines (no prompts, keys or model text).
    (out/'solution-events.log').write_text(proc.stderr,encoding='utf-8')
    info=dict(git_commit=commit(),corpus_id=meta['corpus_id'],knowledge_base_sha256=meta['knowledge_base_sha256'],questions_sha256=meta['questions_sha256'],
        gold_sha256=digest(canonical(cases)),runtime_sha256=digest(canonical({p.name:digest(p.read_bytes()) for p in sorted((ROOT/'prototype').glob('*.py'))})),
        model=env['LLM_MODEL'],provider_base_url=env['LLM_BASE_URL'],returncode=proc.returncode,elapsed_seconds=time.perf_counter()-started,
        tuning_note=meta.get('tuning_note'),scope='Local element check, not the official Score.')
    summary={**info,**summarize(scored)}
    write(out/'summary.json',summary);write(out/'cases.json',scored)
    print(json.dumps({k:summary[k] for k in ('passed','total','outcomes','statuses','failures','not_evaluated','elapsed_seconds')},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--run-id',required=True)
    run(p.parse_args())

if __name__=='__main__':main()
