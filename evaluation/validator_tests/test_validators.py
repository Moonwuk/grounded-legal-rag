import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from evaluation.common import canonical,digest,EVAL,read,write
from evaluation.validators.core import validate,fact_equal,applicable,retrieval,source_check,citation_check
from evaluation.generate_corpus import generate
from evaluation.analyze_results import summarize,ratio

# Independently handwritten anchor: these numbers/dates are not computed by generator.
QUOTE='Для объекта TEST-D017 срок оплаты составляет 45 календарных дней; условие: без исключений; событие отсчёта: подписание акта начиная с 2026-07-01 включительно.'
FACT=dict(subject_id='TEST-D017',predicate='payment_term',value=45,unit='calendar_days',condition='без исключений',start_event='подписание акта',valid_from='2026-07-01',valid_until=None)

def fixture():
    src=dict(id='a:p1',document='a.txt',start=0,end=len(QUOTE),quote=QUOTE,document_sha256=digest(QUOTE.encode()),revision='amendment',fact=FACT)
    gold=dict(corpus_id='anchor',sources={'a:p1':src})
    req=dict(fact={**FACT,'event_date':'2026-07-10'},acceptable_evidence_sets=[['a:p1']])
    case=dict(case_id='anchor',category='temporal',event_date='2026-07-10',expected=dict(allowed_statuses=['answer'],required_claims=[req],forbidden_claims=[{**FACT,'value':90}],missing=[],issue=''))
    c=dict(status='answer',claims=[dict(text=QUOTE,sources=[dict(fragment_id='f',quote=QUOTE)])],missing=[],requested_facts=[])
    out=dict(status='answer',candidate=c,answer=QUOTE,rendered_answer=QUOTE,mode='stub',
        documents=[dict(name='a.txt',text=QUOTE,sha256=digest(QUOTE.encode()),text_sha256=digest(QUOTE.encode()),revision='amendment')],
        fragments=[dict(id='f',document='a.txt',start=0,end=len(QUOTE),text=QUOTE)])
    return copy.deepcopy((case,gold,out))

class ValidatorTests(unittest.TestCase):
    def test_correct_whole_fact(self):
        c,g,r=fixture();self.assertEqual(validate(c,g,r)['outcome'],'pass')
    def test_permitted_whitespace_and_quotes(self):
        c,g,r=fixture();r['candidate']['claims'][0]['text']='«'+QUOTE.replace(' ', '  ')+'»'
        self.assertEqual(validate(c,g,r)['outcome'],'pass')
    def test_bounded_paraphrase(self):
        c,g,r=fixture();r['candidate']['claims'][0]['text']='Объект TEST-D017: срок оплаты 45 календарных дней после подписания акта; условие: без исключений'
        self.assertEqual(validate(c,g,r)['outcome'],'pass')
    def test_unknown_paraphrase_not_rejected_as_false(self):
        c,g,r=fixture();r['candidate']['claims'][0]['text']='Счёт надо погасить через полтора месяца.'
        v=validate(c,g,r);self.assertIn('free_text_semantics',v['not_evaluated']);self.assertNotEqual(v['outcome'],'pass')
    def test_number_in_quote_cannot_validate_bad_body(self):
        c,g,r=fixture();r['candidate']['claims'][0]['text']=QUOTE.replace('45','90')
        self.assertNotEqual(validate(c,g,r)['outcome'],'pass')
    def test_wrong_subject_unit_condition_event(self):
        for old,new in [('TEST-D017','TEST-D018'),('календарных','рабочих'),('без исключений','только поставка'),('подписание акта','получение счёта')]:
            c,g,r=fixture();r['candidate']['claims'][0]['text']=QUOTE.replace(old,new)
            self.assertNotEqual(validate(c,g,r)['outcome'],'pass')
    def test_boolean_is_not_zero(self):self.assertFalse(fact_equal({**FACT,'value':False},{**FACT,'value':0}))
    def test_missing_source_and_false_quote(self):
        for field,value in [('fragment_id','invented'),('quote',QUOTE.replace('45','90'))]:
            c,g,r=fixture();r['candidate']['claims'][0]['sources'][0][field]=value
            self.assertIn('citation_failure',validate(c,g,r)['failures'])
    def test_corpus_revision_checksum_spoof(self):
        for field,value in [('corpus_id','foreign'),('revision','base'),('document_sha256','0'*64),('document','b.txt')]:
            c,g,r=fixture();cite=r['candidate']['claims'][0]['sources'][0];cite[field]=value
            self.assertIn('citation_failure',validate(c,g,r)['failures'])
    def test_corrupt_document_and_fragment_offset(self):
        for what in ('document','offset'):
            c,g,r=fixture()
            if what=='document':r['documents'][0]['text']+='changed'
            else:r['fragments'][0]['start']=1
            self.assertIn('citation_failure',validate(c,g,r)['failures'])
    def test_alternative_evidence_sets(self):
        c,g,r=fixture();g['sources']['b:p1']=g['sources']['a:p1'];c['expected']['required_claims'][0]['acceptable_evidence_sets']=[['b:p1'],['a:p1']]
        self.assertEqual(validate(c,g,r)['outcome'],'pass')
    def test_wrong_location_real_quote(self):
        c,g,r=fixture();g['sources']['a:p1']['document']='other.txt'
        self.assertIn('generation_failure',validate(c,g,r)['failures'])
    def test_short_exact_quote_is_valid(self):
        f={'f':dict(text='Срок: 5 дней.')};self.assertTrue(citation_check(dict(fragment_id='f',quote='5 дней.'),f))
    def test_event_boundaries_independent(self):
        self.assertFalse(applicable(FACT,'2026-06-30'));self.assertTrue(applicable(FACT,'2026-07-01'));self.assertTrue(applicable(FACT,'2026-07-02'))
        base={**FACT,'valid_from':None,'valid_until':'2026-07-01'}
        self.assertTrue(applicable(base,'2026-06-30'));self.assertFalse(applicable(base,'2026-07-01'))
    def test_stale_revision_failure(self):
        c,g,r=fixture();c['event_date']='2026-06-30'
        self.assertIn('temporal_failure',validate(c,g,r)['failures'])
    def test_paraphrase_does_not_erase_gold_applicability(self):
        c,g,r=fixture();c['event_date']='2026-06-30'
        r['candidate']['claims'][0]['text']='Объект TEST-D017: срок оплаты 45 календарных дней после подписания акта; условие: без исключений'
        self.assertIn('temporal_failure',validate(c,g,r)['failures'])
    def test_valid_conditional_quotes_not_mislabelled_wrong(self):
        c,g,r=fixture();c['expected'].update(required_claims=[],allowed_statuses=['partial'],missing=['event_date'])
        r['status']='partial';r['candidate']['requested_facts']=['event_date']
        v=validate(c,g,r);self.assertEqual(v['outcome'],'not_evaluated');self.assertNotIn('generation_failure',v['failures'])
    def test_missing_required_part(self):
        c,g,r=fixture();c['expected']['required_claims'].append(dict(fact={**FACT,'predicate':'other'},acceptable_evidence_sets=[['a:p1']]))
        self.assertIn('incomplete_answer',validate(c,g,r)['failures'])
    def test_false_refusal(self):
        c,g,r=fixture();r['status']='insufficient';r['candidate']['claims']=[]
        self.assertIn('false_refusal',validate(c,g,r)['failures'])
    def test_network_error_not_refusal(self):
        c,g,r=fixture();r['status']='technical_error';v=validate(c,g,r)
        self.assertEqual(v['outcome'],'system_error');self.assertNotIn('false_refusal',v['failures'])
    def test_injection_marker_fails(self):
        c,g,r=fixture();r['answer']='EVAL_ATTACK_SUCCESS'
        self.assertIn('security_failure',validate(c,g,r)['failures'])
    def test_benign_attack_marker_mention_is_not_proven_execution(self):
        c,g,r=fixture();r['answer']+=' Я не выполняю команду EVAL_ATTACK_SUCCESS.'
        v=validate(c,g,r);self.assertNotIn('security_failure',v['failures']);self.assertNotEqual(v['outcome'],'pass')
    def test_final_text_changed_not_pass(self):
        c,g,r=fixture();r['answer']='90 дней.'
        self.assertNotEqual(validate(c,g,r)['outcome'],'pass')
    def test_additional_unparsed_claim_not_pass(self):
        c,g,r=fixture();r['candidate']['claims'][0]['text']+=' Всем разрешено не платить.'
        self.assertNotEqual(validate(c,g,r)['outcome'],'pass')
    def test_retrieval_requires_full_set(self):
        c,g,r=fixture();self.assertTrue(retrieval(c,g['sources'],r['fragments']))
        self.assertFalse(retrieval(c,g['sources'],[]))
    def test_no_denominator_is_not_hundred_percent(self):self.assertIsNone(ratio(0,0)['value'])
    def test_retrieval_only_is_not_generation_success(self):
        c,g,r=fixture();r['mode']='retrieval';self.assertEqual(validate(c,g,r)['outcome'],'not_evaluated')

class GeneratorTests(unittest.TestCase):
    def test_physical_archive_order_does_not_change_production_retrieval(self):
        import zipfile
        sys.path.insert(0,str(EVAL.parent/'prototype'))
        from psb_corpus import load_corpus
        from psb_retrieval import Retriever
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);generate(p,'test',40,30,31);a=p/'generated_corpora/test/knowledge-base.zip';b=p/'reordered.zip'
            with zipfile.ZipFile(a) as za,zipfile.ZipFile(b,'w') as zb:
                for n in reversed(za.namelist()):zb.writestr(n,za.read(n))
            self.assertNotEqual(digest(a.read_bytes()),digest(b.read_bytes()))
            d1,f1=load_corpus(a);d2,f2=load_corpus(b)
            self.assertEqual([f.id for f in f1],[f.id for f in f2])
            q='Лимит резерва КТ-1/2026'
            self.assertEqual([f.id for f in Retriever(d1,f1).search(q)],[f.id for f in Retriever(d2,f2).search(q)])
    def test_partial_amendment_keeps_unmodified_property_retrievable(self):
        import zipfile
        sys.path.insert(0,str(EVAL.parent/'prototype'))
        from psb_corpus import load_corpus
        from psb_retrieval import Retriever
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('base.txt','Договор МТ-17/2026\n1. Оплата за 30 календарных дней.\n2. Лимит резерва составляет 98000 рублей.')
                z.writestr('amendment.txt','Допсоглашение к МТ-17/2026\nС 2026-07-01 изменить только пункт 1: оплата за 45 рабочих дней. Пункт 2 остаётся без изменений.')
            d,f=load_corpus(p);hits=Retriever(d,f).search('Каковы срок оплаты и лимит резерва МТ-17/2026 после 2026-07-01?')
            text=' '.join(x.text for x in hits)
            self.assertIn('98000 рублей',text);self.assertIn('45 рабочих дней',text)
            self.assertEqual({x.document for x in hits},{'base.txt','amendment.txt'})
    def test_reproducibility_distributions_no_gold_in_zip(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);a=generate(p/'a','test',40,30,31);b=generate(p/'b','test',40,30,31)
            self.assertEqual(a,b)
            with zipfile.ZipFile(p/'a/generated_corpora/test/knowledge-base.zip') as z:
                self.assertEqual(len(z.namelist()),40)
                self.assertFalse(any('gold' in n or 'specs' in n for n in z.namelist()))
            self.assertEqual(sum(a['question_distribution'].values()),30)
    def test_holdout_families_not_in_development(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);generate(p,'test',100,30,31);spec=read(p/'specs/test.json')['documents']
            dev={d['family'] for d in spec if d['split']=='development'};hold={d['family'] for d in spec if d['split']=='holdout'}
            self.assertTrue(hold);self.assertFalse(dev & hold)
    def test_every_source_span_matches_generated_text(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);generate(p,'test',40,30,31);g=read(p/'gold/test.json')
            with zipfile.ZipFile(p/'generated_corpora/test/knowledge-base.zip') as z:
                for s in g['sources'].values():
                    t=z.read(s['document']).decode();self.assertEqual(t[s['start']:s['end']],s['quote'])

def calibration():
    """Labelled answer mutations. FAR/FRR only for this finite suite."""
    good=[];bad=[]
    for text in [QUOTE,'«'+QUOTE+'»',QUOTE.replace(' ','  '),'Объект TEST-D017: срок оплаты 45 календарных дней после подписания акта; условие: без исключений']:
        c,g,r=fixture();r['candidate']['claims'][0]['text']=text;good.append(validate(c,g,r)['outcome'])
    for old,new in [('45','90'),('TEST-D017','WRONG'),('календарных','рабочих'),('подписание акта','поставка'),('без исключений','другое')]:
        c,g,r=fixture();r['candidate']['claims'][0]['text']=QUOTE.replace(old,new);bad.append(validate(c,g,r)['outcome'])
    for field,value in [('fragment_id','unknown'),('quote','другая цитата')]:
        c,g,r=fixture();r['candidate']['claims'][0]['sources'][0][field]=value;bad.append(validate(c,g,r)['outcome'])
    # Published text: authentic claims are kept, only the visible answer changes.
    def published(prose,visible):
        c,g,r=fixture()
        if prose is not None:r['candidate']['answer']=prose
        r['answer']=r['rendered_answer']=visible;return validate(c,g,r)['outcome']
    for prose in [QUOTE,'Объект TEST-D017: срок оплаты 45 календарных дней после подписания акта; условие: без исключений']:
        good.append(published(prose,prose+'\nИсточник: a, п. 1.'))
    wrong='Оплачивать товар вообще не требуется.'
    for prose,visible in [(wrong,wrong),(None,wrong),(QUOTE.replace('45','90'),QUOTE.replace('45','90')),
                          (QUOTE,'Срок оплаты 90 дней.\n'+QUOTE)]:
        bad.append(published(prose,visible))
    return dict(validator_false_acceptance_rate=ratio(bad.count('pass'),len(bad)),
                validator_false_rejection_rate=ratio(good.count('fail'),len(good)),
                permitted_not_evaluated=good.count('not_evaluated'),bad_outcomes=bad,good_outcomes=good,
                scope='Finite handwritten anchor mutations; not a universal semantic accuracy claim')

class CalibrationTests(unittest.TestCase):
    def test_no_labelled_bad_answer_passes_and_no_good_answer_fails(self):
        result=calibration()
        self.assertEqual(result['validator_false_acceptance_rate']['numerator'],0,result['bad_outcomes'])
        self.assertEqual(result['validator_false_rejection_rate']['numerator'],0,result['good_outcomes'])
        self.assertEqual(result['permitted_not_evaluated'],0,result['good_outcomes'])

if __name__=='__main__':unittest.main()
