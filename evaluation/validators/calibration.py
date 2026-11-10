"""Labelled answer mutations for the validator (finite, handwritten).

Used by validator tests and by every benchmark summary, so reported
FAR/FRR always describe the validator of the same commit.
"""
import copy
from evaluation.common import digest
from evaluation.validators.core import validate
from evaluation.analyze_results import ratio

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

# Restored source blocks (smoke d0a0658 fact-0000/fact-0001 structure).
def block_case(text,facts,required,forbidden=()):
    """Gold built from the document text; the runtime cites the whole block."""
    sha=digest(text.encode());sources={}
    for sid,(quote,fact) in facts.items():
        start=text.index(quote)
        sources[sid]=dict(id=sid,document='d.txt',start=start,end=start+len(quote),quote=quote,document_sha256=sha,revision='base',fact=fact)
    gold=dict(corpus_id='block',sources=sources)
    case=dict(case_id='block',category='fact',event_date=None,expected=dict(allowed_statuses=['answer'],
        required_claims=[dict(fact=facts[r][1],acceptable_evidence_sets=[[r]]) for r in required],
        forbidden_claims=list(forbidden),missing=[],issue=''))
    shown='«'+' '.join(text.split())+'»'
    c=dict(status='answer',claims=[dict(text=shown,sources=[dict(fragment_id='blk',quote=text)])],missing=[],requested_facts=[])
    out=dict(status='answer',candidate=c,answer=shown+' [1]\n[1] d.',rendered_answer=shown+' [1]\n[1] d.',mode='stub',
        documents=[dict(name='d.txt',text=text,sha256=sha,text_sha256=sha,revision='base')],
        fragments=[dict(id='blk',document='d.txt',start=0,end=len(text),text=text)])
    return case,gold,out

def fact(subject,predicate,value,unit,condition,event):
    return dict(subject_id=subject,predicate=predicate,value=value,unit=unit,condition=condition,start_event=event,valid_from=None,valid_until=None)

DUTY='Для объекта МТ-7/2031 обязанность уведомления составляет не возникает; условие: при отсутствии смены банка; событие отсчёта: сверка реквизитов.'
STORE='Для объекта МТ-7/2031 срок хранения составляет 9 рабочих дней; условие: оригинал передан курьеру; событие отсчёта: передача оригинала.'
LIMIT='Для объекта ПР-3/2032 лимит резерва составляет 81500 рублей; условие: при решении правления; событие отсчёта: утверждение сметы.'
TABLE=('MEMO № МТ-7/2031 / 0312 (ordinary)\nВымышленная организация «Учебная-7».\nПриложение Б. Таблица условий\n'
       '| Положение | Содержание |\n|---|---|\n| 1 | '+STORE+' |\n| 2 | '+DUTY+' |\n')
PROTOCOL=('FINANCIAL № ПР-3/2032 / 0044 (ordinary)\nВымышленная организация «Учебная-3». Объект ПР-3/2032.\nПРОТОКОЛ.\n'
          'СЛУШАЛИ: предложения учебной комиссии.\nРЕШИЛИ: '+LIMIT+'\n')
F_DUTY=fact('МТ-7/2031','duty',False,'boolean','при отсутствии смены банка','сверка реквизитов')
F_STORE=fact('МТ-7/2031','archive_term',9,'working_days','оригинал передан курьеру','передача оригинала')
F_LIMIT=fact('ПР-3/2032','limit',81500,'RUB','при решении правления','утверждение сметы')

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
    # Free prose outside the exact grammar, read by validators/prose.py.
    good.append(published('Срок оплаты по договору TEST-D017 для этого акта составляет 45 календарных дней после подписания акта.',
                          'Срок оплаты по договору TEST-D017 для этого акта составляет 45 календарных дней после подписания акта.\nИсточник: a.'))
    for prose in ['Срок оплаты составляет 90 календарных дней после подписания акта.',
                  'Срок оплаты составляет 45 рабочих дней после подписания акта.',
                  'Срок оплаты составляет 90 календарных дней, а не 45, после подписания акта.']:
        bad.append(published(prose,prose+'\nИсточник: a.'))
    both={'p1':(STORE,F_STORE),'p2':(DUTY,F_DUTY)}
    good.append(validate(*block_case(TABLE,both,['p2']))['outcome'])
    good.append(validate(*block_case(PROTOCOL,{'p1':(LIMIT,F_LIMIT)},['p1']))['outcome'])
    bad.append(validate(*block_case(TABLE,both,['p2'],forbidden=[F_STORE]))['outcome'])
    case,gold,out=block_case(TABLE,both,['p2'])
    out['candidate']['claims'][0]['text']=out['candidate']['claims'][0]['text'].replace('9 рабочих','90 рабочих')
    out['answer']=out['rendered_answer']=out['candidate']['claims'][0]['text'];bad.append(validate(case,gold,out)['outcome'])
    return dict(validator_false_acceptance_rate=ratio(bad.count('pass'),len(bad)),
                validator_false_rejection_rate=ratio(good.count('fail'),len(good)),
                permitted_not_evaluated=good.count('not_evaluated'),bad_outcomes=bad,good_outcomes=good,
                scope='Finite handwritten anchor mutations; not a universal semantic accuracy claim')
