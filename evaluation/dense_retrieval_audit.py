"""Evidence recall with lexical search only vs lexical + dense candidates.

Runs on the organizer base with eval/cases.json questions and their
paraphrases (evaluation/questions/paraphrases.json). The embedding endpoint is
the configured proxy (LLM_BASE_URL, LLM_API_KEY, EMB_MODEL), as on the
platform. Measures retrieval coverage only, not answers or the Score.

Usage: LLM_BASE_URL=... LLM_API_KEY=... EMB_MODEL=... python3 -m evaluation.dense_retrieval_audit
"""
from __future__ import annotations
import json
import sys
import time
from evaluation.common import EVAL, ROOT, write

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus, norm  # noqa: E402
from psb_llm import EmbeddingClient  # noqa: E402
from psb_retrieval import Retriever  # noqa: E402


def recall(retriever, questions, expanded):
    found = total = complete = 0
    misses = []
    for q in questions:
        hits = retriever.search(q['question'], expanded=expanded)
        texts = {}
        for f in sorted(hits, key=lambda f: f.start):
            texts[f.document] = texts.get(f.document, '') + ' ' + norm(f.text)
        ok = [norm(e['quote']) in texts.get(e['document'], '') for e in q['required_evidence']]
        found += sum(ok); total += len(ok); complete += all(ok)
        if not all(ok):
            misses.append(q['id'])
    return dict(span_recall=round(found / total, 4), questions_complete=f'{complete}/{len(questions)}', misses=misses,
                context_characters=None)


def context(retriever, questions):
    sizes = sorted(sum(len(f.text) for f in retriever.search(q['question'])) for q in questions)
    return dict(median=sizes[len(sizes) // 2], maximum=sizes[-1])


def main():
    docs, frags = load_corpus(ROOT / 'organizer' / 'knowledge-base.zip')
    lexical, hybrid = Retriever(docs, frags), Retriever(docs, frags)
    started = time.monotonic()
    status = hybrid.enable_dense(EmbeddingClient(time.monotonic() + 900), time.monotonic() + 600)
    index_seconds = round(time.monotonic() - started, 1)
    original = [dict(id=c['id'], question=c['question'], required_evidence=c['required_evidence'])
                for c in json.loads((ROOT / 'eval' / 'cases.json').read_text(encoding='utf-8'))['cases'] if c['required_evidence']]
    paraphrases = json.loads((EVAL / 'questions' / 'paraphrases.json').read_text(encoding='utf-8'))['questions']
    report = dict(scope='Retrieval coverage on the organizer base; development questions. Not answer accuracy, not the Score.',
                  dense_status=status, index_seconds=index_seconds, fragments=len(frags))
    for name, questions in (('original', original), ('paraphrases', paraphrases)):
        for mode in (False, True):
            key = f"{name}{'_expanded' if mode else ''}"
            report[key] = dict(lexical=recall(lexical, questions, mode), hybrid=recall(hybrid, questions, mode))
        report[name + '_context'] = dict(lexical=context(lexical, questions), hybrid=context(hybrid, questions))
    write(EVAL / 'reports' / 'dense-retrieval-audit.json', report)
    print(json.dumps({k: (v if not isinstance(v, dict) or 'lexical' not in v else
                          {m: {x: y for x, y in v[m].items() if x != 'misses'} for m in v}) for k, v in report.items()},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
