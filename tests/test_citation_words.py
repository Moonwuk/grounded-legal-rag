"""A reference to the basis is not an added assertion.

Demo run 436ae8f, question 12 (probation and labour rules): the model text
ended with «(статья 70 ТК РФ)»; the barrier against unsupported additions
read «актов, содержащих …» as a statement about the contents of a document and
required every word of the sentence, «статья» included, to be in the source.
The same text with «(ст. 70 ТК РФ)» passed. The text was rejected twice and
only the quotation was published.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import added_assertions_safe  # noqa: E402

SOURCE = [Fragment('f', 'law.txt', 0, 200, 'В период стажировки на работника распространяются требования локальных актов, '
                   'содержащих правила внутреннего распорядка.', '')]
BODY = 'Да. В период стажировки на работника распространяются требования локальных актов, содержащих правила внутреннего распорядка'


class CitationWordsTests(unittest.TestCase):
    def test_reference_wordings_are_equivalent(self):
        for reference in ('(ст. 44 Учебного кодекса)', '(статья 44 ТК РФ)', '(статьи 44 Учебного кодекса РФ)',
                          '(пункт 4.2 положения)', '(п. 4.2)', '(подпункт 3 пункта 2 статьи 44 ГК РФ)', '(часть 2 статьи 44 КоАП РФ)'):
            with self.subTest(reference):
                self.assertTrue(added_assertions_safe(f'{BODY} {reference}.', SOURCE))

    def test_unsupported_record_claims_are_still_rejected(self):
        for text in ('Акт содержит подпись директора (статья 44 ТК РФ).',
                     'В период стажировки на работника распространяются требования локальных актов, содержащих премиальные выплаты (статья 44).',
                     'Протокол фиксирует отказ работника (пункт 4.2).'):
            with self.subTest(text):
                self.assertFalse(added_assertions_safe(text, SOURCE))


if __name__ == '__main__':
    unittest.main()


class InclusionImpliesNoSeparatePaymentTests(unittest.TestCase):
    """Demo question 16 (7 of 9 stored runs published only the quotation): «стоимость
    упаковки и доставки включена в цену, поэтому отдельно их оплачивать не нужно»
    was rejected by the barrier against invented absences, although «отдельно не
    оплачивается» follows from «цена включает стоимость … » for the same items."""

    SOURCE = [Fragment('f', 'contract.txt', 0, 200, '5.3. Стоимость работ включает монтаж оборудования и пусконаладку на объекте Заказчика.', '')]

    def test_items_included_in_the_price_are_not_paid_separately(self):
        for text in ('Да, монтаж оборудования и пусконаладка включены в стоимость работ, поэтому отдельно их оплачивать не нужно.',
                     'Монтаж оборудования входит в стоимость работ и отдельно не оплачивается (п. 5.3).',
                     'Нет, пусконаладка на объекте Заказчика включена в стоимость работ; отдельной оплаты не требуется.'):
            with self.subTest(text):
                self.assertTrue(added_assertions_safe(text, self.SOURCE))

    def test_items_not_named_in_the_price_clause_still_fail(self):
        for text in ('Доставка оборудования включена в стоимость работ, отдельно её оплачивать не нужно.',
                     'Монтаж включён в стоимость, а иных платежей по договору нет.',
                     'Отдельно оплачивать ничего не нужно, других расходов договор не предусматривает.'):
            with self.subTest(text):
                self.assertFalse(added_assertions_safe(text, self.SOURCE))

    def test_document_reference_and_connectives_are_not_assertions(self):
        source = [Fragment('f', 'Договор подряда ПД-8-2033.txt', 0, 200,
                           '5.3. Стоимость работ указывается в Смете и включает монтаж оборудования и пусконаладку.', '')]
        text = ('Да, монтаж включён в стоимость: по договору подряда № ПД-8/2033 стоимость работ указывается в Смете '
                'и включает монтаж оборудования и пусконаладку, поэтому отдельно их оплачивать не нужно (п. 5.3).')
        self.assertTrue(added_assertions_safe(text, source))
        # The same sentence with an item the clause does not name still fails.
        self.assertFalse(added_assertions_safe(text.replace('пусконаладку, поэтому', 'пусконаладку и доставку, поэтому'), source))

    def test_items_named_in_the_sentence_before(self):
        self.assertTrue(added_assertions_safe(
            'Да, монтаж оборудования и пусконаладка включены в стоимость работ (п. 5.3). Отдельно их оплачивать не требуется.', self.SOURCE))
        # The previous sentence does not carry an item the absence is about.
        self.assertFalse(added_assertions_safe(
            'Да, монтаж оборудования включён в стоимость работ (п. 5.3). Отдельно доставку оплачивать не требуется.', self.SOURCE))

    def test_without_an_inclusion_clause_the_absence_still_fails(self):
        source = [Fragment('f', 'contract.txt', 0, 200, '5.3. Монтаж оборудования выполняется Подрядчиком на объекте Заказчика.', '')]
        self.assertFalse(added_assertions_safe('Монтаж оборудования отдельно оплачивать не нужно.', source))
