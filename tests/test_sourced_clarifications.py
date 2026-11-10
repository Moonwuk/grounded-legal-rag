"""Clarifications may cite the condition requiring a missing user fact."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from test_prose_answers import run, select, confirm
from test_audit_fixes import verdict

def exchange(generate, verify=None):
    verify = confirm() if verify is None else verify
    def reply(payload):
        return verify(payload) if 'candidate' in payload else generate(payload)
    return [reply] * 4


class SourcedClarifications(unittest.TestCase):
    def test_clarification_can_cite_the_condition_it_explains(self):
        source = ('2.1. Новый адрес применяется к партиям, спецификации на которые '
                  'подписаны после 17 июня 2035 года.')
        prose = ('Какова дата подписания спецификации? Новый адрес применяется к спецификациям '
                 'после 17 июня 2035 года (п. 2.1).')
        text, status, model, _ = run('Куда везти груз по договору?',
            exchange(select('2.1.', prose, status='clarify', requested_facts=['specification_date'])),
            {'Договор.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertEqual(text, prose + '\nИсточник: Договор, п. 2.1.')
        self.assertEqual(model.calls[1][1]['rendered_answer'], text)

    def test_protected_condition_is_kept_in_a_source_backed_clarification(self):
        source = '2.1. Вывоз оборудования допускается только при наличии письменного согласия собственника.'
        false_text = 'Вывоз оборудования допускается без согласия. Когда планируется вывоз?'
        text, status, _, _ = run('Можно вывезти оборудование?',
            exchange(select('2.1.', false_text, status='clarify', requested_facts=['facts'])),
            {'Положение.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertNotIn(false_text, text)
        self.assertIn('условия', text)
        self.assertIn('«' + source + '» [1]', text)
        self.assertIn('[1] Положение.', text)

    def test_empty_fact_code_asks_about_the_cited_condition_not_an_unrelated_contract(self):
        source = '1.1. Вывоз оборудования допускается только при наличии письменного разрешения собственника.'
        response = select('1.1.', 'Получено ли письменное разрешение?', status='clarify', requested_facts=[])
        text, status, _, _ = run('Что нужно уточнить перед вывозом оборудования?', exchange(response),
                                 {'Порядок вывоза.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertIn('приведённые ниже условия', text)
        self.assertNotIn('договор, контрагента', text)
        self.assertIn(source, text)

    def test_changed_number_in_clarification_falls_back_to_question_and_source(self):
        source = '2.1. Срок оплаты составляет 37 календарных дней с даты получения накладной.'
        false_text = 'Уточните дату накладной, поскольку оплатить нужно за 93 дня (п. 2.1).'
        response = select('2.1.', false_text, status='clarify', requested_facts=['event_date'])
        text, status, _, _ = run('До какого числа оплатить по договору?',
                                  exchange(response), {'Договор.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertNotIn('93', text)
        self.assertIn('дата', text)
        self.assertIn(source, text)

    def test_missing_prose_verdict_does_not_publish_the_clarification_draft(self):
        source = '2.1. Оплата производится в течение 37 дней с даты накладной.'
        draft = 'Какова дата накладной? До оплаты предусмотрено 37 дней (п. 2.1).'
        response = select('2.1.', draft, status='clarify', requested_facts=['event_date'])
        text, status, _, _ = run('Когда оплатить по договору?',
                                  exchange(response, verdict), {'Договор.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertNotIn(draft, text)
        self.assertIn(source, text)

    def test_clarification_without_sources_still_uses_fixed_application_wording(self):
        false_text = 'По закону аренду можно не платить. Назовите договор.'
        def response(payload):
            return {'status': 'clarify', 'answer': false_text, 'source_ids': [], 'requested_facts': ['contract']}
        text, status, _, _ = run('Какой договор применить?', [response, confirm()])
        self.assertEqual(status, 'clarify')
        self.assertNotIn('аренду можно не платить', text)
        self.assertIn('номер договора', text)

    def test_missing_contract_request_can_ask_for_its_text(self):
        def response(payload):
            return {'status': 'clarify', 'answer': 'Предоставьте отсутствующий договор.',
                    'source_ids': [], 'requested_facts': ['contract']}
        text, status, _, _ = run('Моего договора в базе нет. Какой в нём адрес доставки?', exchange(response))
        self.assertEqual(status, 'clarify')
        self.assertIn('номер договора', text)
        self.assertIn('текст', text)

    def test_rejected_prose_keeps_the_cited_condition(self):
        source = '2.1. Оплата производится в течение 37 дней с даты накладной.'
        draft = 'Какова дата накладной? Оплата возможна исключительно за 37 дней (п. 2.1).'
        response = select('2.1.', draft, status='clarify', requested_facts=['event_date'])
        text, status, _, _ = run('Когда оплатить по договору?',
                                  exchange(response, confirm(False)), {'Договор.txt': source})
        self.assertEqual(status, 'clarify')
        self.assertNotIn(draft, text)
        self.assertIn(source, text)


if __name__ == '__main__':
    unittest.main()
