"""A qualified member of a source exclusion list cannot become its whole kind."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_policy import lost_exclusion_qualifiers


class QualifiedExclusionGuardTests(unittest.TestCase):
    source = 'рыбы живой (за исключением ценных пород: сига сибирского и амурского);'
    phrase = 'сига сибирского и амурского'

    def check(self, answer, blocked, source=None):
        selected = [SimpleNamespace(text=self.source if source is None else source)]
        found = lost_exclusion_qualifiers(answer, selected)
        self.assertEqual(bool(found), blocked, (answer, found))
        return found

    def test_bare_kind_in_asserted_exception_is_blocked(self):
        for answer in ('Исключение — сиг.', 'Исключения: сиги.', 'Кроме сига.',
                       'За исключением сигов.', 'В перечень исключений входит весь сиг.'):
            with self.subTest(answer=answer):
                self.assertEqual(self.check(answer, True), [self.phrase])

    def test_source_qualifiers_allow_case_order_parentheses_and_subset(self):
        for answer in ('Исключение — сиг сибирский и амурский.',
                       'Исключения — сибирский и амурский сиг.',
                       'Кроме сига амурского.', 'Кроме сибирского сига.',
                       'За исключением сига (сибирского и амурского).',
                       'Исключение — сиг — только амурский.',
                       'Исключения: сиги сибирские и амурские.',
                       'Кроме сига сибирского или амурского.'):
            with self.subTest(answer=answer):
                self.check(answer, False)

    def test_one_known_qualifier_cannot_hide_a_foreign_coordinated_one(self):
        for answer in ('Исключение — сиг сибирский и европейский.',
                       'Исключение — европейский и сибирский сиг.',
                       'Кроме сига амурского и северного.'):
            with self.subTest(answer=answer):
                self.check(answer, True)

    def test_separate_noun_cannot_lend_its_qualifier(self):
        self.check('Исключение — сиг и лосось сибирский.', True)
        self.check('Исключение — сибирский лосось и сиг.', True)

    def test_ordinary_subject_and_explicit_denial_are_not_positive_exception_claims(self):
        for answer in ('Для сига ставка зависит от породы.', 'Сиг не исключается.',
                       'Сиг не является исключением.', 'Исключение не распространяется на весь сиг.'):
            with self.subTest(answer=answer):
                self.check(answer, False)

    def test_closed_negated_broad_claim_with_correct_narrowing_is_allowed(self):
        self.check('Исключение — не любой сиг, а сиг сибирский и амурский.', False)
        self.check('Исключение — не весь сиг, а сибирский и амурский сиг.', False)

    def test_negation_without_real_narrowing_does_not_hide_broadening(self):
        self.check('Исключение — не только сиг, но и лосось.', True)
        self.check('Исключение — не любой сиг, а весь сиг.', True)
        self.check('Исключение — не любой сиг, а сиг сибирский и европейский.', True)

    def test_quoted_error_requires_an_explicit_correct_qualified_replacement(self):
        self.check('Фраза пользователя “Исключение — сиг” неточна: исключены сиг сибирский и амурский.', False)
        self.check('Утверждение «Исключение — сиг» неверно: исключены сибирский и амурский сиг.', False)
        self.check('Фраза пользователя “Исключение — сиг” неточна: исключён весь сиг.', True)
        self.check('Фраза пользователя “Исключение — сиг” неточна: исключены сиг сибирский и европейский.', True)

    def test_a_later_explicit_generalization_is_still_blocked(self):
        self.check('Исключение — сиг сибирский и амурский. В перечень исключений входит весь сиг.', True)

    def test_terms_are_derived_from_sources_not_specific_fish_names(self):
        source = 'Товары (за исключением отдельных видов: кабеля медного и стального).'
        self.assertEqual(self.check('Исключение — кабель.', True, source), ['кабеля медного и стального'])
        self.check('Кроме кабеля медного.', False, source)
        source = 'Услуги (за исключением особых: монтажа наружного и внутреннего).'
        self.check('Исключения — монтаж.', True, source)
        self.check('Исключение — наружный и внутренний монтаж.', False, source)

    def test_unselected_or_unsupported_source_frames_are_not_used(self):
        self.assertEqual(lost_exclusion_qualifiers('Исключение — сиг.', []), [])
        self.check('Исключение — сиг.', False, 'Общее описание сига сибирского и амурского.')
        self.check('Исключение — сиг.', False, '(за исключением видов: сига сибирского и амурского')


if __name__ == '__main__':
    unittest.main()
