"""The «Источник» line names documents as a reader and the organizer golden do.

Comparison with a strong public solution and the organizer golden on the demo
(13 November): we printed file names — «ТК ст70 действующая», «Регламент
согласования договоров ред 2023 (утратил силу), ред. от 10.01.2023, утратила
силу с 01.03.2025», «Договор аренды А-08-2024 Северный Склад, п. 4.3, 1.1» —
where the golden reads «ТК РФ, ст. 70», «Регламент … в редакции от …», «договор
аренды № А-08/2024, п. 4.3». The judge reads the extra file-name words and the
neighbouring clause as noise. Names come from each document's own header.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import cite_name, formal_name, names_referenced_documents, source_line  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_prose_answers import confirm, run, select  # noqa: E402


class FormalNameTests(unittest.TestCase):
    def test_names_from_headers(self):
        cases = [
            ('Источник: Статья 81. ТК РФ Расторжение договора. Трудовой кодекс Российской Федерации\nURL: x', 'ТК РФ, ст. 81'),
            ('Источник: Статья 20.4. КоАП РФ Нарушение требований. Кодекс\n', 'КоАП РФ, ст. 20.4'),
            ('Источник: Статья 6. Условия обработки. Федеральный закон от 27.07.2006 N 152-ФЗ "О данных"\n',
             'Федеральный закон № 152-ФЗ, ст. 6'),
            ('ДОГОВОР ПОДРЯДА № Д-3/2030\nг. Омск — 1 мая 2030 г.\nООО «Вектор» …', 'Договор подряда № Д-3/2030'),
            ('ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 2\nк договору подряда № Д-3/2030 от 1 мая 2030 г.\nг. Омск', 
             'Дополнительное соглашение № 2 к договору подряда № Д-3/2030'),
            ('ПОЛОЖЕНИЕ О ЗАКУПКАХ ООО «ВЕКТОР»\nУтверждено приказом № 3', 'Положение о закупках'),
            ('ООО «ВЕКТОР»\nОтдел кадров\nСЛУЖЕБНАЯ ЗАПИСКА № ОК-4 от 02.03.2031\nО графике', 'Служебная записка № ОК-4'),
            ('ООО «ВЕКТОР»\nСлужба безопасности\nИсх. № СБ-9 от 01.02.2031\nО пропусках', 'Письмо № СБ-9 (служба безопасности)'),
        ]
        for text, name in cases:
            with self.subTest(name):
                self.assertEqual(formal_name(text), name)

    def test_unrecognised_header_keeps_the_file_name(self):
        self.assertEqual(formal_name('Заметки о складе.\nПроизвольный текст.'), '')
        self.assertEqual(cite_name('документы__Заметки о складе.txt', {}), 'Заметки о складе')

    def test_edition_only_for_internal_rules(self):
        editions = {('name', 'r'): 'Положение о закупках', 'r': 'ред. от 05.02.2031, утратила силу с 01.01.2032',
                    ('name', 'c'): 'Договор подряда № Д-3/2030', 'c': 'ред. от 05.02.2031'}
        self.assertEqual(cite_name('r', editions), 'Положение о закупках (ред. от 05.02.2031)')
        self.assertEqual(cite_name('c', editions), 'Договор подряда № Д-3/2030')


class CitedClausesTests(unittest.TestCase):
    EVIDENCE = [Fragment('a', 'd', 0, 10, '4.3. Арендодатель обеспечивает доступ круглосуточно.', ''),
                Fragment('b', 'd', 10, 20, '1.1. Арендодатель передаёт помещение.', '')]
    CANDIDATE = {'claims': [{'sources': [{'fragment_id': 'a'}]}, {'sources': [{'fragment_id': 'b'}]}]}

    def test_only_clauses_the_text_cites(self):
        line = source_line(self.CANDIDATE, self.EVIDENCE, {}, 'Да, доступ круглосуточный (п. 4.3).')
        self.assertEqual(line, 'Источник: d, п. 4.3.')

    def test_all_clauses_when_the_text_cites_none(self):
        line = source_line(self.CANDIDATE, self.EVIDENCE, {}, 'Да, доступ круглосуточный.')
        self.assertEqual(line, 'Источник: d, п. 4.3, 1.1.')
        # «14.3» or «4.31» is not «4.3».
        line = source_line(self.CANDIDATE, self.EVIDENCE, {}, 'Да, по п. 14.3 и 4.31.')
        self.assertEqual(line, 'Источник: d, п. 4.3, 1.1.')



class ValueInAnotherDocumentTests(unittest.TestCase):
    """Demo question 17 (warranty in the manufacturer's coupon): a checked text that
    says where the value is replaces the machine wording and the quotation."""

    FILES = {'Договор.txt': 'ДОГОВОР ПОСТАВКИ № Н-9/2032\n5.4. Срок службы оборудования определяется заводом-изготовителем '
                            'и указывается в техническом формуляре.\n'}

    def test_text_naming_the_document_is_published(self):
        draft = ('Договор срок службы не называет: его определяет завод-изготовитель, '
                 'и он указывается в техническом формуляре (п. 5.4).')
        # A partial with a missing document gets one expanded search (AGENTS rule 3).
        text, status, _, _ = run('Какой срок службы оборудования?', [select('5.4.', draft), confirm()] * 2, self.FILES)
        self.assertEqual(status, 'partial')
        self.assertTrue(text.startswith(draft), text)
        self.assertIn('Источник: Договор поставки № Н-9/2032, п. 5.4.', text)
        self.assertIn('нужен этот документ', text)
        self.assertNotIn('«5.4.', text)

    def test_the_source_document_name_is_not_an_added_record_claim(self):
        # Demo 17: «Срок гарантии по договору с ООО «Альфа-Трейдинг» … указывает в
        # гарантийном талоне» was rejected for the contract and party name.
        from psb_policy import scope_block_reason
        src = [Fragment('s', 'документы компании__Договор поставки Н-9-2032 Бета-Сервис.txt', 0, 1,
                        '5.4. Срок службы оборудования определяется заводом-изготовителем и указывается в сервисном паспорте.', '')]
        good = ('Срок службы по договору с ООО «Бета-Сервис» определяет завод-изготовитель и указывает в сервисном '
                'паспорте (п. 5.4).')
        self.assertEqual(scope_block_reason(good, src, None), '')
        self.assertEqual(scope_block_reason('В сервисном паспорте указывается цена и подпись директора.', src, None),
                         'added_assertion')

    def test_service_life_is_not_a_department(self):
        from psb_policy import prose_scope_safe
        src = [Fragment('s', 'd', 0, 10, '5.4. Срок службы определяется заводом-изготовителем.', '')]
        self.assertTrue(prose_scope_safe('Срок службы договор не называет (п. 5.4).', src))
        # A department still may not be denied a function the source does not deny.
        self.assertFalse(prose_scope_safe('Служба безопасности не согласует договоры (п. 5.4).', src))

    def test_text_hiding_the_document_is_not_published(self):
        self.assertFalse(names_referenced_documents('Договором срок службы не установлен.',
                                                    ['указывается в техническом формуляре']))
        draft = 'Договором срок службы не установлен (п. 5.4).'
        text, _, _, _ = run('Какой срок службы оборудования?', [select('5.4.', draft), confirm()] * 2, self.FILES)
        self.assertNotIn(draft, text)
        self.assertIn('техническом формуляре', text)


if __name__ == '__main__':
    unittest.main()
