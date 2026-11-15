"""An exception belongs to its own thresholded restriction, not any other one."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_policy import lost_bound_numeric_exceptions, all_bound_numeric_exception_phrases


class BoundNumericExceptionTests(unittest.TestCase):
    clause = 'за исключением предприятий, которые соответствуют критериям, установленным Советом директоров'
    source = ('предприятиям, у которых доля экспортной выручки составляет не менее 35 процентов, '
              + clause + ';')
    ban = 'Льгота не применяется к предприятиям с долей экспортной выручки не менее 35 процентов'

    def selected(self, source=None):
        return [SimpleNamespace(text='Льгота не применяется к следующим категориям:'),
                SimpleNamespace(text=self.source if source is None else source)]

    def test_actual_parent_ban_requires_its_own_exception(self):
        self.assertEqual(lost_bound_numeric_exceptions(self.ban + '.', self.selected()), [self.clause])
        self.assertEqual(lost_bound_numeric_exceptions(
            self.ban + ', кроме соответствующих критериям Совета директоров.', self.selected()), [])

    def test_unrelated_list_exception_cannot_cover_a_later_restriction(self):
        answer = ('Льгота не применяется к реорганизованным предприятиям, кроме преобразованных; '
                  'предприятиям с долей экспортной выручки не менее 35 процентов.')
        self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [self.clause])
        answer = self.ban + '; к реорганизованным предприятиям, кроме соответствующих критериям Совета директоров.'
        self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [self.clause])

    def test_wrong_authority_or_inverted_exception_is_not_preservation(self):
        for tail in (', кроме не соответствующих критериям Совета директоров.',
                     ', кроме соответствующих критериям Министерства финансов.',
                     ', кроме соответствующих критериям Совета министров.'):
            with self.subTest(tail=tail):
                self.assertEqual(lost_bound_numeric_exceptions(self.ban + tail, self.selected()), [self.clause])

    def test_short_answer_and_denial_of_a_ban_do_not_invent_obligations(self):
        for answer in ('Размер льготы определяется категорией предприятия.',
                       'Для льготы нужна дополнительная информация о доходах.',
                       'Если предприятие соответствует критериям Совета директоров, одна лишь доля экспортной '
                       'выручки не менее 35 процентов не запрещает применять льготу.'):
            with self.subTest(answer=answer):
                self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [])

    def test_same_number_without_the_source_subject_is_not_enough(self):
        answer = 'Льгота не применяется при потреблении электроэнергии не менее 35 процентов.'
        self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [])

    def test_values_and_authority_come_from_the_selected_source(self):
        source = self.source.replace('35', '42,5').replace('Советом директоров', 'Экспертной комиссией')
        answer = self.ban.replace('35', '42.50')
        expected = self.clause.replace('Советом директоров', 'Экспертной комиссией')
        self.assertEqual(lost_bound_numeric_exceptions(answer + '.', self.selected(source)), [expected])
        self.assertEqual(lost_bound_numeric_exceptions(answer + ', кроме соответствующих критериям Экспертной комиссии.',
                                                      self.selected(source)), [])

    def test_decimal_threshold_comparison_does_not_round_distinct_source_values(self):
        source = self.source.replace('35', '35.00000000000000001')
        self.assertEqual(lost_bound_numeric_exceptions(self.ban + '.', self.selected(source)), [])

    def test_source_only_retry_memory_refreshes_with_current_selection(self):
        self.assertEqual(all_bound_numeric_exception_phrases(self.selected()), [self.clause])
        self.assertEqual(all_bound_numeric_exception_phrases([]), [])
        self.assertEqual(lost_bound_numeric_exceptions(self.ban + '.', []), [])

    def test_standalone_exception_can_continue_one_unambiguous_parent_ban(self):
        answer = (self.ban + '. Экспортная выручка 36 процентов подпадает под этот запрет. '
                  'Исключение — предприятия, соответствующие критериям Совета директоров; сведений об этом нет.')
        self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [])

    def test_standalone_exception_does_not_hide_wrong_authority_or_polarity(self):
        for tail in ('Исключение — предприятия, не соответствующие критериям Совета директоров.',
                     'Исключение — предприятия, соответствующие критериям Совета министров.',
                     'Критерии Совета директоров используются при выдаче грантов.'):
            with self.subTest(tail=tail):
                self.assertEqual(lost_bound_numeric_exceptions(self.ban + '. ' + tail, self.selected()), [self.clause])

    def test_standalone_exception_cannot_choose_between_different_ban_owners(self):
        for prefix in (self.ban + '; а также к иностранным организациям.',
                       self.ban + '. Льгота не применяется к иностранным организациям.'):
            answer = prefix + ' Исключение — предприятия, соответствующие критериям Совета директоров.'
            with self.subTest(answer=answer):
                self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [self.clause])

    def test_standalone_exception_cannot_cross_an_intervening_topic(self):
        for bridge in ('Далее речь только о правилах другой программы.',
                       'Прямое участие 36 процентов подпадает под этот запрет.',
                       'Экспортная выручка 36 процентов подпадает под этот запрет. Далее другой вопрос.'):
            answer = self.ban + '. ' + bridge + ' Исключение — предприятия, соответствующие критериям Совета директоров.'
            with self.subTest(bridge=bridge):
                self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [self.clause])

    def test_bridge_percentage_must_satisfy_the_actual_source_operator(self):
        cases = (('не менее', '34', False), ('не менее', '35', True), ('не менее', '36', True),
                 ('не более', '34', True), ('не более', '35', True), ('не более', '36', False),
                 ('более', '35', False), ('более', '35.01', True),
                 ('менее', '35', False), ('менее', '34.99', True),
                 ('свыше', '35', False), ('свыше', '36', True))
        for operator, value, valid in cases:
            source = self.source.replace('не менее', operator)
            answer = (self.ban.replace('не менее', operator) + '. Экспортная выручка ' + value +
                      ' процентов подпадает под этот запрет. Исключение — предприятия, '
                      'соответствующие критериям Совета директоров.')
            with self.subTest(operator=operator, value=value):
                self.assertEqual(not lost_bound_numeric_exceptions(answer, self.selected(source)), valid)

    def test_bridge_is_one_exact_percentage_not_a_range_or_rounded_hint(self):
        for value in ('-36', '−36', '34–36', 'не более 36', 'около 36', 'до 36',
                      '≤36', '~36', '>=36', '≈36', '≲36'):
            answer = (self.ban + '. Экспортная выручка ' + value +
                      ' процентов подпадает под этот запрет. Исключение — предприятия, '
                      'соответствующие критериям Совета директоров.')
            with self.subTest(value=value):
                self.assertEqual(lost_bound_numeric_exceptions(answer, self.selected()), [self.clause])


if __name__ == '__main__':
    unittest.main()
