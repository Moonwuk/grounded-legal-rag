"""Regressions for two reproduced defects (scripted stub models, no real API).

1. Holdout diagnostics (evaluation/reports/diag-unverified-f08afbd-*): the
   model cites a provision for contrast, the verifier confirms it as authentic
   but inapplicable, and the whole correct answer became a generic refusal.
2. Demo run (evaluation/reports/demo-f744e96): answers about restricted
   provisions were published as quotes without any conclusion.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_policy import UNVERIFIED, inapplicable_only, restrictions_kept
from psb_corpus import Fragment
from test_prose_answers import run, select, confirm

# Two independent scenarios: different numbers, units, dates and clause numbers.
REVISIONS = [
    dict(files={'Договор ЛК-4-2031.txt': 'Договор № ЛК-4/2031\n5.1. Оплата производится в течение 21 рабочего дня, если акт подписан до 01.04.2031.',
                'Доп соглашение 1 к договору ЛК-4-2031.txt': 'Дополнительное соглашение к договору № ЛК-4/2031\n1. Оплата производится в течение 55 рабочих дней, если акт подписан начиная с 01.04.2031.'},
         question='Какой срок оплаты по договору ЛК-4/2031, если акт подписан 15.03.2031?', own='5.1.', other='1. Оплата',
         prose='Срок оплаты — 21 рабочий день: акт подписан до 01.04.2031, поэтому срок 55 рабочих дней из допсоглашения не применяется (п. 5.1).',
         value='21', contrast_quote='55 рабочих дней, если акт'),
    dict(files={'Регламент закупок ред 2030.txt': 'Регламент закупок, редакция 2030 года\n2.2. Закупки свыше 800 000 рублей согласует директор. Редакция действует до 09.02.2032.',
                'Регламент закупок ред 2032.txt': 'Регламент закупок, редакция 2032 года\n2.2. Закупки свыше 1 300 000 рублей согласует директор. Редакция действует с 10.02.2032.'},
         question='Закупку на 900 000 рублей проводили 05.11.2031. С какой суммы требовалось согласование директора?', own='800 000', other='1 300 000',
         prose='Согласование директора требовалось для закупок свыше 800 000 рублей; порог 1 300 000 рублей действует с 10.02.2032 и к этой закупке не применяется (п. 2.2).',
         value='800 000', contrast_quote='1 300 000 рублей согласует'),
]

def both(s):
    def model(payload):
        ids = [next(f['id'] for f in payload['evidence'] if needle in f['text']) for needle in (s['own'], s['other'])]
        return {'status': 'answer', 'answer': s['prose'], 'source_ids': ids}
    return model

def judge(inapplicable=(), unsupported=(), supported_text=True):
    def model(payload):
        claims = payload['candidate']['claims']
        bad = bool(inapplicable or unsupported)
        return {'approved': not bad, 'complete': not bad, 'status': payload['candidate']['status'], 'answer_supported': supported_text and not bad,
                'claim_checks': [{'index': i, 'supported': i not in unsupported, 'applicable': i not in inapplicable} for i in range(len(claims))]}
    return model

class ContrastProvisionTests(unittest.TestCase):
    def test_inapplicable_contrast_provision_no_longer_voids_the_answer(self):
        for s in REVISIONS:
            with self.subTest(s['question']):
                text, status, model, events = run(s['question'], [both(s), judge(inapplicable=[1]), judge()], s['files'])
                self.assertEqual(status, 'answer', text)
                self.assertTrue(text.startswith(s['prose']))
                self.assertEqual(len(model.calls), 3)
                # Re-verified candidate holds only the applicable provision.
                final = model.calls[-1][1]['candidate']
                self.assertEqual(len(final['claims']), 1)
                self.assertIn(s['value'], final['claims'][0]['text'])
                self.assertNotIn(s['contrast_quote'], final['claims'][0]['text'])
                self.assertEqual([e['reduced'] for e in events], [False, True])
                # The inapplicable document is not named as a source of the answer.
                source_line = text.split('\n')[-1]
                self.assertTrue(source_line.startswith('Источник:'), source_line)

    def test_reduced_candidate_still_needs_its_own_approval(self):
        s = REVISIONS[0]
        for second in (judge(inapplicable=[0]), judge(unsupported=[0])):
            text, status, model, _ = run(s['question'], [both(s), judge(inapplicable=[1]), second], s['files'])
            self.assertEqual((text, status), (UNVERIFIED, 'unverified'))
            self.assertEqual(len(model.calls), 3)

    def test_unconfirmed_text_falls_back_to_the_applicable_provision_only(self):
        s = REVISIONS[1]
        text, status, _, _ = run(s['question'], [both(s), judge(inapplicable=[1]), judge(supported_text=False)], s['files'])
        self.assertEqual(status, 'answer')
        self.assertNotIn(s['prose'], text); self.assertIn('800 000', text); self.assertNotIn('1 300 000', text)

    def test_unsupported_or_fully_inapplicable_selection_is_not_reduced(self):
        s = REVISIONS[0]
        for first in (judge(unsupported=[1]), judge(inapplicable=[0, 1]), judge(inapplicable=[1], unsupported=[0])):
            text, status, model, events = run(s['question'], [both(s), first, both(s), first], s['files'])
            self.assertEqual(status, 'unverified')
            self.assertTrue(all(e['reduced'] is False for e in events))

    def test_reduction_never_exceeds_the_per_question_call_limit(self):
        # Holdout 9989f40 temporal-0009: rejected for another reason, then the
        # expanded attempt found an inapplicable provision; the 5th call raised
        # question_call_budget and the answer became a technical error.
        from psb_llm import QUESTION_CALL_LIMIT
        for s in REVISIONS:
            with self.subTest(s['question']):
                text, status, model, events = run(s['question'], [both(s), judge(unsupported=[0]), both(s), judge(inapplicable=[1])], s['files'])
                self.assertEqual(status, 'unverified')
                self.assertLessEqual(len(model.calls), QUESTION_CALL_LIMIT)
                self.assertEqual([e['reduced'] for e in events], [False, False])

    def test_inapplicable_only_requires_a_complete_wellformed_verdict(self):
        c = {'status': 'answer', 'claims': [{}, {}]}
        ok = lambda a, b: {'status': 'answer', 'claim_checks': [{'index': 0, 'supported': True, 'applicable': a}, {'index': 1, 'supported': True, 'applicable': b}]}
        self.assertEqual(inapplicable_only(c, ok(True, False)), [1])
        self.assertEqual(inapplicable_only(c, ok(True, True)), [])
        self.assertEqual(inapplicable_only(c, {**ok(True, False), 'status': 'partial'}), [])
        self.assertEqual(inapplicable_only(c, {'status': 'answer', 'claim_checks': [{'index': 0, 'supported': True, 'applicable': False}]}), [])
        self.assertEqual(inapplicable_only(c, {'status': 'answer', 'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}] * 2}), [])
        self.assertEqual(inapplicable_only(c, None), [])


RESTRICTED = [
    dict(file={'Положение об отпусках.txt': '6.2. Испытание не может превышать четырёх месяцев для руководителей филиалов.'}, needle='6.2.',
         question='Какой максимальный срок испытания у руководителя филиала?',
         good='Срок испытания не может превышать четырёх месяцев для руководителей филиалов (п. 6.2).',
         bad=['Срок испытания для руководителей филиалов составляет четыре месяца и более (п. 6.2).']),
    dict(file={'Договор подряда Р-9-2032.txt': '7.4. По соглашению сторон допускается авансирование работ. Размер аванса указывается в смете.'}, needle='7.4.',
         question='Можно ли оплатить работы авансом?',
         good='Да, авансирование работ допускается по соглашению сторон; размер аванса указывается в смете (п. 7.4).',
         bad=['Да, авансирование работ допускается в любом случае (п. 7.4).']),
    dict(file={'Правила склада.txt': '3.3. Вывоз оборудования допускается только при наличии пропуска, за исключением аварийных работ.'}, needle='3.3.',
         question='Можно вывезти оборудование?',
         good='Вывоз оборудования допускается только при наличии пропуска, за исключением аварийных работ (п. 3.3).',
         bad=['Вывоз оборудования допускается при наличии пропуска (п. 3.3).', 'Вывоз оборудования допускается только при наличии пропуска (п. 3.3).']),
]

class RestrictedProvisionTests(unittest.TestCase):
    def test_conclusion_that_keeps_every_restriction_is_published_with_the_source(self):
        for s in RESTRICTED:
            with self.subTest(s['question']):
                text, status, _, events = run(s['question'], [select(s['needle'], s['good']), confirm()], s['file'])
                source = next(iter(s['file'].values()))
                self.assertEqual(status, 'answer')
                self.assertTrue(text.startswith(s['good']), text)
                self.assertIn('«' + source + '»', text)
                self.assertEqual(events[-1]['prose'], 'published')

    def test_conclusion_that_drops_a_restriction_is_not_published(self):
        for s in RESTRICTED:
            for bad in s['bad']:
                with self.subTest(bad=bad):
                    text, status, _, events = run(s['question'], [select(s['needle'], bad), confirm()], s['file'])
                    self.assertEqual(status, 'answer')
                    self.assertNotIn(bad, text)
                    self.assertIn('«' + next(iter(s['file'].values())) + '»', text)
                    self.assertEqual(events[-1]['prose'], 'source_only')

    def test_verifier_rejection_of_the_text_keeps_only_the_source(self):
        s = RESTRICTED[1]
        text, status, _, _ = run(s['question'], [select(s['needle'], s['good']), confirm(False), select(s['needle'], s['good']), confirm(False)], s['file'])
        self.assertEqual(status, 'answer'); self.assertNotIn(s['good'], text); self.assertIn('«7.4.', text)

    def test_restrictions_kept_is_per_class(self):
        f = [Fragment('i', 'd', 0, 1, 'Не вправе передавать, за исключением случаев по соглашению сторон.', '')]
        self.assertTrue(restrictions_kept('Передавать нельзя, за исключением случаев по соглашению сторон.', f))
        self.assertFalse(restrictions_kept('Передавать нельзя.', f))
        self.assertFalse(restrictions_kept('Передавать можно по соглашению сторон, за исключением отдельных случаев.', f))

if __name__ == '__main__':
    unittest.main()
