"""Paraphrased retrieval questions for eval/cases.json (development set).

A model rewrites each question in everyday words, keeping names, numbers and
dates, and avoiding the content words of the provisions the answer needs.
This measures retrieval when the user's wording differs from the document.
The output is a development measurement set: the questions derive from cases
that were used for tuning, and the model writing them is the solution model.

Usage (key only through the environment):
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... python3 -m evaluation.make_paraphrases
"""
from __future__ import annotations
import json
import re
import sys
from evaluation.common import EVAL, ROOT, write

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_llm import ProxyClient  # noqa: E402

PROMPT = """Перефразируй вопрос пользователя юридическому ассистенту так, как его
задал бы сотрудник своими словами. Сохрани смысл, названия организаций, номера
договоров, суммы и даты. Не используй слова из списка avoid и однокоренные с ними,
если их можно заменить синонимом или описанием. Не добавляй новых условий.
Верни только JSON: {"paraphrases": ["вариант 1", "вариант 2"]}."""
STOP = set('и в во на по с со у к из за от до для не ли как что это при или его ее их'.split())


def avoid_words(quotes):
    words = re.findall(r'[а-яё]{5,}', ' '.join(quotes).casefold())
    return sorted({w for w in words if w not in STOP})[:40]


def main():
    import time
    cases = json.loads((ROOT / 'eval' / 'cases.json').read_text(encoding='utf-8'))['cases']
    rows = []
    for case in cases:
        if not case['required_evidence']:
            continue
        client = ProxyClient(time.monotonic() + 120)
        value = client.complete(PROMPT, {'question': case['question'],
                                         'avoid': avoid_words(e['quote'] for e in case['required_evidence'])})
        options = [p for p in value.get('paraphrases', []) if isinstance(p, str) and 10 <= len(p) <= 600][:2]
        for i, text in enumerate(options):
            rows.append(dict(id=f"{case['id']}-p{i + 1}", source_case=case['id'], question=text,
                             required_evidence=case['required_evidence']))
        print(case['id'], len(options), file=sys.stderr)
    write(EVAL / 'questions' / 'paraphrases.json', dict(
        version='1.0.0', source='eval/cases.json', generator='solution model, prompt in evaluation/make_paraphrases.py',
        note='Development measurement set; derived from tuned cases.', questions=rows))
    print(json.dumps(dict(questions=len(rows)), ensure_ascii=False))


if __name__ == '__main__':
    main()
