"""A restricted answer reduced to quotes is retried with the restrictions to keep.

Combined run 9dd8e3c, LegalBench-RU (lb033, lb039, lb061, lb073 and four more):
the norm had a restriction ("только", "не вправе"); the model text did not
repeat it, so only the quotation was published (AGENTS rule 9), the verifier
found that the quotation alone does not answer the yes/no question, and the
retry, given no reason, repeated the omission: a generic refusal.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import answer_question, lost_restrictions  # noqa: E402
from psb_corpus import Fragment  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

NORM = ('Источник: Статья 21. Учебный кодекс Российской Федерации\nСтатья 21. Отказ от договора\n'
        'Заказчик вправе отказаться от исполнения договора только при условии оплаты исполнителю фактически понесённых расходов.\n')
QUESTION = 'Может ли заказчик отказаться от договора, не оплатив исполнителю понесённые расходы?'


def generate(text):
    def answer(payload):
        fid = next(e['id'] for e in payload['evidence'] if 'только при условии' in e['text'])
        return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': [], 'issue': ''}
    return answer


def verdict(approved, complete):
    return {'approved': approved, 'complete': complete, 'status': 'answer', 'answer_supported': approved,
            'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}


class RestrictionRetryTests(unittest.TestCase):
    def test_retry_names_the_lost_restrictions_and_the_kept_answer_is_published(self):
        lost = 'Нет, заказчик должен оплатить исполнителю фактически понесённые расходы.'
        kept = 'Нет: заказчик вправе отказаться только при условии оплаты исполнителю фактически понесённых расходов.'
        model = ScriptedModel([generate(lost), verdict(False, False), generate(kept), verdict(True, True)])
        with corpus({'law.txt': NORM}) as r:
            text, status = answer_question(QUESTION, r, model)
        retry = model.calls[2][1]
        self.assertEqual(retry.get('retry_reason'), 'answer_lost_restrictions')
        self.assertIn('только', retry.get('retry_restrictions', []))
        self.assertEqual(status, 'answer')
        self.assertTrue(text.startswith(kept))

    def test_lost_restrictions_lists_source_wording(self):
        source = [Fragment('f', 'd', 0, 10, 'Арендатор не вправе сдавать помещение в субаренду, за исключением случаев согласия арендодателя.', '')]
        self.assertEqual(lost_restrictions('Сдавать в субаренду нельзя.', source), ['за исключением'])
        self.assertEqual(lost_restrictions('Нельзя, за исключением случаев согласия арендодателя.', source), [])


if __name__ == '__main__':
    unittest.main()
