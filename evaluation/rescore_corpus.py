"""Re-score a finished run_corpus report with the current gold and validator.

Answers are taken from <report>/cases.json; nothing calls the model. Writes
<report>/rescored.json and prints every case whose outcome changed, so each
change can be reviewed by hand before it is trusted.

Usage: python3 -m evaluation.rescore_corpus --corpus evaluation/corpora/demo evaluation/reports/<run> [...]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from evaluation.common import read, write
from evaluation.run_corpus import score, summarize


def rescore(corpus, report):
    cases = {c['case_id']: c for c in read(Path(corpus) / 'gold' / 'cases.json')['cases']}
    old = {r['case_id']: r for r in read(Path(report) / 'cases.json')}
    gold = {cid: cases[cid] for cid in old}
    new = score(gold, {cid: r['answer'] for cid, r in old.items()})
    changed = [dict(case_id=r['case_id'], before=old[r['case_id']]['outcome'], after=r['outcome'],
                    failures=r['failures'], not_evaluated=r['not_evaluated']) for r in new
               if r['outcome'] != old[r['case_id']]['outcome']]
    summary = summarize(new)
    write(Path(report) / 'rescored.json', dict(summary=summary, changed=changed, cases=new))
    return summary, changed


def main():
    p = argparse.ArgumentParser(); p.add_argument('--corpus', required=True); p.add_argument('reports', nargs='+')
    a = p.parse_args()
    for report in a.reports:
        summary, changed = rescore(a.corpus, report)
        print(json.dumps(dict(report=Path(report).name, passed=summary['passed'], total=summary['total'],
                              changed=changed), ensure_ascii=False))


if __name__ == '__main__':
    main()
