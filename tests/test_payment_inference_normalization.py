"""Remove only a dangling connector of an already supported payment inference."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import added_assertions_safe, _without_payment_absence
from test_one_call_answers import one_call, answer

PROVISION = ('7.3. Цена оборудования указывается в Смете и включает стоимость '
             'погрузки и перевозки до склада Заказчика.')
FILES = {'Договор.txt': 'Договор оборудования\n' + PROVISION}
SELECTED = [Fragment('a', 'Договор.txt', 0, len(PROVISION), PROVISION, '')]
PREFIX = ('Цена оборудования указывается в Смете и включает стоимость '
          'погрузки и перевозки до склада Заказчика')


class PaymentInferenceNormalizationTests(unittest.TestCase):
    def test_supported_inference_keeps_the_source_destination_exact(self):
        for conjunction in (', поэтому', ', значит', ' и', ','):
            with self.subTest(conjunction=conjunction):
                text = PREFIX + ' (п. 7.3)' + conjunction + ' отдельно их оплачивать не нужно.'
                self.assertTrue(added_assertions_safe(text, SELECTED))

    def test_pipeline_publishes_the_direct_answer_without_an_extra_call(self):
        text = 'Да. ' + PREFIX + ' (п. 7.3), поэтому отдельно их оплачивать не нужно.'
        result, model, _ = one_call('Погрузка и перевозка уже входят в цену?',
                                   [answer('7.3.', text)] * 2, FILES)
        self.assertTrue(result['text'].startswith(text), result['text'])
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 1)

    def test_wrong_destination_is_still_rejected(self):
        text = PREFIX.replace('Заказчика', 'Исполнителя') + ', поэтому отдельно их оплачивать не нужно.'
        self.assertFalse(added_assertions_safe(text, SELECTED))

    def test_missing_or_changed_condition_is_still_rejected(self):
        source = [Fragment('b', 'Договор.txt', 0, 1,
                  PROVISION[:-1] + ' при наличии пропуска.', '')]
        for text in (PREFIX + ', поэтому отдельно их оплачивать не нужно.',
                     PREFIX + ' при отсутствии пропуска, поэтому отдельно их оплачивать не нужно.'):
            with self.subTest(text=text):
                self.assertFalse(added_assertions_safe(text, source))

    def test_unsupported_absence_or_extra_ordinary_clause_is_not_erased(self):
        for text in (PREFIX + ', поэтому отдельно ремонт оплачивать не нужно.',
                     PREFIX + ', поэтому отдельно их оплачивать не нужно, а ремонт также бесплатный.',
                     PREFIX + ', поэтому отдельно их оплачивают.',
                     PREFIX.replace('включает', 'не включает') + ', поэтому отдельно их оплачивать не нужно.'):
            with self.subTest(text=text):
                self.assertFalse(added_assertions_safe(text, SELECTED))

    def test_nonpayment_sentences_are_left_unchanged(self):
        for text in (PREFIX + ', поэтому нужна доверенность.',
                     PREFIX + ', и право собственности переходит к Заказчику.',
                     'Товар доставляется до склада компании.'):
            with self.subTest(text=text):
                self.assertEqual(_without_payment_absence(text), text)


if __name__ == '__main__':
    unittest.main()
