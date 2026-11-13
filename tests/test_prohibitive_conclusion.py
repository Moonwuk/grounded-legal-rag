"""A conclusion that only prohibits need not repeat the conditions of a permission.

24-question run on 06a3dda and a fixed version, question N17 (pregnant
employee who consented in writing to overtime): the article prohibits overtime
for pregnant women and, in the next sentence, permits it for other categories
«только с их письменного согласия и при условии …». Verified texts «Нет.
Привлечение беременных женщин … не допускается; письменное согласие значения
не имеет» were dropped because they lacked «только» and «при условии»; the
answer was the bare quotation, without «Нет».

These classes qualify a permission. A text that permits nothing cannot loosen
them. Every class is still required once the text permits something, and a
prohibition with an exception must keep the exception. The source provisions
are published below the text in every case.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import restrictions_kept  # noqa: E402

NIGHT = [Fragment('n', 'Кодекс о труде.txt', 0, 300,
                  'Не допускается привлечение к ночной работе работников моложе восемнадцати лет. '
                  'Привлечение к ночной работе инвалидов допускается только с их письменного согласия и при условии, '
                  'что это не запрещено им медицинским заключением.', '')]
TRAVEL = [Fragment('t', 'Положение о поездках.txt', 0, 200,
                   '4.2. Командирование стажёров запрещено, за исключением поездок на обучение.', '')]
LEASE = [Fragment('l', 'Договор аренды.txt', 0, 200,
                  '4.2. Арендатор не вправе сдавать Помещение в субаренду без письменного согласия Арендодателя; '
                  'субаренда допускается только по соглашению сторон.', '')]


class ProhibitiveConclusionTests(unittest.TestCase):
    def test_pure_prohibition_is_kept(self):
        for text in ('Нет. Привлечение работника моложе восемнадцати лет к ночной работе не допускается; '
                     'его письменное согласие значения не имеет.',
                     'Нет, нельзя: закон прямо запрещает ночную работу для несовершеннолетних, согласие этого не меняет.',
                     'Нет. Ночная работа несовершеннолетнего не допускается даже при наличии его письменного согласия.'):
            with self.subTest(text):
                self.assertTrue(restrictions_kept(text, NIGHT))

    def test_permission_still_needs_every_condition(self):
        for text in ('Да, инвалида можно привлечь к ночной работе с его письменного согласия.',
                     'Несовершеннолетних привлекать нельзя, а инвалидов можно с их письменного согласия.',
                     'Инвалид вправе работать ночью, если согласен.'):
            with self.subTest(text):
                self.assertFalse(restrictions_kept(text, NIGHT))
        self.assertTrue(restrictions_kept(
            'Несовершеннолетних привлекать нельзя; инвалидов допускается только с их письменного согласия '
            'и при условии, что это не запрещено медицинским заключением.', NIGHT))

    def test_prohibition_must_keep_its_exception(self):
        self.assertFalse(restrictions_kept('Нет, командирование стажёров запрещено.', TRAVEL))
        self.assertTrue(restrictions_kept(
            'Нет, командирование стажёров запрещено, за исключением поездок на обучение.', TRAVEL))

    def test_negated_permission_words_are_not_permissions(self):
        # «не вправе … без согласия» prohibits; «по соглашению» qualifies the permission in the source.
        self.assertTrue(restrictions_kept('Нет. Арендатор не вправе сдавать помещение в субаренду без письменного '
                                          'согласия арендодателя; устного разрешения недостаточно.', LEASE))
        self.assertFalse(restrictions_kept('Да, субаренда допускается, если арендодатель согласен.', LEASE))


if __name__ == '__main__':
    unittest.main()
