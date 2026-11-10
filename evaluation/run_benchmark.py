"""Controller keeps gold outside worker. JSON config, checkpointed per case."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from evaluation.common import ROOT,EVAL,VERSION,read,write,canonical,digest,commit
from evaluation.validators import validate,retrieval
from evaluation.validators.core import recall_coverage
from evaluation.analyze_results import report

def execute(worker,inp):
    try:
        proc=subprocess.run([sys.executable,'-I',str(worker/'worker.py')],input=json.dumps(inp,ensure_ascii=False),
            cwd=worker,env={**os.environ,'PYTHONPATH':'','PYTHONIOENCODING':'utf-8'},capture_output=True,encoding='utf-8',
            timeout=inp['config'].get('case_seconds',240)+10)
        if proc.returncode!=0:return dict(status='technical_error',error='worker_process_failed',answer='')
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:return dict(status='technical_error',error='worker_timeout',answer='')

def run(args):
    started=time.perf_counter();config=read(args.config)
    config.update(engine=args.engine,top_k=args.top_k or config['top_k'])
    if args.workers:config['workers']=args.workers
    if args.max_requests is not None:config['max_requests']=args.max_requests
    if args.no_save_responses:config['save_responses']=False
    if not 1<=config['workers']<=8 or not 1<=config['top_k']<=40:raise ValueError('workers/top_k out of range')
    if config.get('max_cost') is not None and min(config['input_price_per_million'],config['output_price_per_million'])<=0:raise ValueError('cost cap requires explicit positive unit prices')
    name=args.corpus;cp=EVAL/'generated_corpora'/name;archive=cp/'knowledge-base.zip'
    if name=='public' and args.engine!='retrieval':raise ValueError('public gold is structural retrieval only; no public legal accuracy annotation')
    gold_path=EVAL/'gold'/f'{name}.json';questions_path=EVAL/'questions'/f'{name}.json'
    gold=read(gold_path);questions=read(questions_path);manifest=read(cp/'manifest.json')
    if digest(archive.read_bytes())!=manifest['archive_sha256']:raise ValueError('corpus checksum mismatch')
    if gold['corpus_id']!=manifest['corpus_id']:raise ValueError('gold corpus identity mismatch')
    cases={c['case_id']:c for c in gold['cases']}
    selected=[q for q in questions if (q['split']=='holdout')==(args.mode=='holdout')]
    # Interleave categories so smoke is representative, not the first 12 simple facts.
    selected.sort(key=lambda q:(int(q['case_id'].rsplit('-',1)[-1]) if q['case_id'].rsplit('-',1)[-1].isdigit() else 0,q['case_id']))
    if args.case_id:selected=[q for q in selected if q['case_id']==args.case_id]
    limit=args.limit or (12 if args.mode in {'smoke','integration'} else len(selected))
    selected=selected[:limit]
    if not selected:raise ValueError('empty selection')
    if args.mode=='smoke' and not 10<=len(selected)<=20:raise ValueError('smoke requires 10..20 questions')
    runtime_sha=digest(canonical({p.name:digest(p.read_bytes()) for p in sorted((ROOT/'prototype').glob('*.py'))}))
    own_sha=digest(canonical({str(p.relative_to(EVAL)):digest(p.read_bytes()) for p in sorted(EVAL.rglob('*.py'))}))
    info=dict(version=VERSION,git_commit=commit(),runtime_sha256=runtime_sha,evaluation_sha256=own_sha,
        validator_sha256=digest((EVAL/'validators/core.py').read_bytes()),
        retrieval_adapter_sha256=digest((EVAL/'adapters/worker.py').read_bytes()),
        corpus_id=manifest['corpus_id'],corpus_sha256=manifest['archive_sha256'],gold_sha256=digest(gold_path.read_bytes()),
        gold_version=gold['version'],questions_sha256=digest(questions_path.read_bytes()),selection_sha256=digest(canonical(selected)),
        documents=manifest['documents'],questions_selected=len(selected),mode=args.mode,engine=args.engine,
        model=os.getenv('DEEPSEEK_MODEL') if args.engine=='deepseek' else None,
        provider_base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1') if args.engine=='deepseek' else None,config=config)
    if info['provider_base_url']:
        from urllib.parse import urlparse
        parsed=urlparse(info['provider_base_url'])
        if parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('provider URL must not contain credentials/query/fragment')
    fingerprint=digest(canonical(info));out=EVAL/'reports'/args.run_id;out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        previous=read(out/'manifest.json')
        if previous['fingerprint']!=fingerprint:raise ValueError('resume fingerprint mismatch; use new run-id')
        if not args.resume:raise ValueError('run exists; use --resume or a new run-id')
    info.update(fingerprint=fingerprint,started_utc=datetime.now(timezone.utc).isoformat())
    write(out/'manifest.json',info)
    db=out/'budget.sqlite'
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, requests INTEGER,tokens_reserved INTEGER,cost_reserved REAL)')
        conn.execute('INSERT OR IGNORE INTO budget VALUES(1,0,0,0)')
    config={**config,'budget_db':str(db.resolve())}
    before={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in (ROOT/'organizer').rglob('*') if p.is_file()}
    rows=[]
    with tempfile.TemporaryDirectory(prefix='psb-evaluation-') as tmp:
        worker=Path(tmp)
        for p in (ROOT/'prototype').glob('*.py'):shutil.copyfile(p,worker/p.name)
        for name_ in ('worker.py','net_client.py'):shutil.copyfile(EVAL/'adapters'/name_,worker/name_)
        safe_archive=worker/'knowledge-base.zip';shutil.copyfile(archive,safe_archive)
        # isolated mode doesn't add the script directory; use explicit bootstrap file.
        original=(worker/'worker.py').read_text(encoding='utf-8')
        (worker/'worker.py').write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parent))\n'+original,encoding='utf-8')
        if args.engine=='deepseek':
            if not os.getenv('DEEPSEEK_API_KEY') or not os.getenv('DEEPSEEK_MODEL'):
                info.update(api_status='not_run_missing_environment',elapsed_seconds=time.perf_counter()-started,isolation='worker inputs contain only archive/question/history/config; gold not copied')
                report(out,info,[]);return
            smoke_marker=EVAL/'reports'/f'smoke-{manifest["corpus_id"]}.json'
            if args.mode not in {'smoke','integration'}:
                if not smoke_marker.exists():raise ValueError('run real smoke first')
                marker=read(smoke_marker)
                if any(marker.get(k)!=info.get(k) for k in ('runtime_sha256','corpus_sha256','model')):raise ValueError('smoke model/corpus/runtime mismatch')
            if not args.resume or not (out/'probe.json').exists():
                probe=execute(worker,dict(probe=True,config=config));write(out/'probe.json',probe)
                if probe.get('status')!='probe':info.update(api_status='probe_failed');report(out,info,[]);return
        def one(q):
            cid=q['case_id'];case=cases[cid];path=out/'cases'/f'{cid}.json'
            if args.resume and path.exists():return read(path)
            inp=dict(archive=str(safe_archive),question=q['question'],history=q['history'],config=config)
            res=execute(worker,inp);hits=res.get('searches',[])
            ctx=hits[-1]['fragments'] if hits else []
            suff=retrieval(case,gold['sources'],ctx) if hits else None
            raw=res.get('raw_bm25',[])
            recalls={str(k):recall_coverage(case,gold['sources'],raw[:k]) if 'raw_bm25' in res else None for k in (1,5,10)}
            result=validate(case,gold,res)
            retrieval_failed=suff is False
            if retrieval_failed:result['failures']=sorted(set(result['failures']+['retrieval_failure']))
            row=dict(case_id=cid,category=case['category'],engine=args.engine,status=res.get('status'),seconds=res.get('seconds',0),
                answerable='answer' in case['expected']['allowed_statuses'],expects_clarification='clarification' in case['expected']['allowed_statuses'],
                has_required_evidence=bool(case['expected']['required_claims']),
                recall=recalls,sufficient=suff,validation=result,requests=res.get('requests',0),usage=res.get('usage',[]),api_errors=res.get('api_errors',[]),
                observed_error=res.get('error'),retrieval_failure=retrieval_failed)
            if config['save_responses']:
                row['observation']=res
            else:
                row['observation_hash']=digest(canonical(res))
            write(path,row)
            if result['failures']:
                # Reproduction references full corpus; no false claim of minimality.
                # Minimized source archive includes required + retrieved docs; reranking may differ.
                names={f['document'] for f in ctx}
                for r in case['expected']['required_claims']:
                    names.update(gold['sources'][s]['document'] for ss in r['acceptable_evidence_sets'] for s in ss)
                write(out/'reproduction'/f'{cid}.json',dict(case_id=cid,question=q['question'],history=q['history'],
                    corpus=str(archive.relative_to(ROOT)),candidate_documents=sorted(names),
                    command=f'python -m evaluation.run_benchmark --corpus {args.corpus} --mode {args.mode} --engine {args.engine} --case-id {cid} --run-id repro-{cid}',
                    caution='candidate reduced context; full corpus is authoritative for rank reproduction',failures=result['failures']))
            return row
        with ThreadPoolExecutor(max_workers=config['workers']) as pool:
            queue=iter(selected);pending=set();stopped=False
            def fill():
                while not stopped and len(pending)<config['workers']:
                    q=next(queue,None)
                    if q is None:break
                    pending.add(pool.submit(one,q))
            fill()
            while pending:
                done,pending=wait(pending,return_when=FIRST_COMPLETED)
                for f in done:
                    row=f.result();rows.append(row)
                    if str(row.get('observed_error','')).startswith('benchmark_'):
                        stopped=True;info['stop_reason']=row['observed_error']
                    if len(rows)%25==0 or len(rows)==len(selected):print(f'completed={len(rows)}/{len(selected)}',flush=True)
                fill()
            info['cases_not_run']=len(selected)-len(rows)
    after={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in (ROOT/'organizer').rglob('*') if p.is_file()}
    if before!=after:raise RuntimeError('organizer corpus changed')
    with closing(sqlite3.connect(db)) as conn:budget=conn.execute('SELECT requests,tokens_reserved,cost_reserved FROM budget').fetchone()
    info.update(elapsed_seconds=time.perf_counter()-started,organizer_unchanged=True,budget=dict(zip(('requests','tokens_reserved','cost_reserved'),budget)),
                isolation='fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied',
                api_status='not_requested' if args.engine!='deepseek' else 'executed')
    value=report(out,info,sorted(rows,key=lambda r:r['case_id']))
    if args.engine=='deepseek' and args.mode=='smoke' and len(rows)>=10 and not any(r['validation']['outcome']=='system_error' for r in rows):
        write(EVAL/'reports'/f'smoke-{manifest["corpus_id"]}.json',info)
    print(json.dumps(dict(cases=len(rows),outcomes=value['outcomes'],output=str(out)),ensure_ascii=False))

def main():
    p=argparse.ArgumentParser();p.add_argument('--corpus',default='synthetic');p.add_argument('--mode',choices=['unit','integration','smoke','full','holdout'],default='integration')
    p.add_argument('--engine',choices=['retrieval','stub','deepseek'],default='retrieval');p.add_argument('--config',type=Path,default=EVAL/'config.json')
    p.add_argument('--run-id',default='local');p.add_argument('--limit',type=int);p.add_argument('--case-id');p.add_argument('--top-k',type=int);p.add_argument('--workers',type=int)
    p.add_argument('--max-requests',type=int);p.add_argument('--resume',action='store_true');p.add_argument('--no-save-responses',action='store_true');a=p.parse_args()
    if a.mode=='unit':raise SystemExit(subprocess.call([sys.executable,'-m','unittest','discover','-s',str(EVAL/'validator_tests'),'-v']))
    run(a)

if __name__=='__main__':main()
