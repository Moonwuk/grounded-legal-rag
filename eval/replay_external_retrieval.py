"""Replay a supplied evaluation corpus on current search without model/API calls.

Only JSON and corpus ZIP inputs are read from --evaluation-root; external Python
is not executed. The published span-coverage definitions are reproduced here.
"""
from pathlib import Path
from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus
from psb_retrieval import Retriever, tokens, user_turns


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def covers(source, hits):
    return any(f['document'] == source['document'] and f['start'] <= source['start']
               and f['end'] >= source['end'] and source['quote'] ==
               f['text'][source['start'] - f['start']:source['end'] - f['start']] for f in hits)


def coverage(case, sources, hits):
    required = case['expected']['required_claims']
    if not required:
        return None, None
    sufficient = all(any(all(covers(sources[s], hits) for s in group)
                         for group in item['acceptable_evidence_sets']) for item in required)
    recall = sum(max(sum(covers(sources[s], hits) for s in group) / len(group)
                     for group in item['acceptable_evidence_sets']) for item in required) / len(required)
    return sufficient, recall


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation-root', type=Path, required=True)
    parser.add_argument('--corpus', choices=['synthetic', 'mixed', 'public'], required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--top-k', type=int, default=6)
    parser.add_argument('--mode', choices=['all', 'development', 'holdout'], default='all')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 40 or (args.limit is not None and args.limit <= 0):
        parser.error('top-k must be 1..40 and limit must be positive')
    base = args.evaluation_root
    archive = base / 'generated_corpora' / args.corpus / 'knowledge-base.zip'
    gold_path = base / 'gold' / (args.corpus + '.json')
    questions_path = base / 'questions' / (args.corpus + '.json')
    gold = json.loads(gold_path.read_text(encoding="utf-8-sig"))
    questions = json.loads(questions_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads((archive.parent / 'manifest.json').read_text(encoding='utf-8-sig'))
    assert digest(archive) == manifest['archive_sha256']
    assert gold['corpus_id'] == manifest['corpus_id']
    if args.mode != 'all':
        questions = [q for q in questions if (q['split'] == 'holdout') == (args.mode == 'holdout')]
    questions.sort(key=lambda q: (int(q['case_id'].rsplit('-', 1)[-1])
                                 if q['case_id'].rsplit('-', 1)[-1].isdigit() else 0, q['case_id']))
    if args.limit:
        questions = questions[:args.limit]
    started = time.monotonic()
    docs, fragments = load_corpus(archive)
    by_name = {d.name: d for d in docs}
    assert all(s['quote'] == by_name[s['document']].text[s['start']:s['end']]
               for s in gold['sources'].values())
    retriever = Retriever(docs, fragments)
    cases = {c['case_id']: c for c in gold['cases']}
    rows = []
    for q in questions:
        case = cases[q['case_id']]
        labels = {'user': 'Пользователь', 'assistant': 'Ассистент'}
        history = q.get('history', [])
        question = ('\n'.join(labels[x['role']] + ': ' + x['content'] for x in history) +
                    '\nПользователь: ' + q['question']) if history else q['question']
        turns = user_turns(question)
        query = Counter(tokens(turns[-1]))
        for turn in turns[:-1]:
            for token in tokens(turn):
                query[token] += .35
        scores = retriever._scores(query)
        rank = sorted(scores, key=lambda i: (-scores[i], fragments[i].document, fragments[i].start))
        raw = [asdict(fragments[i]) for i in rank[:10] if scores[i] > 0]
        row = {'case_id': q['case_id'], 'category': case['category'], 'split': q['split'],
               'requires_evidence': bool(case['expected']['required_claims']),
               'recall': {str(k): coverage(case, gold['sources'], raw[:k])[1] for k in (1, 5, 10)}}
        try:
            hits = [asdict(f) for f in retriever.search(question, top_k=args.top_k)]
            row.update(status='context', sufficient=coverage(case, gold['sources'], hits)[0],
                       context_fragments=len(hits), context_characters=sum(len(f['text']) for f in hits))
        except ValueError as error:
            row.update(status='guard_exception', error_code=str(error), sufficient=None)
        rows.append(row)
        if len(rows) % 100 == 0:
            print(f'completed={len(rows)}/{len(questions)}', flush=True)
    required = [r for r in rows if r['requires_evidence']]
    errors = [r for r in rows if r['status'] == 'guard_exception']
    completed = [r for r in required if r['status'] == 'context']
    summary = {'source_commit': args.source_commit, 'corpus': args.corpus, 'mode': args.mode,
               'archive_sha256': digest(archive), 'gold_sha256': digest(gold_path),
               'questions_sha256': digest(questions_path), 'top_k': args.top_k,
               'documents': len(docs), 'indexed_fragments': len(fragments),
               'questions': len(rows), 'source_spans_checked': len(gold['sources']),
               'context_success': len(rows) - len(errors), 'guard_errors': len(errors),
               'errors_by_code': dict(Counter(r['error_code'] for r in errors)),
               'required_questions': len(required), 'required_completed': len(completed),
               'required_sufficient': sum(r['sufficient'] is True for r in completed),
               'raw_recall': {str(k): {'numerator': sum(r['recall'][str(k)] for r in required),
                                      'denominator': len(required)} for k in (1, 5, 10)},
               'runtime_file_sha256': {p.name: digest(p) for p in sorted((ROOT / 'prototype').glob('*.py'))},
               'seconds': round(time.monotonic() - started, 3), 'api_calls': 0,
               'answer_metrics': 'NOT_EVALUATED: retrieval only',
               'limits': 'Reused one immutable index; original worker rebuilt it per case. Timing is not directly comparable. Gold was used only after search for span coverage; this is logical input separation, not an OS sandbox.',
               'rows': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
