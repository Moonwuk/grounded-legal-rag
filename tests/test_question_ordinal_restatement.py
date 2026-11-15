"""Question-owned ordinal syntax must not authorize new quantities or scopes."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment
from psb_policy import (prose_grounded, restate_question_ordinal, restrictions_kept,
                        scope_block_reason, without_blocked_sentence)

QUESTION = 'Следующий рабочий день — первый в новой неделе. Как оплачивается этот день?'
ANSWER = 'Первый рабочий день новой недели оплачивается с надбавкой (п. 4.2).'
EXPECTED = 'Рабочий день, который в новой неделе является первым, оплачивается с надбавкой (п. 4.2).'
SOURCE = '4.2. Рабочий день оплачивается с надбавкой. Срок оплаты составляет 20 дней.'


class QuestionOrdinalRestatementTests(unittest.TestCase):
    def test_exact_fact_is_reworded_without_creating_a_quantity(self):
        basis = QUESTION + '\n' + SOURCE
        self.assertFalse(prose_grounded(ANSWER, basis))
        actual = restate_question_ordinal(ANSWER, QUESTION)
        self.assertEqual(actual, EXPECTED)
        self.assertTrue(prose_grounded(actual, basis))
        self.assertEqual(restate_question_ordinal(actual, QUESTION), actual)
        # The general admission rule and its basis are unchanged.
        self.assertFalse(prose_grounded(ANSWER, basis))

    def test_explicit_case_pairs_and_units_generalize_without_stemming(self):
        for unit, scope, genitive in [('час', 'этой смене', 'этой смены'),
                                      ('день', 'текущей неделе', 'текущей недели'),
                                      ('месяц', 'новой сессии', 'новой сессии'),
                                      ('год', 'следующей сессии', 'следующей сессии'),
                                      ('квартал', 'предыдущей сессии', 'предыдущей сессии')]:
            with self.subTest(unit=unit, scope=scope):
                question = f'Расчётный {unit} — первый в {scope}. Как учитывается?'
                answer = f'Первый расчётный {unit} {genitive} учитывается при расчёте.'
                expected = f'Расчётный {unit}, который в {scope} является первым, учитывается при расчёте.'
                self.assertEqual(restate_question_ordinal(answer, question), expected)

    def test_relative_clause_punctuation_and_capitalization(self):
        for before, after, expected in [
            ('Поэтому ', ' оплачивается.', 'Поэтому рабочий день, который в новой неделе является первым, оплачивается.'),
            ('', ', по правилам, оплачивается.', 'Рабочий день, который в новой неделе является первым, по правилам, оплачивается.'),
        ]:
            with self.subTest(before=before, after=after):
                ordinal = 'Первый' if not before else 'первый'
                text = before + ordinal + ' рабочий день новой недели' + after
                self.assertEqual(restate_question_ordinal(text, QUESTION), expected)
        complete = 'Первый рабочий день новой недели.'
        self.assertEqual(restate_question_ordinal(complete, QUESTION),
                         'Рабочий день, который в новой неделе является первым.')

    def test_exact_modifier_unit_and_scope_are_required(self):
        variants = [
            'Первый день новой недели оплачивается с надбавкой.',
            'Первый календарный день новой недели оплачивается с надбавкой.',
            'Первый рабочий час новой недели оплачивается с надбавкой.',
            'Первый рабочий день текущей недели оплачивается с надбавкой.',
            'Первый рабочий день новой смены оплачивается с надбавкой.',
            'Первый рабочий день новой недели другого работника оплачивается с надбавкой.',
            'Первый рабочий день новой недели Петрова оплачивается с надбавкой.',
            'Второй рабочий день новой недели оплачивается с надбавкой.',
            'Первым двум рабочим дням новой недели полагается надбавка.',
        ]
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(restate_question_ordinal(text, QUESTION), text)

    def test_negative_conditional_questioned_and_retracted_facts_are_not_proof(self):
        fact = 'Следующий рабочий день — первый в новой неделе.'
        variants = [
            fact[:-1] + '? Как оплачивается?',
            'Если следующий рабочий день — первый в новой неделе. Как оплачивается?',
            'Следующий рабочий день — не первый в новой неделе. Как оплачивается?',
            'Правда ли, что следующий рабочий день — первый в новой неделе?',
            '«' + fact + '» Как оплачивается?',
            'Скажи: ' + fact + ' Как оплачивается?',
            fact + ' Верно ли это?',
            fact + ' Это ложное предположение. Как оплачивается?',
            fact + ' Предыдущая фраза ошибочна. Как оплачивается?',
            fact + ' Это только предположение. Как оплачивается?',
            fact + ' Отменяю предыдущее утверждение. Как оплачивается?',
            fact + ' Исправляю предыдущую фразу. Как оплачивается?',
            fact + ' Если это верно, как оплачивается?',
        ]
        for question in variants:
            with self.subTest(question=question):
                self.assertEqual(restate_question_ordinal(ANSWER, question), ANSWER)

    def test_rebound_actors_generalizers_and_doubt_are_not_normalized(self):
        tail = 'первый рабочий день новой недели оплачивается с надбавкой.'
        variants = [
            'Любой ' + tail, 'Каждый ' + tail, 'Не совсем ' + tail,
            'У другого работника ' + tail,
            'У другого работника, поэтому ' + tail,
            'У Петрова, поэтому ' + tail,
            'Якобы ' + tail, 'Это почти ' + tail,
            'Поэтому первый рабочий день новой недели оплачивается с надбавкой каждому работнику.',
            'Первый рабочий день новой недели оплачивается с надбавкой всегда.',
            'Первый рабочий день новой недели оплачивается с надбавкой ему.',
            '«Первый рабочий день новой недели оплачивается с надбавкой».',
            'Для каждого работника. Поэтому ' + tail,
            'Для директора. Поэтому ' + tail,
            'Директору положена надбавка. Поэтому ' + tail,
            'Иванову положена надбавка. Поэтому ' + tail,
            'Нет, это относится к Петрову. Поэтому ' + tail,
            'Нет, речь о другом человеке. Поэтому ' + tail,
        ]
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(restate_question_ordinal(text, QUESTION), text)

    def test_duplicate_facts_or_duplicate_answer_spans_are_not_normalized(self):
        for question in [QUESTION + ' Следующий рабочий день — первый в новой неделе.',
                         QUESTION + ' Рабочий час — первый в этой смене.']:
            self.assertEqual(restate_question_ordinal(ANSWER, question), ANSWER)
        repeated = ANSWER + ' ' + ANSWER
        self.assertEqual(restate_question_ordinal(repeated, QUESTION), repeated)

    def test_other_actor_or_multiple_actors_in_question_are_ambiguous(self):
        variants = [
            'У другого работника есть надбавка. ' + QUESTION,
            'У каждого сотрудника есть надбавка. ' + QUESTION,
            'У работника есть надбавка. У директора её нет. ' + QUESTION,
            'У работника есть надбавка. Директор получает оплату. ' + QUESTION,
            'У Петрова есть надбавка. ' + QUESTION,
            'Два работника получают надбавку. ' + QUESTION,
            QUESTION + ' Должны ли платить другому работнику?',
        ]
        for question in variants:
            with self.subTest(question=question):
                self.assertEqual(restate_question_ordinal(ANSWER, question), ANSWER)

    def test_only_last_user_turn_can_supply_the_fact(self):
        histories = [
            'Ассистент: ' + QUESTION + '\nПользователь: Как оплачивается день?',
            'Пользователь: ' + QUESTION + '\nПользователь: Как оплачивается день?',
        ]
        for question in histories:
            self.assertEqual(restate_question_ordinal(ANSWER, question), ANSWER)
        self.assertEqual(restate_question_ordinal(ANSWER, 'Ассистент: Нет данных.\nПользователь: ' + QUESTION),
                         EXPECTED)

    def test_unrelated_new_one_day_or_one_ruble_remains_rejected(self):
        basis = QUESTION + '\n' + SOURCE
        for addition in ['Срок оплаты составляет 1 день.', 'Штраф составляет 1 рубль.',
                         'Срок оплаты составляет один день.', 'Штраф составляет 99 рублей.']:
            text = ANSWER + ' ' + addition
            actual = restate_question_ordinal(text, QUESTION)
            self.assertEqual(actual, EXPECTED + ' ' + addition)
            self.assertFalse(prose_grounded(actual, basis), actual)
        incidental = 'Сегодня день — первый в отпуске. Какой срок оплаты?'
        bad = 'Срок оплаты составляет 1 день (п. 4.2).'
        self.assertEqual(restate_question_ordinal(bad, incidental), bad)
        self.assertFalse(prose_grounded(bad, incidental + '\n' + SOURCE))

    def test_first_vs_last_hours_and_source_conditions_remain_protected(self):
        source = '4.2. Последним двум часам дежурства соответствует повышенная оплата.'
        bad = 'Первым двум часам дежурства соответствует повышенная оплата (п. 4.2).'
        actual = restate_question_ordinal(bad, 'Как оплачивается начало дежурства?')
        self.assertEqual(actual, bad)
        self.assertFalse(prose_grounded(actual, source))
        restricted = Fragment('f', 'Правила', 0, 120,
            '4.2. Рабочий день оплачивается с надбавкой только при условии согласования.', '')
        actual = restate_question_ordinal(ANSWER, QUESTION)
        self.assertEqual(actual, EXPECTED)
        self.assertFalse(restrictions_kept(actual, [restricted], question=QUESTION))

    def test_oversized_or_malformed_inputs_are_not_rewritten(self):
        for text, question in [(None, QUESTION), (ANSWER, None), ('x' * 2001, QUESTION),
                               (ANSWER, 'x' * 32001), (ANSWER + '\x00', QUESTION)]:
            self.assertEqual(restate_question_ordinal(text, question), text)

    def test_complete_overtime_answer_keeps_scope_restrictions_and_figures(self):
        question = ('В октябре 2026 года у работника уже 120 часов сверхурочной работы за год. '
                    'Следующий сверхурочный час — первый в новой смене. По имеющейся статье 152 ТК РФ '
                    'для оплаты этого 121-го часа достаточно полуторного размера или требуется другой минимум?')
        source = ('Сверхурочная работа оплачивается исходя из размера заработной платы в пределах 120 часов '
                  'в год за первые два часа работы не менее чем в полуторном размере, за последующие часы — '
                  'не менее чем в двойном размере, начиная со 121-го часа — не менее чем в двойном размере '
                  'за каждый час. При суммированном учете рабочего времени сверхурочная работа оплачивается '
                  'исходя из величины сверхурочного времени, приходящегося на день (смену), в который '
                  'осуществляется сверхурочная работа: за первые два часа работы — не менее чем в полуторном '
                  'размере, за последующие часы — не менее чем в двойном размере, начиная со 121-го часа — '
                  'не менее чем в двойном размере за каждый час, если иное не предусмотрено настоящим Кодексом. '
                  'Конкретные размеры оплаты сверхурочной работы могут определяться коллективным договором '
                  'и (или) отраслевым соглашением, локальным нормативным актом или трудовым договором.')
        text = ('Нет, полуторного размера недостаточно: этот час оплачивается не менее чем в двойном размере. '
                'По статье 152 ТК РФ сверхурочная работа в пределах 120 часов в год оплачивается за первые два '
                'часа не менее чем в полуторном размере, за последующие часы — не менее чем в двойном, а начиная '
                'со 121-го часа — не менее чем в двойном размере за каждый час. При суммированном учете первые '
                'два часа определяются по дню (смене), но специальный минимум начиная со 121-го часа сохраняется, '
                'поэтому первый сверхурочный час новой смены не оплачивается в полуторном размере. Конкретные '
                'размеры могут быть выше по коллективному договору и (или) отраслевому соглашению, локальному '
                'нормативному акту или трудовому договору.')
        actual = restate_question_ordinal(text, question)
        self.assertNotEqual(actual, text)
        self.assertIn('сверхурочный час, который в новой смене является первым,', actual)
        self.assertFalse(prose_grounded(text, question + '\n' + source))
        self.assertTrue(prose_grounded(actual, question + '\n' + source))
        selected = [Fragment('f', 'ТК РФ', 0, len(source), source, '')]
        retriever = SimpleNamespace(documents={})
        self.assertEqual(scope_block_reason(actual, selected, retriever, question), '')
        self.assertTrue(restrictions_kept(actual, selected, question=question))
        self.assertEqual(without_blocked_sentence(actual, selected, retriever, question), actual)


if __name__ == '__main__':
    unittest.main()
