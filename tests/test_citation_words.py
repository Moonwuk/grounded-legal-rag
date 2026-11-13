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


class ScopeRuleExclusiveTests(unittest.TestCase):
    """Diagnostic set on the organizer base (PSB_AB_20_vs_24, N05): «новый адрес
    применяется только к партиям, спецификации на которые подписаны после 1
    октября» was rejected because the source has no literal «только», although its
    application rule with a condition («применяется к партиям …, подписаны после»)
    already limits the scope. The text then fell back to bare quotations and the
    verifier refused them as giving no conclusion."""

    SOURCE = [Fragment('f', 'Доп соглашение 2 к договору Р-4-2033.txt', 0, 300,
                       'Новая ставка хранения применяется к поставкам, акты на которые подписаны после 15 марта 2033 г.', '')]

    def test_only_restating_a_conditional_scope_rule_passes(self):
        from psb_policy import prose_scope_safe
        for text in ('Нет. Новая ставка хранения применяется только к поставкам, акты на которые подписаны после 15 марта 2033 г.',
                     'Новая ставка хранения применяется лишь к поставкам, акты на которые подписаны после 15 марта 2033 г.; '
                     'ваш акт подписан раньше.',
                     'Допсоглашение № 2 меняет ставку хранения, но новая ставка хранения применяется только к поставкам, '
                     'акты на которые подписаны после 15 марта 2033 г.'):
            with self.subTest(text):
                self.assertTrue(prose_scope_safe(text, self.SOURCE))

    def test_only_on_another_subject_still_fails(self):
        from psb_policy import prose_scope_safe
        for text in ('Новая ставка хранения применяется только к поставкам оборудования.',
                     'Хранение возможно только на складе поставщика.',
                     'Только руководитель вправе подписать акт поставки после 15 марта 2033 г.'):
            with self.subTest(text):
                self.assertFalse(prose_scope_safe(text, self.SOURCE))


class ScopeRuleWithSubjectFromTheSameProvisionTests(unittest.TestCase):
    """One-call run on 13 November, question on the delivery address under a
    supplementary agreement: «Новый адрес — Московская область, г. Химки, … —
    применяется только к партиям, спецификации на которые подписаны после 1
    октября» was rejected. The scope rule was restated, but the clause also named
    the new address, which the same agreement states in the sentence before."""

    SOURCE = [Fragment('f', 'Доп соглашение 3 к договору Р-4-2033.txt', 0, 400,
                       'Изложить пункт 5.1 договора в следующей редакции: «5.1. Хранение осуществляется на складе '
                       'по адресу: г. Тверь, ул. Озёрная, д. 9, склад № 2».\nНовый адрес хранения применяется к партиям, '
                       'накладные на которые оформлены после 20 мая 2033 г.', '')]

    def test_scope_rule_with_the_subject_named_passes(self):
        from psb_policy import prose_scope_safe
        for text in ('Новый адрес — г. Тверь, ул. Озёрная, д. 9, склад № 2 — применяется только к партиям, накладные на которые '
                     'оформлены после 20 мая 2033 г., а ваша накладная оформлена раньше.',
                     'Новый адрес хранения (г. Тверь, ул. Озёрная, д. 9, склад № 2) применяется лишь к партиям, накладные на '
                     'которые оформлены после 20 мая 2033 г.'):
            with self.subTest(text):
                self.assertTrue(prose_scope_safe(text, self.SOURCE))

    def test_words_from_outside_the_provision_still_fail(self):
        from psb_policy import prose_scope_safe
        for text in ('Новый адрес — г. Тверь, ул. Озёрная, д. 9, склад № 2 — применяется только к партиям мебели, '
                     'оплаченным авансом после 20 мая 2033 г.',
                     'Хранение на складе в Твери возможно только для партий, оформленных после 20 мая 2033 г. руководителем.',
                     'Только склад № 2 по адресу г. Тверь, ул. Озёрная, д. 9 принимает партии.'):
            with self.subTest(text):
                self.assertFalse(prose_scope_safe(text, self.SOURCE))


class ContentDescriptionOnlyTests(unittest.TestCase):
    """Diagnostic set on the organizer base (PSB_AB_20_vs_24, N14): «срок возврата в
    договоре не установлен; пункт 3.5 устанавливает лишь размер платежа» was cut
    because the source has no «лишь», though the word describes what the clause
    says, not a stronger norm. Only right after a content verb with a clause or
    document as the subject."""

    SOURCE = [Fragment('f', 'Договор хранения Х-2-2034.txt', 0, 200,
                       '4.4. При подписании договора Поклажедатель вносит гарантийный взнос в размере 30 000 рублей.', '')]

    def test_description_of_a_clause_passes(self):
        from psb_policy import prose_scope_safe
        for text in ('Срок возврата гарантийного взноса договором не установлен: пункт 4.4 устанавливает лишь размер взноса.',
                     'Договор предусматривает только внесение взноса при подписании (п. 4.4), срок его возврата не указан.'):
            with self.subTest(text):
                self.assertTrue(prose_scope_safe(text, self.SOURCE))

    def test_stronger_norm_still_fails(self):
        from psb_policy import prose_scope_safe
        for text in ('Гарантийный взнос вносится только при подписании договора.',
                     'Только Поклажедатель вправе вносить гарантийный взнос.',
                     'Возврат возможен лишь после окончания хранения.'):
            with self.subTest(text):
                self.assertFalse(prose_scope_safe(text, self.SOURCE))
