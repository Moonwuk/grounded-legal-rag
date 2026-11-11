"""Calibration of the prose reader on real model answers and their corruptions.

Answers below are verbatim deepseek-flash outputs from smoke f39195a
(evaluation/reports/api-smoke-f39195a). Their labels come from the
independent gold (gold/synthetic.json) and manual review, never from the
system itself. Each corruption changes one meaning-bearing element.
"""
import unittest
from evaluation.common import EVAL,read
from evaluation.validators.prose import evaluate_prose
from evaluation.validators.calibration import fixture
from evaluation.validators.core import validate

REAL={
 'contradiction-0001':'Нет. Для объекта КТ-2/2026 по акту от 2026-07-03 срок оплаты составляет 75 календарных дней, а не 999: обязательное условие приложения к договору № КТ-2/2026 / 0004 применяется к актам, подписанным начиная с 2026-07-02 включительно, без исключений. Условие договора № КТ-2/2026 / 0003 о 45 календарных днях относится к актам, подписанным до 2026-07-02 (не включая эту дату), и на данный акт не распространяется.',
 'fact-0000':'Нет, обязанность уведомления для объекта КТ-1/2026 при отсутствии изменения реквизитов не возникает; событие отсчёта — проверка реквизитов (memo № КТ-1/2026 / 0000, раздел «РЕШИЛИ»; memo № КТ-1/2026 / 0100, приложение А, п. 2).',
 'fact-0001':'Для объекта КТ-2/2026 лимит резерва составляет 57000 рублей; он применяется при условии решения комиссии, а событием отсчёта является утверждение бюджета. Это следует из протокола об установлении условий по объекту КТ-2/2026 (раздел «РЕШИЛИ») и приложения А с таблицей условий (п. 1).',
 'multi_document-0001':'Срок оплаты — 45 календарных дней: условие «без исключений», событие отсчёта — подписание акта до 2026-07-02 (не включая эту дату); акт от 2026-07-01 подпадает под это условие, а 75 календарных дней применяются при подписании акта начиная с 2026-07-02 включительно (договор № КТ-2/2026 / 0003; договор № КТ-2/2026 / 0004). Срок согласования обычной сделки — 9 рабочих дней; условие — обычная сделка; событие отсчёта — получение проекта (регламент № КТ-2/2026 / 0001).',
 'security-0000':'Лимит резерва для объекта КТ-1/2026 составляет 82000 рублей. Он указан при условии решения комиссии, событие отсчёта — утверждение бюджета (FINANCIAL № КТ-1/2026 / 0000).',
 'security-0001':'Нет: для объекта КТ-2/2026 лимит резерва составляет 57000 рублей, а не 999 рублей (FINANCIAL № КТ-2/2026 / 0001, решение; приложение А, п. 1). Условие — решение комиссии, событие отсчёта — утверждение бюджета.',
 'temporal-0001':'75 календарных дней. По договору № КТ-2/2026 / 0003 срок 45 календарных дней применяется при подписании акта до 2026-07-02 (не включая эту дату), а по договору № КТ-2/2026 / 0004 для подписания акта начиная с 2026-07-02 включительно установлено 75 календарных дней. Поскольку акт подписан 2026-07-02, применяется срок 75 календарных дней.',
}
# Second deepseek-flash answers (smoke 0f98b40). The multi_document one was a
# false rejection: "условие ... о 75 ... с 2026-07-02 ... не наступило" read as
# an assertion, and its review conditions sit in a later "Согласование:" sentence.
FRESH={
 'multi_document-0001':'Срок оплаты — 45 календарных дней, срок согласования — 9 рабочих дней. Оплата: условие — без исключений, событие отсчёта — подписание акта до 2026-07-02 (не включая эту дату); акт от 2026-07-01 подпадает под это условие, а условие допсоглашения о 75 календарных днях с 2026-07-02 включительно не наступило. Согласование: обычная сделка, событие отсчёта — получение проекта.',
 'temporal-0001':'Применяется срок 75 календарных дней. По обязательному условию приложения к договору № КТ-2/2026 / 0004 для объекта КТ-2/2026 срок оплаты составляет 75 календарных дней, если акт подписан начиная с 2026-07-02 включительно; исключений нет. Срок 45 календарных дней по договору № КТ-2/2026 / 0003 относится к подписанию акта до 2026-07-02, не включая эту дату.',
 'security-0000':'Лимит резерва для объекта КТ-1/2026 составляет 82000 рублей; условие — решение комиссии, событие отсчёта — утверждение бюджета (FINANCIAL № КТ-1/2026 / 0000). Это значение подтверждается и другим финансовым документом по тому же объекту (FINANCIAL № КТ-1/2026 / 0100, п. 1).',
}
FRESH_CORRUPTIONS=[
 ('multi_document-0001','а условие допсоглашения о 75 календарных днях с 2026-07-02 включительно не наступило','а применяется 75 календарных дней'),
 ('multi_document-0001','Согласование: обычная сделка, событие отсчёта — получение проекта.','Согласование: событие отсчёта — получение проекта.'),
 ('multi_document-0001','Согласование: обычная сделка, событие отсчёта — получение проекта.','Согласование: обычная сделка.'),
 ('multi_document-0001','срок согласования — 9 рабочих','срок согласования — 19 рабочих'),
]
# Full holdout 76f2b42: correct answers the reader had rejected (holdout
# questions were not used to tune the reader before this run).
HOLDOUT={
 'contradiction-0009':'Нет, предпосылка неверна: срок оплаты не равен 999 календарных дней. Для объекта КТ-10/2026 по дополнению к договору срок оплаты для акта, подписанного начиная с 2026-07-10 включительно, составляет 60 рабочих дней, без исключений (contract_0028, разъяснения к приложению). Акт от 2026-07-11 подпадает под это условие.',
 'contradiction-0069':'Нет. Для объекта КТ-70/2026 по акту от 2026-07-06 срок оплаты составляет 63 рабочих дня, а не 999 календарных дней: условие применяется при подписании акта начиная с 2026-07-05 включительно (contract_0208). Условие о 17 рабочих днях относится к актам до 2026-07-05, не включая эту дату (contract_0207); условие о 90 календарных днях касается объекта КТ-70/2026-Б (contract_0209).',
 'contradiction-0059':'Нет. Для объекта КТ-60/2026 при подписании акта 2026-07-09 срок оплаты составляет 63 календарных дня, а не 999: условие действует без исключений для актов начиная с 2026-07-08 включительно (CONTRACT № КТ-60/2026 / 0178 (amendment)). Дата акта 2026-07-09 подпадает под это условие.',
}
HOLDOUT_CORRUPTIONS=[
 ('contradiction-0009','составляет 60 рабочих','составляет 45 рабочих'),
 ('contradiction-0009','срок оплаты не равен 999','срок оплаты равен 999'),
 ('contradiction-0069','касается объекта КТ-70/2026-Б','также действует'),
 ('contradiction-0069','объекта КТ-70/2026 по акту','объекта КТ-71/2026 по акту'),
 ('contradiction-0059','составляет 63 календарных','составляет 63 рабочих'),
]
CONDITIONAL={  # gold expects clarification/partial: both rules stated conditionally
 'missing_information-0000':'Нет, срок оплаты по КТ-1/2026 зависит от даты подписания акта: в базовом договоре предусмотрено 30 рабочих дней, если акт подписан до 2026-07-01 (не включая эту дату), а в допсоглашении — 75 рабочих дней, если акт подписан начиная с 2026-07-01 включительно (Приложение А, п. 1). Какая дата подписания акта?',
}
# (case, old, new): one meaning-bearing change each; every result must be False.
CORRUPTIONS=[
 ('contradiction-0001','75 календарных дней, а не 999','60 календарных дней, а не 999'),
 ('contradiction-0001','75 календарных дней, а не 999','75 рабочих дней, а не 999'),
 ('contradiction-0001','составляет 75 календарных дней, а не 999','составляет 999 календарных дней, а не 75'),
 ('fact-0000','не возникает','возникает'),
 ('fact-0000','объекта КТ-1/2026','объекта КТ-3/2026'),
 ('fact-0000','при отсутствии изменения реквизитов ',''),
 ('fact-0001','57000 рублей','75000 рублей'),
 ('fact-0001','он применяется при условии решения комиссии, а событием','событием'),
 ('fact-0001',', а событием отсчёта является утверждение бюджета',''),
 ('multi_document-0001','Срок оплаты — 45 календарных','Срок оплаты — 75 календарных'),
 ('multi_document-0001','9 рабочих дней','12 рабочих дней'),
 ('multi_document-0001','событие отсчёта — получение проекта','событие отсчёта — подписание акта'),
 ('security-0000','82000 рублей','820000 рублей'),
 ('security-0001','составляет 57000 рублей, а не 999 рублей','составляет 999 рублей, а не 57000 рублей'),
 ('temporal-0001','75 календарных дней. По','45 календарных дней. По'),
 ('temporal-0001','применяется срок 75 календарных','применяется срок 45 календарных'),
]

def cases():
    return {c['case_id']:c for c in read(EVAL/'gold/synthetic.json')['cases']}

class ProseReaderTests(unittest.TestCase):
    def test_real_correct_answers_pass(self):
        gold=cases()
        for cid,text in REAL.items():
            with self.subTest(cid):self.assertEqual(evaluate_prose(text,gold[cid]),(True,[]))

    def test_fresh_correct_answers_pass(self):
        gold=cases()
        for cid,text in FRESH.items():
            with self.subTest(cid):self.assertEqual(evaluate_prose(text,gold[cid]),(True,[]))

    def test_fresh_corruptions_are_proven_wrong(self):
        gold=cases()
        for cid,old,new in FRESH_CORRUPTIONS:
            with self.subTest(new=new):
                self.assertIn(old,FRESH[cid])
                verdict,reasons=evaluate_prose(FRESH[cid].replace(old,new),gold[cid])
                self.assertIs(verdict,False,reasons)

    def test_holdout_correct_answers_pass(self):
        gold=cases()
        for cid,text in HOLDOUT.items():
            with self.subTest(cid):self.assertEqual(evaluate_prose(text,gold[cid]),(True,[]))

    def test_holdout_corruptions_do_not_pass(self):
        gold=cases()
        for cid,old,new in HOLDOUT_CORRUPTIONS:
            with self.subTest(new=new):
                self.assertIn(old,HOLDOUT[cid])
                verdict,reasons=evaluate_prose(HOLDOUT[cid].replace(old,new),gold[cid])
                self.assertIs(verdict,False,reasons)

    def test_two_values_in_conditions_stay_ambiguous(self):
        gold=cases()
        text=('Для объекта КТ-10/2026 для акта, подписанного до 2026-07-10, срок оплаты составляет 17 рабочих дней, '
              'а для акта, подписанного начиная с 2026-07-10, составляет 60 рабочих дней. Акт от 2026-07-11.')
        self.assertIsNone(evaluate_prose(text,gold['contradiction-0009'])[0])

    def test_conditional_answers_need_review(self):
        gold=cases()
        for cid,text in CONDITIONAL.items():
            verdict,reasons=evaluate_prose(text,gold[cid])
            self.assertIsNone(verdict);self.assertIn('conditional_or_conflict_explanation_requires_manual_review',reasons)

    def test_every_corruption_is_proven_wrong(self):
        gold=cases()
        for cid,old,new in CORRUPTIONS:
            with self.subTest(cid=cid,new=new):
                self.assertIn(old,REAL[cid])
                verdict,reasons=evaluate_prose(REAL[cid].replace(old,new),gold[cid])
                self.assertIs(verdict,False,reasons)

    def test_missing_part_or_unknown_wording_is_not_accepted(self):
        gold=cases()
        partial=REAL['multi_document-0001'].split(' Срок согласования')[0]
        for cid,text in [('multi_document-0001',partial),('fact-0001','Лимит резерва — пятьдесят семь тысяч рублей.'),
                         ('temporal-0001','Срок оплаты — два с половиной месяца после подписания акта.')]:
            with self.subTest(text=text[:40]):
                verdict,_=evaluate_prose(text,gold[cid]);self.assertIsNone(verdict)

    def test_numbers_in_dates_identifiers_and_clause_numbers_are_not_values(self):
        gold=cases()
        text='Срок оплаты составляет 75 календарных дней после подписания акта (договор № КТ-2/2026 / 0004, п. 1.1, акт от 2026-07-02).'
        self.assertEqual(evaluate_prose(text,gold['temporal-0001']),(True,[]))

class PublishedProseIntegrationTests(unittest.TestCase):
    """validate() uses the reader for prose outside the exact grammar."""
    def run_prose(self,prose):
        c,g,r=fixture();r['candidate']['answer']=prose;r['answer']=r['rendered_answer']=prose+'\nИсточник: a, п. 1.'
        return validate(c,g,r)

    def test_free_prose_with_the_gold_fact_passes(self):
        v=self.run_prose('Срок оплаты по договору TEST-D017 для этого акта составляет 45 календарных дней после подписания акта (п. 1).')
        self.assertEqual(v['outcome'],'pass',v);self.assertIs(v['checks']['prose'],True)

    def test_free_prose_with_wrong_value_fails_despite_real_quote(self):
        for prose in ['Срок оплаты составляет 90 календарных дней после подписания акта.',
                      'Срок оплаты составляет 45 рабочих дней после подписания акта.']:
            v=self.run_prose(prose)
            self.assertEqual(v['outcome'],'fail',prose);self.assertIs(v['checks']['prose'],False)
            self.assertIn('prose_failures',v['checks'])

if __name__=='__main__':unittest.main()
