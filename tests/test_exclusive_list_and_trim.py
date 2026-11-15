"""Bare quotations after the scope barriers, 13 November same-time runs.

1. «6 месяцев допускается только для главных бухгалтеров …»: the law reads «срок
   испытания не может превышать трех месяцев, а для руководителей …, главных
   бухгалтеров … — шести месяцев». A general rule with an exception for listed
   persons makes the listed value theirs only; «только для» followed by words of
   that list restates the source. Other uses of «только» are still rejected.
2. «Запускает начальник вашего отдела … (п. 1.3). Юридический отдел проект
   согласует, но не запускает согласование (п. 2.1).»: the role negation in the
   second sentence discarded the correct direct answer; both generations did it
   and only the provisions were published. One later sentence the barriers reject
   is dropped when at least ten words stay; the shorter text passes every check.
"""
from pathlib import Path
import sys
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'), str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment  # noqa: E402
from psb_policy import prose_scope_safe  # noqa: E402
from test_prose_answers import confirm, run, select  # noqa: E402

LAW = [Fragment('a', 'УчК', 0, 1, 'Срок стажировки не может превышать двух месяцев, а для старших инженеров и их '
                'заместителей, руководителей лабораторий - четырёх месяцев, если иное не установлено законом.', '')]


class ExceptionListTests(unittest.TestCase):
    def test_only_for_the_listed_persons(self):
        for text in ('Общий предел — два месяца; четыре месяца допускается только для старших инженеров и их '
                     'заместителей, руководителей лабораторий (ст. 41).',
                     'Четыре месяца — только для руководителей лабораторий.'):
            with self.subTest(text):
                self.assertTrue(prose_scope_safe(text, LAW))

    def test_other_exclusive_claims_stay_rejected(self):
        for text in ('Четыре месяца допускается только для стажёров-исследователей.',
                     'Стажировку можно назначать только после аттестации.',
                     'Только старшие инженеры могут проходить стажировку.'):
            with self.subTest(text):
                self.assertFalse(prose_scope_safe(text, LAW))
        plain = [Fragment('b', 'УчК', 0, 1, 'Срок стажировки для старших инженеров не может превышать четырёх месяцев.', '')]
        self.assertFalse(prose_scope_safe('Четыре месяца допускается только для старших инженеров.', plain))


CONTRACT = [Fragment('c', 'Договор.txt', 0, 1, '5.1. Заказчик оплачивает работы в течение 20 дней с даты приёмки.\n'
                     '5.2. По соглашению сторон допускается авансовый платёж. Размер аванса указывается в счёте.', ''),
            Fragment('d', 'Договор.txt', 1, 2, '6.1. По соглашению сторон устанавливается график работ.', '')]


class PermissionConditionTests(unittest.TestCase):
    """Demo 9 and its paraphrases: «предоплата возможна, но только по соглашению
    Сторон» for «По соглашению Сторон допускается предоплата» was rejected."""

    def test_only_with_the_condition_of_a_permission(self):
        self.assertTrue(prose_scope_safe('Да, аванс возможен, но только по соглашению сторон (п. 5.2).', CONTRACT))

    def test_other_conditions_stay_rejected(self):
        for text in ('Аванс возможен только по письменному заявлению заказчика.',
                     'График работ определяется только по соглашению сторон и иначе не меняется.',
                     'Аванс возможен только при согласии директора.'):
            with self.subTest(text):
                self.assertFalse(prose_scope_safe(text, CONTRACT))


RULES = {'Порядок закупок.txt': 'ПОРЯДОК ЗАКУПОК\n1.4. Заявку на закупку подаёт руководитель отдела, которому нужен товар.\n'
                                '2.2. Заявка согласуется с финансовым отделом.\n'}
FIRST = ('Заявку подаёт руководитель вашего отдела: её подаёт руководитель отдела, которому нужен товар (п. 1.4).')


class BlockedSentenceTests(unittest.TestCase):
    def test_role_negation_in_a_later_sentence_is_dropped(self):
        draft = FIRST + ' Финансовый отдел заявку согласует, но не инициирует закупку (п. 2.2).'
        text, status, _, _ = run('Кто подаёт заявку на закупку — финансовый отдел или наш руководитель?',
                                 [select('1.4.', draft), confirm()], RULES)
        self.assertEqual(status, 'answer')
        self.assertTrue(text.startswith(FIRST + '\n'), text)
        self.assertNotIn('не инициирует', text)

    def test_bare_yes_or_no_is_not_left(self):
        draft = 'Нет. Финансовый отдел не подаёт заявку, это делает руководитель отдела (п. 1.4).'
        text, _, _, _ = run('Подаёт ли финансовый отдел заявку на закупку?',
                            [select('1.4.', draft), confirm()] * 2, RULES)
        self.assertNotEqual(text.split('\n')[0], 'Нет.')

    def test_blocked_first_sentence_is_not_kept(self):
        draft = ('Финансовый отдел заявку согласует, но не инициирует закупку (п. 2.2). ' + FIRST)
        text, _, _, _ = run('Кто подаёт заявку на закупку?', [select('1.4.', draft), confirm()] * 2, RULES)
        self.assertNotIn('не инициирует', text)


if __name__ == '__main__':
    unittest.main()
