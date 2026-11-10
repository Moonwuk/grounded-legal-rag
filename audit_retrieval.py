"""Measure evidence coverage, not answer correctness or LLM-judge score."""
from pathlib import Path
import sys, json, statistics, time, hashlib
from dataclasses import asdict
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'prototype'))
from psb_corpus import load_corpus, norm
from psb_retrieval import Retriever


def main():
    start=time.perf_counter()
    docs,frags=load_corpus(ROOT/'organizer/knowledge-base.zip')
    retriever=Retriever(docs,frags)
    index_seconds=time.perf_counter()-start
    cases=json.loads((ROOT/'eval/cases.json').read_text())['cases']
    rows=[]
    for case in cases:
        start=time.perf_counter()
        hits=retriever.search(case['question'])
        elapsed=time.perf_counter()-start
        by_doc={}
        for f in hits:
            by_doc.setdefault(f.document,[]).append(f)
        texts={n:norm(' '.join(f.text for f in sorted(fs,key=lambda x:x.start))) for n,fs in by_doc.items()}
        req=case['required_evidence']
        matched=[norm(e['quote']) in texts.get(e['document'],'') for e in req]
        rows.append({'id':case['id'],'origin':case['origin'],'required':len(req),'found':sum(matched),
                     'all_required_found':all(matched) if req else None,
                     'missing':[e for e,ok in zip(req,matched) if not ok],
                     'selected_documents':list(by_doc),'context_characters':sum(len(f.text) for f in hits),
                     'retrieval_seconds':elapsed})
    eligible=[r for r in rows if r['required']]
    report={'scope':'Offline retrieval coverage on an author-labelled development set. NOT answer accuracy, NOT a blind benchmark, NOT competition score.',
            'documents':len(docs),'fragments':len(frags),'quarantined_lines':sum(len(d.quarantined) for d in docs),
            'index_seconds':index_seconds,'cases_total':len(rows),'cases_with_evidence':len(eligible),
            'all_evidence_cases':sum(r['all_required_found'] for r in eligible),
            'span_recall':sum(r['found'] for r in eligible)/sum(r['required'] for r in eligible),
            'median_context_characters':statistics.median(r['context_characters'] for r in rows),
            'max_context_characters':max(r['context_characters'] for r in rows),
            'rows':rows}
    out=ROOT/'results';out.mkdir(exist_ok=True)
    (out/'retrieval_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    manifest=[]
    for d in docs:
        manifest.append({'name':d.name,'sha256':d.sha256,'characters':len(d.text),
                         'fragments':sum(f.document==d.name for f in frags),
                         'quarantined_source_spans':[{'start':a,'end':b,'text':d.text[a:b]} for a,b in d.quarantined]})
    (out/'corpus_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
    for r in rows:
        if r['missing']:
            print('MISSING',r['id'],r['missing'])


if __name__=='__main__':main()
