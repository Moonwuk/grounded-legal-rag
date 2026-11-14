"""A later attempt does not replace a verified answer with a poorer one.

24-question regression on 06a3dda, question N14 (deadline for returning a
security deposit that the lease does not set): the first attempt was a
partial answer whose text the verifier confirmed («the contract sets no such
deadline; п. 3.5 only provides for paying the deposit»). As a partial with a
missing document it got one expanded search; that attempt was verified too,
but its text was dropped, and the bare quotations replaced the first answer.

The expanded attempt still replaces the first one when it is at least as good:
a full answer, or a partial with published text.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_prose_answers import run  # noqa: E402

CASES = [
    dict(files={'Договор аренды Б-11-2031 Вектор.txt': 'Договор аренды № Б-11/2031\n2.1. Арендная плата составляет 310 000 рублей в месяц.\n'
                '2.4. При подписании договора Арендатор вносит гарантийный взнос в размере двух месячных платежей.\n'
                '5.2. При прекращении договора Арендатор возвращает Помещение по акту.\n'},
         question='Через сколько дней после возврата помещения по Б-11/2031 арендодатель возвращает гарантийный взнос?',
         clause='2.4.',
         text='Срок возврата гарантийного взноса договором Б-11/2031 не установлен: п. 2.4 предусматривает только его внесение при подписании договора.'),
    dict(files={'Договор хранения Х-4-2033 Опора.txt': 'Договор хранения № Х-4/2033\n3.1. Плата за хранение — 18 000 рублей в месяц.\n'
                '3.3. Поклажедатель вносит залог в размере 40 000 рублей при передаче груза.\n'},
         question='В какой срок хранитель по Х-4/2033 возвращает залог после выдачи груза?',
         clause='3.3.',
         text='Срок возврата залога договором Х-4/2033 не назван: п. 3.3 предусматривает только внесение залога 40 000 рублей при передаче груза.'),
]


def generate(clause, text):
    def model(payload):
        f = next(f for f in payload['evidence'] if f['text'].startswith(clause))
        return {'status': 'partial', 'answer': text, 'source_ids': [f['id']], 'requested_facts': ['document'], 'issue': ''}
    return model


def partial_verdict(payload):
    return {'approved': True, 'complete': False, 'status': 'partial', 'answer_supported': True,
            'claim_checks': [{'index': i, 'supported': True, 'applicable': True}
                             for i in range(len(payload['candidate']['claims']))]}


class KeepBetterAttemptTests(unittest.TestCase):
    def test_verified_text_is_not_replaced_by_bare_quotations(self):
        for case in CASES:
            with self.subTest(case['question']):
                text, status, model, events = run(case['question'], [
                    generate(case['clause'], case['text']), partial_verdict,
                    generate(case['clause'], ''), partial_verdict], case['files'])
                self.assertEqual(len(model.calls), 4)  # the expanded attempt did run
                self.assertEqual([e['prose'] for e in events], ['published', 'absent'])
                self.assertEqual(status, 'partial')
                self.assertTrue(text.startswith(case['text']), text)

    def test_expanded_attempt_with_text_still_replaces_the_first(self):
        case = CASES[0]
        better = 'Договор Б-11/2031 срока возврата гарантийного взноса не содержит; п. 2.4 предусматривает только его внесение.'
        text, status, model, events = run(case['question'], [
            generate(case['clause'], case['text']), partial_verdict,
            generate(case['clause'], better), partial_verdict], case['files'])
        self.assertEqual([e['prose'] for e in events], ['published', 'published'])
        self.assertTrue(text.startswith(better), text)


if __name__ == '__main__':
    unittest.main()
