"""Import the public split of LegalBench-RU as a platform-format corpus.

Source: https://huggingface.co/datasets/AlsKozlov/legalbench-ru (CC-BY-4.0,
"ru-legal contributors", v0.3). Only `split=public` records that carry a
`norm_text` are used; the holdout split stays untouched as its authors ask.

Mapping:
- knowledge base: every distinct `norm_text` and `distractor_text` as a law
  document (`законы__…`); distractors are real-looking wrong norms that the
  solution must not follow;
- question: the dataset `question` only. The `context` field is never given
  to the solution: it often names the trap or the answer;
- gold: `binary` → the answer opens with the gold «да/нет», the opposite is
  forbidden; `extraction` → the article number of `gold_norm` is cited.
  `multiple_choice`, `knowledge` and `tool-use` records are skipped.

Every record is flagged `needs_expert_review` by its authors; gold here is
generated with adversarial verification, not lawyer-annotated.

Usage:
  python3 -m evaluation.import_legalbench_ru path/to/legalbench_ru.jsonl
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import re
from pathlib import Path
from evaluation.common import EVAL,archive,digest,write

SOURCE = 'https://huggingface.co/datasets/AlsKozlov/legalbench-ru'
OUT = EVAL / 'corpora' / 'legalbench-ru'


def as_text(value):
    """`gold_norm` is a string or a list of citations."""
    return '; '.join(map(str, value)) if isinstance(value, list) else str(value or '')


def slug(text):
    text = as_text(text)
    return re.sub(r'[^0-9A-Za-zА-Яа-яЁё.]+', '_', text).strip('_')[:60] or 'норма'


def heading(text):
    """First words of a norm text ("Статья 782 ГК РФ", "ГК РФ ст.421 …")."""
    return re.split(r'[.:«]', ' '.join(text.split()), maxsplit=1)[0][:50] if text else 'норма'


def article_numbers(gold_norm):
    """Article/clause numbers of a citation such as "ГК РФ ст.782" or "ст. 30.3"."""
    return re.findall(r'ст\.?\s*(\d+(?:\.\d+)*)', as_text(gold_norm))


def build(rows):
    records = [r for r in rows if isinstance(r, dict) and r.get('split') == 'public' and r.get('norm_text')
               and r.get('answer_type') in {'binary', 'extraction'}]
    texts = {}
    def add(text, norm):
        key = ' '.join(text.split())
        if key not in texts:
            texts[key] = f'законы__{slug(norm)}_{digest(key.encode())[:6]}.txt'
        return texts[key]
    cases, questions = [], []
    for i, r in enumerate(records, 1):
        # File names come from each text's own heading, identically for real and
        # distractor norms: a name must not reveal which document is correct.
        add(r['norm_text'], heading(r['norm_text']))
        if r.get('distractor_text'):
            add(r['distractor_text'], heading(r['distractor_text']))
        cid = f'lb{i:03d}'
        questions.append((cid, r['question']))
        case = dict(case_id=cid, family=f"{r['track']}/{r['answer_type']}/{r.get('domain')}", source_task=r.get('task'),
                    allowed_statuses=['answer'], checked_by_hand=False, needs_expert_review=bool(r.get('needs_expert_review')))
        if r['answer_type'] == 'binary':
            polarity = 'да' if str(r['answer']).strip().lower().startswith('да') else 'нет'
            other = 'нет' if polarity == 'да' else 'да'
            case['required'] = [dict(id='polarity ' + polarity, kind='polarity', value=polarity)]
            case['forbidden'] = [dict(id='polarity ' + other, kind='polarity', value=other)]
        else:
            numbers = article_numbers(r.get('gold_norm'))
            if not numbers:
                continue
            case['required'] = [dict(id='article ' + numbers[0], kind='clause', any=numbers)]
            case['reference_answer'] = r['answer']
        cases.append(case)
    keep = {c['case_id'] for c in cases}
    questions = [q for q in questions if q[0] in keep]
    files = {name: text for text, name in ((k, v) for k, v in texts.items())}
    return cases, questions, files


def main():
    p = argparse.ArgumentParser(); p.add_argument('jsonl', type=Path); a = p.parse_args()
    raw = a.jsonl.read_bytes()
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    cases, questions, files = build(rows)
    (OUT / 'data').mkdir(parents=True, exist_ok=True); (OUT / 'gold').mkdir(parents=True, exist_ok=True)
    kb = archive(OUT / 'data' / 'knowledge-base.zip', files)
    buffer = io.StringIO(); w = csv.writer(buffer, lineterminator='\n'); w.writerow(['id', 'question']); w.writerows(questions)
    (OUT / 'data' / 'questions.csv').write_text(buffer.getvalue(), encoding='utf-8')
    write(OUT / 'gold' / 'cases.json', dict(version='1.0.0', corpus_id='legalbench-ru-public-grounded', source=SOURCE,
          license='CC-BY-4.0, ru-legal contributors', cases=cases))
    write(OUT / 'corpus.json', dict(corpus_id='legalbench-ru-public-grounded', knowledge_base='data/knowledge-base.zip',
          knowledge_base_sha256=kb, questions='data/questions.csv', questions_sha256=digest((OUT / 'data' / 'questions.csv').read_bytes()),
          gold='gold/cases.json', source=SOURCE, source_sha256=digest(raw), license='CC-BY-4.0',
          tuning_note='External set, not used for tuning. Gold is generated and adversarially verified, not lawyer-annotated.'))
    print(json.dumps(dict(cases=len(cases), documents=len(files)), ensure_ascii=False))


if __name__ == '__main__':
    main()
