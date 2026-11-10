"""Synthetic bounded stress runs; not a production capacity benchmark."""
from pathlib import Path
import importlib.util
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus
from psb_retrieval import Retriever


def child(size):
    # Lower than the platform's 16 GiB; makes accidental allocation spikes visible.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    with tempfile.TemporaryDirectory() as temp:
        p = Path(temp) / 'synthetic.zip'
        t = time.monotonic()
        with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in range(size):
                text = (f'ДОГОВОР С КОНТРАГЕНТОМ Номер{i}\n'
                        f'1. Оплата составляет {i*17+1000} условных единиц.\n'
                        f'2. Срок проверки {i%27+1} рабочих дней.\n'
                        + ('3. Дополнительные условия поставки и приёмки товара.\n' * (i%9+1)))
                z.writestr(f'contract_{i}.txt', text)
        d, f = load_corpus(p, time.monotonic() + 20)
        r = Retriever(d, f, time.monotonic() + 20)
        indexed = time.monotonic()
        durations=[]
        for i in range(20):
            a=time.monotonic()
            r.search(f'Номер{i*31} срок проверки и какой размер оплаты')
            durations.append((time.monotonic()-a)*1000)
        return {'documents':len(d),'fragments':len(f),'archive_bytes':p.stat().st_size,
                'create_load_index_seconds':round(indexed-t,3),
                'search_p50_ms':round(statistics.median(durations),3),
                'search_p95_ms':round(sorted(durations)[18],3),
                'max_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
                'address_space_limit_mib':512}


def main():
    results=[]
    for size in (100,1000,4000):
        p=subprocess.run([sys.executable,__file__,'--child',str(size)],cwd=ROOT,capture_output=True,text=True,timeout=35)
        results.append(json.loads(p.stdout) if p.returncode==0 else {'documents_requested':size,'exit_code':p.returncode,'error':p.stderr[-500:]})
    sys.path.insert(0,str(ROOT/'tests'))
    from test_security import EntrypointTests
    EntrypointTests.setUpClass()
    case=EntrypointTests('test_concurrent_batch_and_no_cross_id_history')
    proc,elapsed,rows,calls=case.run_zip(count=1000,seconds='25')
    batch={'questions':len(rows),'http_calls':len(calls),'seconds':round(elapsed,3),'exit_code':proc.returncode,
           'all_rows_complete':all('пределы моей задачи' in row['answer'] for row in rows),
           'generator':'local HTTP stub, no model inference; 8 workers'}
    # Differential replay checks that the inverted index retains the old ranking.
    old_path=ROOT/'eval/fixtures/legacy_retrieval.py'
    spec=importlib.util.spec_from_file_location('old_retrieval',old_path)
    old=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    d,f=load_corpus(ROOT/'organizer/knowledge-base.zip')
    before,after=old.Retriever(d,f),Retriever(d,f)
    cases=json.loads((ROOT/'eval/cases.json').read_text())
    if isinstance(cases,dict):cases=cases['cases']
    matches=[]; old_ms=[]; new_ms=[]
    for c in cases:
        q=c['question']
        for expanded in (False,True):
            a=time.monotonic(); b=before.search(q,top_k=6,expanded=expanded);old_ms.append((time.monotonic()-a)*1000)
            a=time.monotonic(); n=after.search(q,top_k=6,expanded=expanded);new_ms.append((time.monotonic()-a)*1000)
            matches.append([x.id for x in b]==[x.id for x in n])
    value={'synthetic_scaling':results,'batch':batch,'differential':{'queries':len(matches),'identical_evidence_order':sum(matches),
           'old_p50_ms':round(statistics.median(old_ms),3),'new_p50_ms':round(statistics.median(new_ms),3)},
           'limitations':'Synthetic corpora, one machine, lexical search only; no 16 GiB/8 CPU platform environment or production SLA verified.'}
    (ROOT/'results/security_stress_20261110/resources.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print(json.dumps(value,ensure_ascii=False,indent=2))

if __name__=='__main__':
    if len(sys.argv)>1:print(json.dumps(child(int(sys.argv[2]))))
    else:main()
