"""Elliptical dialogue versions of eval/cases.json questions (development set).

The model writes a short dialogue whose last user turn cannot be understood
without the history ("А по нему за сколько дней?") but asks the same thing as
the source question; the gold provisions of the source case stay the gold.
Measures retrieval with dialogue history. The writer is the solution model.

Usage: LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... python3 -m evaluation.make_dialogs
"""
from __future__ import annotations
import json
import sys
import time
from evaluation.common import EVAL, ROOT, write

sys.path.insert(0, str(ROOT / 'prototype'))
from psb_llm import ProviderError, ProxyClient  # noqa: E402

PROMPT = """Составь короткий диалог пользователя с юридическим ассистентом по исходному
вопросу. Первая реплика пользователя называет документ, контрагента или тему, но
спрашивает о другом аспекте. Ответ ассистента — одно короткое предложение без
чисел и норм. Последняя реплика пользователя по смыслу равна исходному вопросу,
но без истории непонятна: используй «он», «по нему», «там», «а если», не
повторяй название документа и контрагента. Верни только JSON:
{"turns": ["реплика пользователя", "реплика ассистента", "последняя реплика пользователя"]}"""


def main():
    cases = json.loads((ROOT / 'eval' / 'cases.json').read_text(encoding='utf-8'))['cases']
    rows = []
    for case in cases:
        if not case['required_evidence'] or case['question'].startswith('Пользователь:'):
            continue
        try:
            value = ProxyClient(time.monotonic() + 120).complete(PROMPT, {'question': case['question']})
        except ProviderError:
            continue
        turns = value.get('turns') if isinstance(value, dict) else None
        if not (isinstance(turns, list) and len(turns) == 3 and all(isinstance(t, str) and 3 <= len(t) <= 400 for t in turns)):
            continue
        question = f'Пользователь: {turns[0]}\nАссистент: {turns[1]}\nПользователь: {turns[2]}'
        rows.append(dict(id=case['id'] + '-d', source_case=case['id'], question=question, required_evidence=case['required_evidence']))
        print(case['id'], file=sys.stderr)
    write(EVAL / 'questions' / 'dialogs.json', dict(version='1.0.0', source='eval/cases.json',
          generator='solution model, prompt in evaluation/make_dialogs.py', note='Development measurement set; derived from tuned cases.',
          questions=rows))
    print(json.dumps(dict(questions=len(rows)), ensure_ascii=False))


if __name__ == '__main__':
    main()
