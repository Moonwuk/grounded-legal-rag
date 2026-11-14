"""Estimate the regulation's judge Score (section 8) against a baseline analog.

For every question the judge sees the question, the organizer golden answer
and two answers, and rates B against A on the regulation scale (1, 0.75,
0.5, 0.25, 0). Round 1: A is the baseline, B the team answer; round 2 swaps
them and its rating is mirrored, so both rounds rate the team answer. A
fabricated fact the judge marks in the team answer in either round sets the
question to 0. Then, as in the regulation:

  MatchRate = mean s_i;  WinRate = W / (W + L), ties excluded (0.5 if none);
  Score = 0.7 * MatchRate + 0.3 * WinRate.

Questions where the judge call fails are excluded and counted.

Limits: the baseline is an analog (by default the organizer starter run on
the same questions, see evaluation/reports/starter-*/manifest.json), the
judge prompt is ours, and golden answers exist only for the demo questions
and their paraphrases. The judge is the model configured in LLM_MODEL; use a
model other than the solution model for an evaluation independent of the
generator. This is a development estimate, not the platform Score.

Usage: LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=<judge> \
  python3 -m evaluation.judge_score --corpus evaluation/corpora/demo \
    --report evaluation/reports/<team run> --baseline evaluation/reports/starter-demo/submission.csv --run-id <id>
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
from evaluation.common import EVAL, ROOT, read, write
from evaluation.judge_forms import judge

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_llm import ProviderError, env  # noqa: E402


def rows(path: Path) -> dict[str, str]:
    with path.open(encoding='utf-8-sig', newline='') as h:
        return {r['id']: r['answer'] for r in csv.DictReader(h)}


def question_score(r1: float, r2_mirrored: float, fabricated_team: bool) -> float:
    return 0.0 if fabricated_team else (r1 + r2_mirrored) / 2


def summarize(scores: list[float]) -> dict:
    wins = sum(s > 0.5 for s in scores)
    losses = sum(s < 0.5 for s in scores)
    match = sum(scores) / len(scores) if scores else None
    win = wins / (wins + losses) if wins + losses else 0.5
    return dict(judged=len(scores), wins=wins, losses=losses, ties=len(scores) - wins - losses,
                match_rate=None if match is None else round(match, 3), win_rate=round(win, 3),
                score=None if match is None else round(0.7 * match + 0.3 * win, 3))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True, help='team run directory with cases.json')
    p.add_argument('--baseline', type=Path, required=True, help='baseline submission.csv (id,answer)')
    p.add_argument('--run-id', required=True)
    a = p.parse_args()
    golden = rows(ROOT / 'organizer' / 'demo_output.csv')
    meta = read(a.corpus / 'corpus.json')
    with (a.corpus / meta['questions']).open(encoding='utf-8-sig', newline='') as h:
        questions = {r['id']: r['question'] for r in csv.DictReader(h)}
    gold_cases = {c['case_id']: c for c in read(a.corpus / 'gold' / 'cases.json')['cases']}
    baseline = rows(a.baseline)
    out, scores = [], []
    for case in read(a.report / 'cases.json'):
        cid, team = case['case_id'], case['answer']
        source = gold_cases[cid].get('paraphrase_of', cid)
        if cid not in baseline or source not in golden:
            out.append(dict(case_id=cid, judged=False, error='no_baseline_or_golden'))
            continue
        try:
            r1, _, fab_team_1 = judge(questions[cid], golden[source], baseline[cid], team)   # B = team
            r2, fab_team_2, _ = judge(questions[cid], golden[source], team, baseline[cid])   # A = team
        except (ProviderError, ValueError) as error:
            out.append(dict(case_id=cid, judged=False, error=str(error)))
            continue
        fabricated = fab_team_1 or fab_team_2
        s = question_score(r1, 1 - r2, fabricated)
        scores.append(s)
        out.append(dict(case_id=cid, judged=True, score=s, rounds=[r1, 1 - r2], fabricated_team=fabricated,
                        status=case.get('status')))
        print(cid, s, file=sys.stderr)
    summary = dict(scope='Development estimate of the regulation judge (section 8) against a baseline analog; '
                         'not the platform judge, baseline or Score.',
                   judge_model=env('LLM_MODEL', 'OPENAI_MODEL', 'GEN_MODEL'), report=a.report.name,
                   team_model=read(a.report / 'summary.json').get('model'), baseline=str(a.baseline.resolve().relative_to(ROOT))
                   if a.baseline.resolve().is_relative_to(ROOT) else a.baseline.name,
                   corpus=meta['corpus_id'], judge_failures=sum(not r['judged'] for r in out),
                   fabricated_team=sum(bool(r.get('fabricated_team')) for r in out), **summarize(scores))
    target = EVAL / 'reports' / a.run_id
    write(target / 'summary.json', summary)
    write(target / 'cases.json', out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
