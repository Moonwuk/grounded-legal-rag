"""Restriction classes kept in other words; conditions the question states as met.

One-call runs of 13 November, texts dropped to bare quotations:
- «при одном смягчающем обстоятельстве штраф уменьшается не менее чем в два…»
  for «При наличии хотя бы одного смягчающего … обстоятельства» — the question
  said one mitigating circumstance was established; the text had no «при наличии»;
- «Освобождение не распространяется на организации, применяющие УСН» for
  «… за исключением организаций, применяющих …» — no literal «за исключением»;
- «за исключением случаев, предусмотренных настоящим Кодексом / частями 2,
  11–18 настоящей статьи» — a reference to other provisions, required verbatim;
- «только, если работы длятся до двух месяцев» for «временных (до двух
  месяцев) работ» — rejected as an added «только».
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import lost_restrictions, prose_scope_safe, restrictions_kept  # noqa: E402

FINE = [Fragment('f', 'd', 0, 1, '3. При наличии хотя бы одного смягчающего ответственность обстоятельства размер взыскания '
                 'подлежит уменьшению не менее чем в три раза.', '')]
RELIEF = [Fragment('r', 'd', 0, 1, '1. Предприятия, за исключением предприятий, применяющих патентную систему, имеют право '
                   'на льготу, если выручка не превысила 5 миллионов рублей.', '')]
BOILER = [Fragment('b', 'd', 0, 1, '1. Нарушение порядка хранения сведений, за исключением случаев, предусмотренных частями 4 и '
                   '7 настоящей статьи, влечет штраф для юридических лиц от 40 тысяч до 90 тысяч рублей.', '')]


class RestrictionParaphraseTests(unittest.TestCase):
    def test_condition_stated_as_met_in_the_question(self):
        question = 'Исходное взыскание 90 000 рублей, установлено одно смягчающее обстоятельство. Какой размер?'
        text = 'Взыскание уменьшается не менее чем в три раза: 90 000 / 3 = 30 000 рублей.'
        self.assertTrue(restrictions_kept(text, FINE, question=question))
        # Without the fact in the question, the condition must be stated.
        self.assertFalse(restrictions_kept(text, FINE, question='Какой размер взыскания?'))
        self.assertTrue(restrictions_kept('Если есть смягчающее обстоятельство, взыскание уменьшается не менее чем в три раза.',
                                          FINE, question='Какой размер взыскания?'))

    def test_exception_in_other_words(self):
        question = 'Предприятие на общей системе, выручка 4 млн. Есть ли право на льготу?'
        for text in ('Да, если выручка не превысила 5 миллионов рублей; льгота не распространяется на предприятия на патенте.',
                     'Да, если выручка не превысила 5 миллионов рублей, кроме предприятий на патентной системе.'):
            with self.subTest(text):
                self.assertTrue(restrictions_kept(text, RELIEF, question=question))
        self.assertFalse(restrictions_kept('Да, если выручка не превысила 5 миллионов рублей.', RELIEF, question=question))
        self.assertIn('за исключением', lost_restrictions('Да, если выручка не превысила 5 миллионов рублей.', RELIEF, question))

    def test_reference_exception_is_not_required(self):
        text = 'Штраф для юридического лица — от 40 тысяч до 90 тысяч рублей.'
        self.assertTrue(restrictions_kept(text, BOILER, question='Какой штраф по части 1?'))

    def test_only_restating_a_source_bound(self):
        src = [Fragment('t', 'd', 0, 1, 'Договор заключается на время выполнения сезонных (до четырёх месяцев) работ;', '')]
        self.assertTrue(prose_scope_safe('Нет, только если работы длятся до четырёх месяцев.', src))
        self.assertFalse(prose_scope_safe('Нет, только до пяти месяцев.', src))
        self.assertFalse(prose_scope_safe('Договор заключается только с совершеннолетними.', src))


if __name__ == '__main__':
    unittest.main()
