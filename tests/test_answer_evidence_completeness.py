"""Publication regressions with approving stubs and source-derived dependencies.

Names, periods and clauses are synthetic. Passing these cases is not a claim
of general semantic entailment or a measured improvement in the contest score.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from test_prose_answers import run, select, confirm
from test_audit_fixes import corpus


def repeated(generate):
    return [generate, confirm(), generate, confirm()]


class AnswerEvidenceCompleteness(unittest.TestCase):
    def test_an_approving_judge_cannot_add_document_contents(self):
        source = '8.4. Оборудование возвращается по протоколу в исправном состоянии.'
        for extra in ['В протоколе фиксируется состояние оборудования.',
                      'Состояние оборудования указывается в протоколе.',
                      'Протокол содержит сведения о состоянии оборудования.',
                      'В протоколе должны быть указаны сведения о состоянии оборудования.']:
            with self.subTest(extra=extra):
                draft = 'Оборудование возвращается по протоколу. ' + extra
                text, status, model, _ = run('Как вернуть оборудование?',
                    repeated(select('8.4.', draft)), {'Прокат.txt':source})
                self.assertEqual(status, 'answer')
                self.assertNotIn(extra, text)
                self.assertIn(source, text)
                for _, payload in model.calls:
                    if 'candidate' in payload:
                        self.assertNotIn(extra, payload['rendered_answer'])
                        self.assertNotIn('answer', payload['candidate'])

    def test_explicit_document_contents_are_allowed_but_wrong_fields_are_not(self):
        source = '8.4. В протоколе фиксируется состояние оборудования.'
        draft = 'Состояние оборудования указывается в протоколе.'
        text, status, _, _ = run('Что указать в протоколе?',
            [select('8.4.', draft), confirm()], {'Прокат.txt':source})
        self.assertEqual(status, 'answer')
        self.assertTrue(text.startswith(draft))
        for other in ['Стоимость оборудования указывается в протоколе.',
                      'Состояние оборудования указывается в ведомости.']:
            text, _, _, _ = run('Что указать в протоколе?',
                repeated(select('8.4.', other)), {'Прокат.txt':source})
            self.assertNotIn(other, text)

    def test_negative_document_contents_do_not_authorize_a_positive_claim(self):
        source = '8.4. В протоколе не указывается стоимость оборудования.'
        wrong = 'В протоколе указывается стоимость оборудования.'
        text, _, _, _ = run('Что указать в протоколе?',
            repeated(select('8.4.', wrong)), {'Прокат.txt':source})
        self.assertNotIn(wrong, text)
        self.assertIn(source, text)

    def test_absence_of_other_requirements_needs_an_explicit_source(self):
        source = '7.3. К заявке прилагается ведомость об осмотре оборудования.'
        for extra in ['Иных приложений к заявке не требуется.',
                      'Порядок не требует иных приложений к заявке.',
                      'Порядок не требует отдельного разрешения.',
                      'Положений об ином комплекте документов в порядке нет.',
                      'Иного комплекта приложений не предусмотрено.',
                      'Другие документы прикладывать не нужно.',
                      'Дополнительные требования отсутствуют.']:
            with self.subTest(extra=extra):
                draft = 'К заявке прилагается ведомость об осмотре оборудования. ' + extra
                text, status, _, _ = run('Что приложить к заявке?',
                    repeated(select('7.3.', draft)), {'Порядок.txt':source})
                self.assertEqual(status, 'answer')
                self.assertNotIn(extra, text)
                self.assertIn(source, text)
        source += ' Иных приложений к заявке не требуется.'
        draft = 'Иных приложений к заявке не требуется.'
        text, _, _, _ = run('Нужны ли иные приложения?',
            [select('7.3.', draft), confirm()], {'Порядок.txt':source})
        self.assertTrue(text.startswith(draft))

    def test_sufficiency_cannot_be_inferred_from_one_requirement(self):
        source = '7.3. К заявке прилагается ведомость об осмотре оборудования.'
        wrong = 'Для заявки достаточно ведомости об осмотре оборудования.'
        text, _, _, _ = run('Что приложить к заявке?',
            repeated(select('7.3.', wrong)), {'Порядок.txt':source})
        self.assertNotIn(wrong, text)
        self.assertIn(source, text)
        text, _, _, _ = run('Что приложить к заявке?',
            [select('7.3.', wrong), confirm()], {'Порядок.txt':'7.3. '+wrong})
        self.assertTrue(text.startswith(wrong))

    def test_date_definition_is_selected_verified_and_published_even_if_model_omits_it(self):
        for days, event in [(9, 'приёмки'), (13, 'отгрузки')]:
            source = f'6.2. Проверка выполняется в течение {days} рабочих дней с даты {event}.'
            definition = f'2.8. Датой {event} считается дата подписания ведомости обеими сторонами.'
            draft = f'Проверка выполняется в течение {days} рабочих дней с даты {event}.'
            files = {'Условия.txt':definition+'\n'+source}
            text, status, model, _ = run('Когда выполнить проверку?',
                [select('6.2.', draft), confirm()], files)
            self.assertEqual(status, 'answer')
            self.assertIn(definition, text)
            self.assertIn('п. 2.8', text)
            verified = model.calls[1][1]
            self.assertEqual(verified['rendered_answer'], text)
            self.assertIn(definition, str(verified['candidate']['claims']))

    def test_date_definition_is_not_borrowed_from_another_document(self):
        source = '6.2. Проверка выполняется в течение 9 дней с даты приёмки.'
        unrelated = '2.8. Датой приёмки считается дата оплаты счета.'
        files = {'Условия.txt':source, 'Иной порядок.txt':unrelated}
        text, _, _, _ = run('Когда выполнить проверку по условиям?',
            [select('6.2.', source), confirm()], files)
        self.assertNotIn('дата оплаты', text)

    def test_inline_date_definition_cannot_disappear_from_prose(self):
        source = ('6.2. Проверка выполняется в течение 11 дней с даты передачи. '
                  'Датой передачи считается дата подписания ведомости обеими сторонами.')
        draft = 'Проверка выполняется в течение 11 дней с даты передачи.'
        text, status, model, _ = run('Когда выполнить проверку?',
            [select('6.2.', draft), confirm()], {'Условия.txt':source})
        self.assertEqual(status, 'answer')
        self.assertIn('дата подписания ведомости обеими сторонами', text)
        self.assertEqual(model.calls[1][1]['rendered_answer'], text)

    def test_missing_date_dependency_is_explicit_not_silently_omitted(self):
        files = {'Условия.txt':'2.8. Датой приёмки считается дата подписания ведомости.\n'
                             '6.2. Проверка выполняется в течение 9 дней с даты приёмки.'}
        with corpus(files) as r:
            f=next(f for f in r.search('Когда выполнить проверку?') if '6.2.' in f.text)
            with self.assertRaises(ValueError):
                r.complete_sources([{'fragment_id':f.id,'quote':f.text}], [f])

    def test_a_general_upper_bound_keeps_a_conditional_bound_for_the_same_subject(self):
        for subject, nominative in [('проверки', 'проверка'), ('испытания', 'испытание')]:
            source = f'4.1. Срок {subject} не может превышать 19 дней.'
            condition = f'4.2. При аренде на срок до месяца {nominative} не может превышать 2 дней.'
            draft = f'Срок {subject} не может превышать 19 дней.'
            with self.subTest(subject=subject):
                text, status, model, _ = run(f'Какой максимальный срок {subject}?',
                    [select('4.1.', draft), confirm()], {'Условия.txt':source+'\n'+condition})
                self.assertEqual(status, 'answer')
                self.assertIn(condition, text)
                self.assertIn(condition, str(model.calls[1][1]['candidate']['claims']))
                self.assertEqual(text, model.calls[1][1]['rendered_answer'])

    def test_conditional_bound_must_match_the_subject_and_document(self):
        source = '4.1. Срок проверки не может превышать 19 дней.'
        other_subject = '4.2. При срочном заказе срок доставки не может превышать 2 дней.'
        other_document = '4.2. При аренде на срок до месяца проверка не может превышать 3 дней.'
        text, _, _, _ = run('Какой максимальный срок проверки?',
            [select('4.1.', source), confirm()],
            {'Условия.txt':source+'\n'+other_subject, 'Иные условия.txt':other_document})
        self.assertNotIn('2 дней', text)
        self.assertNotIn('3 дней', text)

    def test_preamble_stays_in_verification_but_is_not_printed_for_a_value_question(self):
        preamble = ('ДОГОВОР ПОСТАВКИ № М-42/2031\nг. Томск — 4 мая 2031 г.\n'
                    'ООО «Орион» (ИНН 7000000000), именуемое в дальнейшем «Поставщик», '
                    'в лице директора Петрова, действующего на основании Устава, с одной стороны, и\n'
                    'ООО «Вега», именуемое в дальнейшем «Покупатель», с другой стороны,\n'
                    'заключили настоящий договор о нижеследующем.')
        provision = '7.2. Срок обслуживания определяется изготовителем и указывается в сервисном паспорте.'
        def choose(payload):
            return {'status':'answer','source_ids':[f['id'] for f in payload['evidence']],
                    'answer':'Срок обслуживания определяется изготовителем.'}
        files = {'Договор Орион.txt':preamble+'\n'+provision}
        text, status, model, _ = run('Какой срок обслуживания?', repeated(choose), files)
        self.assertEqual(status, 'partial')
        self.assertIn(provision, text)
        self.assertIn('Предоставьте', text)
        self.assertNotIn('7000000000', text)
        self.assertIn('7000000000', str(model.calls[1][1]['candidate']))
        self.assertEqual(text.count('Договор Орион.'), 1)
        # A metadata question and a preamble containing a norm must keep it.
        for question, extra in [('Кто является поставщиком и каков срок обслуживания?', ''),
                                ('Какой срок обслуживания?', '\nПредоплата запрещена.')]:
            text, _, _, _ = run(question, repeated(choose),
                {'Договор Орион.txt':preamble+extra+'\n'+provision})
            self.assertIn('7000000000', text)
            if extra:self.assertIn('Предоплата запрещена.', text)

    def test_repeated_sources_share_one_document_reference_without_cutting_conditions(self):
        first='4.2. Перевозка разрешена только после получения пропуска.'
        second='4.3. Разгрузка разрешена по соглашению сторон.'
        def choose(payload):
            return {'status':'answer','source_ids':[f['id'] for f in payload['evidence']]}
        text, status, _, _ = run('Какие условия перевозки и разгрузки?',
            [choose,confirm()], {'Правила.txt':first+'\n'+second})
        self.assertEqual(status, 'answer')
        self.assertIn(first,text);self.assertIn(second,text)
        self.assertEqual(text.count('Правила.'),1)


if __name__ == '__main__':unittest.main()
