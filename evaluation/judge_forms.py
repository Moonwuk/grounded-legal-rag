"""Compare two forms of the same answers with an LLM judge (regulation, section 8).

Full form: the published answer (model conclusion, verbatim provisions «…» [n],
application lines, source line). Compact form: the same answer without the
verbatim provisions and their reference lines; an answer that has no model
conclusion (quotes or application text only) is the same in both forms and
is not judged.

The judge sees the question, the organizer golden answer and answers A and
B, and rates B against A on the regulation scale (1, 0.75, 0.5, 0.25, 0);
each question is judged twice with A and B swapped, as on the platform. A
fabricated fact marked by the judge sets the score of that form to 0.

The judge here is the solution model: a development measurement, not the
platform judge and not an independent evaluation.

Usage: LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  python3 -m evaluation.judge_forms --corpus evaluation/corpora/demo --report evaluation/reports/<run> --run-id <id>
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from evaluation.common import EVAL, ROOT, read, write
from evaluation.validators.elements import APPLICATION_LINES

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_llm import ProviderError, ProxyClient  # noqa: E402

PROMPT = """Ты судья качества ответов юридического ассистента банка. Тебе даны вопрос,
эталонный ответ (golden) и два ответа: A и B. Сравни B с A, ориентируясь на
эталон: правильность и полнота вывода, существенные условия и исключения,
ссылки на положения, ясность и краткость для юриста. Выдуманный факт (норма,
число, документ, которых нет в эталоне и которые ему противоречат) — грубая
ошибка. Верни только JSON:
{"score": 1|0.75|0.5|0.25|0, "fabricated_a": true|false, "fabricated_b": true|false}
где score: 1 — B значительно лучше A, 0.75 — немного лучше, 0.5 — сопоставимы,
0.25 — немного хуже, 0 — значительно хуже."""
SCORES = {1, 0.75, 0.5, 0.25, 0}


def compact(answer: str) -> str:
    """The answer without verbatim provisions and their numbered reference lines."""
    lines = [line for line in answer.splitlines() if line.strip()]
    if not lines or lines[0].lstrip().startswith('«') or lines[0].lstrip().startswith(APPLICATION_LINES):
        return answer
    kept = [line for line in lines if not re.match(r'\s*«', line) and not re.match(r'\s*\[\d+\]', line)]
    # Numbered reference lines ("[1], [2] Договор …") become one source line.
    names = list(dict.fromkeys(re.sub(r'^\s*(?:\[\d+\],?\s*)+', '', line).rstrip('.')
                               for line in lines if re.match(r'\s*\[\d+\]', line)))
    if names and not any(line.startswith('Источник') for line in kept):
        kept.append(('Источник: ' if len(names) == 1 else 'Источники: ') + '; '.join(names) + '.')
    text = '\n'.join(re.sub(r'\s*\[\d+\](?:,\s*\[\d+\])*', '', line) for line in kept)
    return text if text.strip() else answer


def judge(question, golden, a, b):
    value = ProxyClient(time.monotonic() + 120).complete(PROMPT, {'question': question, 'golden': golden, 'A': a, 'B': b})
    score = value.get('score')
    if score not in SCORES:
        raise ValueError('judge_score')
    return float(score), bool(value.get('fabricated_a')), bool(value.get('fabricated_b'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    with (ROOT / 'organizer' / 'demo_output.csv').open(encoding='utf-8-sig', newline='') as h:
        golden = {r['id']: r['answer'] for r in csv.DictReader(h)}
    meta = read(a.corpus / 'corpus.json')
    with (a.corpus / meta['questions']).open(encoding='utf-8-sig', newline='') as h:
        questions = {r['id']: r['question'] for r in csv.DictReader(h)}
    gold_cases = {c['case_id']: c for c in read(a.corpus / 'gold' / 'cases.json')['cases']}
    rows = []
    for case in read(a.report / 'cases.json'):
        cid, full = case['case_id'], case['answer']
        short = compact(full)
        if short == full:
            rows.append(dict(case_id=cid, judged=False))
            continue
        source = gold_cases[cid].get('paraphrase_of', cid)
        try:
            r1, fab_full_1, fab_short_1 = judge(questions[cid], golden[source], full, short)   # B = compact
            r2, fab_short_2, fab_full_2 = judge(questions[cid], golden[source], short, full)   # A = compact
        except (ProviderError, ValueError) as error:
            rows.append(dict(case_id=cid, judged=False, error=str(error)))
            continue
        compact_score = (r1 + (1 - r2)) / 2
        fabricated = dict(full=fab_full_1 or fab_full_2, compact=fab_short_1 or fab_short_2)
        if fabricated['compact'] and not fabricated['full']:
            compact_score = 0.0
        elif fabricated['full'] and not fabricated['compact']:
            compact_score = 1.0
        rows.append(dict(case_id=cid, judged=True, compact_vs_full=compact_score, rounds=[r1, 1 - r2],
                         fabricated=fabricated, full_words=len(full.split()), compact_words=len(short.split())))
        print(cid, compact_score, file=sys.stderr)
    judged = [r for r in rows if r['judged']]
    wins = sum(r['compact_vs_full'] > 0.5 for r in judged)
    losses = sum(r['compact_vs_full'] < 0.5 for r in judged)
    summary = dict(scope='Development comparison with the solution model as judge; not the platform judge or Score.',
                   report=a.report.name, corpus=meta['corpus_id'], judged=len(judged), same_form=len(rows) - len(judged),
                   mean_compact_vs_full=round(sum(r['compact_vs_full'] for r in judged) / len(judged), 3) if judged else None,
                   compact_wins=wins, compact_losses=losses, ties=len(judged) - wins - losses)
    out = EVAL / 'reports' / a.run_id
    write(out / 'summary.json', summary)
    write(out / 'cases.json', rows)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
