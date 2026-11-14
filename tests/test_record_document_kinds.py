"""Claims about what another document records, for every document kind.

The barrier against added «в X указывается …» assertions knew only acts,
protocols, registers, journals, reports, specifications, coupons and
passports. A text «в формуляре прибора указываются цена и подпись директора»
passed: the formulary (and a certificate, waybill, estimate, application …)
was not recognised as a document, so the added contents were never compared
with the source sentence. The source's own wording must still pass.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import added_assertions_safe, scope_block_reason  # noqa: E402

# (source sentence, restated by the answer, invented contents of the same document)
CASES = [
    ('6.3. Межповерочный интервал определяется изготовителем и указывается в формуляре прибора.',
     'Межповерочный интервал определяет изготовитель и указывает в формуляре прибора (п. 6.3).',
     'В формуляре прибора указываются цена прибора и подпись главного инженера.'),
    ('4.5. Срок годности продукции устанавливается производителем и указывается в сертификате качества.',
     'Срок годности устанавливает производитель, он указывается в сертификате качества (п. 4.5).',
     'В сертификате качества указываются адрес склада и фамилия кладовщика.'),
    ('3.2. Количество поставленного товара фиксируется в товарной накладной.',
     'Количество поставленного товара фиксируется в товарной накладной (п. 3.2).',
     'В товарной накладной фиксируются штрафы поставщика и сроки оплаты.'),
    ('2.6. Стоимость работ определяется сметой и указывается в локальной смете.',
     'Стоимость работ указывается в локальной смете (п. 2.6).',
     'В локальной смете указываются гарантийный срок и состав бригады.'),
    ('5.1. Объём закупки указывается в заявке подразделения.',
     'Объём закупки указывается в заявке подразделения (п. 5.1).',
     'В заявке подразделения указываются банковские реквизиты поставщика и лимит неустойки.'),
    ('7.4. Сумма аванса отражается в счёте-фактуре.',
     'Сумма аванса отражается в счёте-фактуре (п. 7.4).',
     'В счёте-фактуре отражаются сроки поставки и порядок приёмки.'),
]


class RecordDocumentKindTests(unittest.TestCase):
    def test_invented_contents_of_each_document_kind_are_rejected(self):
        for source, _, invented in CASES:
            with self.subTest(invented):
                src = [Fragment('s', 'Договор.txt', 0, len(source), source, '')]
                self.assertFalse(added_assertions_safe(invented, src))
                self.assertEqual(scope_block_reason(invented, src, None), 'added_assertion')

    def test_restated_source_wording_passes(self):
        for source, restated, _ in CASES:
            with self.subTest(restated):
                src = [Fragment('s', 'Договор.txt', 0, len(source), source, '')]
                self.assertTrue(added_assertions_safe(restated, src))

    def test_ordinary_words_are_not_documents(self):
        # «за счёт», «в счёт оплаты» are not an invoice.
        src = [Fragment('s', 'Договор.txt', 0, 80, '2.2. Доставка производится за счёт Поставщика.', '')]
        for text in ('Доставка производится за счёт поставщика, это указано в п. 2.2.',
                     'Расходы на доставку несёт поставщик: она производится за его счёт (п. 2.2).'):
            with self.subTest(text):
                self.assertTrue(added_assertions_safe(text, src))

    def test_clause_about_the_contract_is_not_a_record_claim(self):
        source = '5.4. Срок службы оборудования определяется заводом-изготовителем и указывается в техническом формуляре.'
        src = [Fragment('s', 'Договор.txt', 0, len(source), source, '')]
        for text in ('Договор срок службы не называет: его определяет завод-изготовитель, '
                     'и он указывается в техническом формуляре (п. 5.4).',
                     'Договор срока не содержит — срок службы указывается в техническом формуляре.'):
            with self.subTest(text):
                self.assertTrue(added_assertions_safe(text, src))
        # The clause with the document is still compared with the source.
        self.assertFalse(added_assertions_safe(
            'Договор срок не называет: в техническом формуляре указываются цена и подпись директора.', src))


if __name__ == '__main__':
    unittest.main()
