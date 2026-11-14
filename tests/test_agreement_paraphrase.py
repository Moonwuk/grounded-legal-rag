"""A paraphrased agreement must preserve the permitted operation and parties."""
from contextlib import redirect_stderr
from pathlib import Path
import io
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_corpus import Fragment
from psb_policy import answer_structured, lost_restrictions, prose_scope_safe, restrictions_kept
from test_audit_fixes import corpus
from test_baseline import ScriptedModel


PAYMENT = '7.4. По соглашению сторон допускается предоплата. Размер предоплаты указывается в счёте.'
SELECTED = [Fragment('f', 'Условия.txt', 0, 200, PAYMENT, '')]


class AgreementParaphraseTests(unittest.TestCase):
    def test_agreed_operation_is_kept_and_published_without_retry(self):
        text = ('Да, оборудование можно оплатить авансом, если стороны согласуют предоплату; '
                'её размер указывается в счёте (п. 7.4).')
        self.assertTrue(restrictions_kept(text, SELECTED))
        self.assertEqual(lost_restrictions(text, SELECTED), [])

        def response(payload):
            fid = next(f['id'] for f in payload['evidence'] if f['text'].startswith('7.4.'))
            return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': []}

        with corpus({'Условия.txt': PAYMENT}) as retriever:
            model = ScriptedModel([response, response])
            with redirect_stderr(io.StringIO()):
                result = answer_structured('Допускается ли предоплата оборудования?', retriever, model, verify=False)
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(text))
        self.assertEqual(len(model.calls), 1)

    def test_equivalence_is_not_specific_to_payment(self):
        selected = [Fragment('g', 'Условия.txt', 0, 100,
                             '8.2. По соглашению сторон разрешается разгрузка контейнера.', '')]
        self.assertTrue(restrictions_kept('Разгрузка возможна, если стороны согласуют разгрузку контейнера.', selected))
        self.assertEqual(lost_restrictions('Разгрузка возможна, если стороны согласуют разгрузку контейнера.', selected), [])

    def test_unilateral_or_no_agreement_payment_stays_blocked(self):
        for text in ('Аванс можно перечислить односторонне, без согласия поставщика.',
                     'Аванс возможен, если стороны не согласуют предоплату.',
                     'Аванс возможен, если покупатель согласует предоплату.',
                     'Аванс можно перечислить без согласия. Если стороны согласуют предоплату, сумма не изменится.',
                     'Аванс возможен даже если стороны согласуют предоплату.'):
            with self.subTest(text=text):
                self.assertFalse(restrictions_kept(text, SELECTED))
                self.assertIn('по соглашению', lost_restrictions(text, SELECTED))

    def test_agreement_on_another_operation_does_not_qualify_payment(self):
        selected = [Fragment('f', 'Условия.txt', 0, 200,
                             PAYMENT + ' График поставок устанавливает покупатель.', '')]
        for text in ('Предоплата допускается. Если стороны согласуют график поставок, он изменится.',
                     'Аванс возможен, если стороны согласуют разгрузку.',
                     'Предоплата допускается всегда. Если стороны согласуют предоплату, график изменится.',
                     'Да, договор можно расторгнуть, если стороны согласуют предоплату (п. 7.4).',
                     'Да, срок поставки можно перенести, если стороны согласуют предоплату (п. 7.4).',
                     'Отмена предоплаты возможна, если стороны согласуют предоплату.'):
            with self.subTest(text=text):
                self.assertFalse(restrictions_kept(text, selected))
        unloading = [Fragment('g', 'Условия.txt', 0, 100,
                             '8.2. По соглашению сторон разрешается разгрузка контейнера.', '')]
        self.assertFalse(restrictions_kept(
            'Разгрузка вагона возможна, если стороны согласуют разгрузку контейнера.', unloading))
        equipment = [Fragment('e', 'Условия.txt', 0, 100,
                              '7.4. По соглашению сторон допускается предоплата оборудования.', '')]
        self.assertFalse(restrictions_kept(
            'Да, штраф можно оплатить авансом, если стороны согласуют предоплату оборудования (п. 7.4).', equipment))
        self.assertTrue(restrictions_kept(
            'Да, оборудование можно оплатить авансом, если стороны согласуют предоплату оборудования (п. 7.4).', equipment))

    def test_unrelated_clause_does_not_supply_permitted_subject(self):
        for source in ('7.4. По соглашению сторон допускается разгрузка; предоплата допускается без ограничений.',
                       '7.4. По соглашению сторон допускается разгрузка, а предоплата не допускается.',
                       '7.4. По соглашению сторон допускается разгрузка. Предоплата устанавливается поставщиком.'):
            selected = [Fragment('f', 'Условия.txt', 0, 200, source, '')]
            with self.subTest(source=source):
                self.assertFalse(restrictions_kept('Предоплата возможна, если стороны согласуют предоплату.', selected))

    def test_unrelated_exclusive_claim_is_still_rejected(self):
        text = ('Предоплата возможна, если стороны согласуют предоплату. '
                'График изменяется только по соглашению сторон.')
        self.assertFalse(prose_scope_safe(text, SELECTED))


if __name__ == '__main__':
    unittest.main()
