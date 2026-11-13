"""Retrieval coverage on three sets, without the generation model.

- organizer base: eval/cases.json questions and their paraphrases
  (evaluation/questions/paraphrases.json); a case is covered when every
  labelled quote is in the evidence;
- LegalBench-RU public part: the gold norm of each imported case is in the
  evidence (the norm text identifies its document).

Dense candidates and the reranker are used when EMB_MODEL / RERANKER_MODEL and
the proxy variables are set, as on the platform. Measures retrieval only, not
answers or the Score.

Usage: python3 -m evaluation.retrieval_bench --legalbench path/to/legalbench_ru.jsonl [--expanded] [--run-id name]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from evaluation.common import EVAL, ROOT, write

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus, norm  # noqa: E402
from psb_llm import EmbeddingClient, ProviderError, env  # noqa: E402
from psb_retrieval import Retriever  # noqa: E402


def prepare(path):
    docs, frags = load_corpus(path)
    retriever = Retriever(docs, frags)
    notes = {}
    if env('EMB_MODEL'):
        notes['dense'] = retriever.enable_dense(EmbeddingClient(time.monotonic() + 3600), time.monotonic() + 1800)
    if env('RERANKER_MODEL') and hasattr(retriever, 'enable_rerank'):
        from psb_llm import RerankClient
        try:
            notes['rerank'] = retriever.enable_rerank(RerankClient(time.monotonic() + 3600))
        except ProviderError as error:
            notes['rerank'] = 'rerank_disabled:' + str(error)
    return retriever, notes


def covered_quotes(retriever, question, evidence, expanded):
    hits = retriever.search(question, expanded=expanded)
    texts = {}
    for f in sorted(hits, key=lambda f: f.start):
        texts[f.document] = texts.get(f.document, '') + ' ' + norm(f.text)
    return all(norm(e['quote']) in texts.get(e['document'], '') for e in evidence), sum(len(f.text) for f in hits)


def legalbench_cases(jsonl):
    rows = [json.loads(line) for line in Path(jsonl).read_text(encoding='utf-8').splitlines() if line.strip()]
    records = [r for r in rows if r.get('split') == 'public' and r.get('norm_text') and r.get('answer_type') in {'binary', 'extraction'}]
    return [(f'lb{i:03d}', r['question'], ' '.join(r['norm_text'].split())) for i, r in enumerate(records, 1)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--legalbench', type=Path, required=True)
    p.add_argument('--expanded', action='store_true')
    p.add_argument('--run-id', default='retrieval-bench')
    a = p.parse_args()
    report = dict(scope='Retrieval coverage only; development sets.', expanded=a.expanded)
    retriever, notes = prepare(ROOT / 'organizer' / 'knowledge-base.zip')
    report['organizer_modes'] = notes
    original = [c for c in json.loads((ROOT / 'eval' / 'cases.json').read_text(encoding='utf-8'))['cases'] if c['required_evidence']]
    paraphrases = json.loads((EVAL / 'questions' / 'paraphrases.json').read_text(encoding='utf-8'))['questions']
    for name, cases in (('original', original), ('paraphrases', paraphrases)):
        results = [(c['id'],) + covered_quotes(retriever, c['question'], c['required_evidence'], a.expanded) for c in cases]
        report[name] = dict(covered=f"{sum(r[1] for r in results)}/{len(results)}",
                            misses=[r[0] for r in results if not r[1]],
                            median_context=sorted(r[2] for r in results)[len(results) // 2])
    retriever, notes = prepare(EVAL / 'corpora' / 'legalbench-ru' / 'data' / 'knowledge-base.zip')
    report['legalbench_modes'] = notes
    by_text = {' '.join(d.text.split()): d.name for d in retriever.documents.values()}
    results = []
    for cid, question, gold in legalbench_cases(a.legalbench):
        hits = retriever.search(question, expanded=a.expanded)
        results.append((cid, by_text.get(gold) in {f.document for f in hits}, sum(len(f.text) for f in hits)))
    report['legalbench'] = dict(covered=f"{sum(r[1] for r in results)}/{len(results)}",
                                misses=[r[0] for r in results if not r[1]],
                                median_context=sorted(r[2] for r in results)[len(results) // 2])
    write(EVAL / 'reports' / a.run_id / 'summary.json', report)
    print(json.dumps({k: (v if not isinstance(v, dict) else {x: y for x, y in v.items() if x != 'misses'}) for k, v in report.items()},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
