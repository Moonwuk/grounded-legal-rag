"""Element validator and section-14 corpus contract.

Organizer reference answers are the labelled good set; each corruption changes
one meaning-bearing element and must stop the case from passing.
"""
import csv
import unittest
from evaluation.common import EVAL,ROOT,read
from evaluation.run_corpus import load,score,summarize
from evaluation.validators.elements import check,status_of,values

DEMO=EVAL/'corpora/demo'
def gold():return {c['case_id']:c for c in read(DEMO/'gold/cases.json')['cases']}
def reference():
    with (ROOT/'organizer/demo_output.csv').open(encoding='utf-8-sig',newline='') as h:return {r['id']:r['answer'] for r in csv.DictReader(h)}

# (case, old, new) on the organizer reference answer.
CORRUPTIONS=[
 ('1','450 000','540 000'),('1','5-го числа','15-го числа'),('2','шести месяцев','трёх месяцев'),
 ('4','составляет 450 000 рублей в месяц, включая НДС, а не 500 000','составляет 500 000 рублей в месяц'),
 ('5','Да.','Нет.'),('5','10 000 000','15 000 000'),('6','5 рабочих дней','5 календарных дней'),('6','5 рабочих дней','15 рабочих дней'),
 ('7','Да.','Нет.'),('7','круглосуточный ',''),('8','акта о выявленных недостатках','счёта'),('9','п. 4.2','п. 4.1'),
 ('10','руководитель подразделения','юридический отдел'),('11','трёх рабочих дней','пяти рабочих дней'),
 ('12','Да.','Нет.'),('14','Да,','Нет,'),('15','п. 6.3','п. 6.1'),('16','упаковки и ',''),
 ('17','в гарантийном талоне','в договоре: 24 месяца'),('18','трёх рабочих дней','трёх календарных дней'),('18','п. 3.2','п. 3.1'),
]

class ElementTests(unittest.TestCase):
    def test_every_organizer_reference_answer_passes(self):
        g,ref=gold(),reference()
        for cid,case in g.items():
            with self.subTest(cid):self.assertEqual(check(case,ref[cid])['outcome'],'pass',check(case,ref[cid]))

    def test_every_corruption_stops_passing(self):
        g,ref=gold(),reference()
        for cid,old,new in CORRUPTIONS:
            with self.subTest(cid=cid,new=new):
                self.assertIn(old,ref[cid]);self.assertNotEqual(check(g[cid],ref[cid].replace(old,new))['outcome'],'pass')

    def test_refusal_and_technical_statuses(self):
        g=gold()
        unverified='Не удалось получить достаточно проверенных оснований для ответа по доступным документам. Уточните договор.'
        technical='Не удалось проверить ответ из-за технической ошибки. Это не означает, что нужных сведений нет.'
        self.assertIn('false_refusal',check(g['1'],unverified)['failures'])
        self.assertEqual(check(g['1'],technical)['outcome'],'system_error')
        self.assertEqual(status_of('В найденных документах недостаточно оснований для ответа по существу.'),'insufficient')
        # A fabricated amount where the base has none is a failure even with a caveat.
        self.assertNotEqual(check(g['3'],'В базе нет документов, но обычно пособие составляет 100 000 рублей.')['outcome'],'pass')

    def test_values_units_words_and_refutation(self):
        self.assertIn((450000,'RUB',False),values('плата 450 000 (четыреста пятьдесят тысяч) рублей'))
        self.assertIn((12000000,'RUB',False),values('договор на 12 млн рублей'))
        self.assertIn((3,'working_days',False),values('не более трёх рабочих дней'))
        self.assertIn((500000,'RUB',True),values('450 000 рублей, а не 500 000 рублей'))
        self.assertEqual(values('п. 3.1 договора № А-08/2024 от 12.05.2025'),[])

class CorpusContractTests(unittest.TestCase):
    def test_demo_corpus_is_consistent_and_gold_is_not_a_question_field(self):
        meta,kb,questions,rows,cases=load(DEMO)
        self.assertEqual(len(rows),18);self.assertEqual(list(rows[0]),['id','question'])
        self.assertTrue(all(c['checked_by_hand'] is False for c in cases.values()))

    def test_missing_row_is_a_failure_and_summary_counts(self):
        g,ref=gold(),reference();answers=dict(ref);del answers['7']
        rows=score(g,answers);s=summarize(rows)
        self.assertEqual((s['passed'],s['total']),(17,18));self.assertEqual(s['failures'],{'7':['no_answer_row']})

if __name__=='__main__':unittest.main()
