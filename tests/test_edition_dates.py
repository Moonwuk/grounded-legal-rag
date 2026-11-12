"""Deterministic check of the edition in force on the event date.

The verifier is a model; it may approve an answer built only on an edition
that was not in force on the date the user named. When the event date is
unambiguous and every selected provision states its validity, the
application rejects such an answer whatever the verdict says.
"""
from pathlib import Path
import datetime
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_corpus import load_corpus  # noqa: E402
from psb_policy import answer_question  # noqa: E402
from psb_retrieval import Retriever, event_interval  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

QUESTION = 'Договор на 12 млн рублей заключали в августе 2024 года. Нужно ли было одобрение генерального директора?'


def pick(payload, edition, marker='2.4.'):
    return next(e['id'] for e in payload['evidence'] if edition in e['document'] and e['text'].startswith(marker))


def selection(*editions, text='Нет, одобрение генерального директора требуется для договоров свыше 15 000 000 рублей (п. 2.4).'):
    def generate(payload):
        return {'status': 'answer', 'answer': text, 'source_ids': [pick(payload, e) for e in editions],
                'requested_facts': [], 'issue': ''}
    return generate


def verdict(count):
    return {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
            'claim_checks': [{'index': i, 'supported': True, 'applicable': True} for i in range(count)]}


class EditionDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs, frags = load_corpus(ROOT / 'organizer/knowledge-base.zip')
        cls.r = Retriever(docs, frags)

    def test_answer_from_an_edition_not_yet_in_force_is_rejected_despite_approval(self):
        # August 2024: the 2025 edition (in force from 01.03.2025) does not apply.
        model = ScriptedModel([selection('ред 2025'), verdict(1),
                               selection('ред 2023', text='Да, договоры свыше 10 000 000 рублей подлежат одобрению генеральным директором (п. 2.4).'),
                               verdict(1)])
        text, status = answer_question(QUESTION, self.r, model)
        self.assertEqual(status, 'answer')
        self.assertIn('10 000 000', text)
        self.assertEqual(model.calls[2][1].get('retry_reason'), 'inapplicable_edition')

    def test_both_editions_as_contrast_are_not_rejected(self):
        model = ScriptedModel([selection('ред 2023', 'ред 2025', text='Да: в августе 2024 года действовала редакция 2023 года, '
                               'по ней договоры свыше 10 000 000 рублей одобряет генеральный директор (п. 2.4); '
                               'порог 15 000 000 рублей действует с 01.03.2025.'), verdict(2)])
        _, status = answer_question(QUESTION, self.r, model)
        self.assertEqual(status, 'answer')
        self.assertEqual(len(model.calls), 2)

    def test_without_an_event_date_nothing_is_decided(self):
        model = ScriptedModel([selection('ред 2025'), verdict(1)])
        _, status = answer_question('Нужно ли одобрение генерального директора для договора на 12 млн рублей?', self.r, model)
        self.assertEqual(status, 'answer')
        self.assertEqual(len(model.calls), 2)

    def test_event_dates(self):
        day = datetime.date
        self.assertEqual(event_interval(QUESTION), (day(2024, 8, 1), day(2024, 8, 31)))
        self.assertEqual(event_interval('Акт подписан 2031-07-02. Какой срок? Сейчас декабрь 2031 года.'),
                         (day(2031, 7, 2), day(2031, 7, 2)))
        self.assertEqual(event_interval('Акт от 3 мая 2030 г.: какой срок оплаты?'), None)  # document reference
        self.assertIsNone(event_interval('Акт подписан 01.03.2030, спецификация 05.03.2030. Что применяется?'))
        self.assertIsNone(event_interval('Сейчас декабрь 2031 года. Какой срок оплаты?'))
        self.assertIsNone(event_interval('Акт подписан 31.02.2030.'))
        self.assertEqual(event_interval('Пользователь: Акт подписали 3 мая 2030 г.\nАссистент: Уточните объект.\nПользователь: КТ-9/2030'),
                         (day(2030, 5, 3), day(2030, 5, 3)))

    def test_provision_level_dates_and_laws(self):
        files = {
            'a.txt': 'ДОГОВОР № КТ-9/2030\nСрок оплаты составляет 30 рабочих дней; событие отсчёта: подписание акта до 2030-07-02 (не включая эту дату).\n',
            'b.txt': 'ДОПОЛНЕНИЕ № КТ-9/2030\nСрок оплаты составляет 60 рабочих дней; событие отсчёта: подписание акта начиная с 2030-07-02 включительно.\n',
            'c.txt': 'Источник: Статья 5. Налоговый кодекс Российской Федерации\nСтатья 5. Положения применяются начиная с 1 января 2031 года.\n',
        }
        with corpus(files) as r:
            by_doc = {f.document: r.validity(f) for f in r.fragments if 'Срок' in f.text or 'Статья 5.' in f.text}
        self.assertEqual(by_doc['a.txt'], (None, datetime.date(2030, 7, 2)))
        self.assertEqual(by_doc['b.txt'], (datetime.date(2030, 7, 2), None))
        self.assertEqual(by_doc['c.txt'], (None, None))


if __name__ == '__main__':
    unittest.main()
