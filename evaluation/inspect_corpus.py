"""Real production loader/index verification and separate index snapshots."""
from __future__ import annotations
import argparse
from collections import Counter
import dataclasses
from pathlib import Path
import sys
import time
from evaluation.common import ROOT,EVAL,read,write,digest,canonical
sys.path.insert(0,str(ROOT/'prototype'))
from psb_corpus import load_corpus
from psb_retrieval import Retriever

def inspect(name):
    base=EVAL/'generated_corpora'/name;m=read(base/'manifest.json');p=base/'knowledge-base.zip'
    if digest(p.read_bytes())!=m['archive_sha256']:raise ValueError('archive_changed')
    started=time.perf_counter();docs,frags=load_corpus(p);r=Retriever(docs,frags)
    built_seconds=time.perf_counter()-started
    index=dict(version=1,corpus_id=m['corpus_id'],archive_sha256=m['archive_sha256'],
        runtime_sha256=digest(canonical({p.name:digest(p.read_bytes()) for p in sorted((ROOT/'prototype').glob('*.py'))})),
        algorithm='production BM25 snapshot; worker rebuilds RAM index from archive, no pickle execution',
        documents=[dict(name=d.name,sha256=d.sha256,quarantined=d.quarantined) for d in docs],
        fragments=[dataclasses.asdict(f) for f in frags],postings=dict(r.postings),idf=r.idf,lengths=r.lengths,avg=r.avg,
        doc_ids={k:sorted(v) for k,v in r.doc_ids.items()},parties={k:sorted(v) for k,v in r.parties.items()})
    dest=EVAL/'indexes'/m['archive_sha256'][:16]/'bm25.json';write(dest,index)
    hashes=Counter(d.sha256 for d in docs)
    source_ok=all(f.text==r.documents[f.document].text[f.start:f.end] for f in frags)
    result=dict(corpus=name,documents=len(docs),fragments=len(frags),source_offsets_exact=source_ok,
        exact_duplicates=sum(n-1 for n in hashes.values() if n>1),nonempty=all(d.text.strip() for d in docs),
        quarantined_spans=sum(len(d.quarantined) for d in docs),load_index_seconds=built_seconds,snapshot_total_seconds=time.perf_counter()-started,
        index_path=str(dest.relative_to(EVAL)),index_sha256=digest(dest.read_bytes()),
        index_has_gold=False,supported_formats=sorted({Path(d.name).suffix for d in docs}))
    write(EVAL/'reports'/f'corpus-quality-{name}.json',result);print(result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('corpus',nargs='+');a=p.parse_args()
    for n in a.corpus:inspect(n)
