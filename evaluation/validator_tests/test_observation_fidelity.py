"""Regressions for the worker observing the real runtime and the published text.

The scripted model below is a controlled stub, not a quality measurement of any
real model. It approves whatever it is given so that differences in the
result can come only from the observation code path.
"""
import contextlib
import copy
import dataclasses
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from evaluation.common import ROOT,EVAL,archive
sys.path[:0]=[str(ROOT/'prototype'),str(EVAL/'adapters')]
from psb_corpus import load_corpus
from psb_retrieval import Retriever
from psb_policy import answer_question
import worker
from evaluation.validators.calibration import fixture,QUOTE,block_case,TABLE,PROTOCOL,DUTY,STORE,LIMIT,F_DUTY,F_STORE,F_LIMIT
from evaluation.validators.core import validate

# Two independent variants of one defect class: a value that the contract
# delegates to a separate document which IS present in the corpus. Names,
# numbers and wording differ so the regression does not encode one string.
SCENARIOS=[
    dict(files={
        'документы компании__Договор сервиса С-12-2031.txt':
            'Договор сервисного обслуживания № С-12/2031\nСтороны: ООО «Альфа-Тест» и ООО «Бета-Тест».\n'
            '7. Сервис\n7.1. Сервис выполняется на территории заказчика.\n'
            '7.2. Срок сервисного обслуживания определяется изготовителем и указывается в сервисном паспорте.\n',
        'документы компании__Сервисный паспорт С-12-2031.txt':
            'Сервисный паспорт к договору № С-12/2031\n1. Сроки\n1.1. Срок сервисного обслуживания составляет 19 месяцев.\n'},
        question='Какой срок сервисного обслуживания по договору С-12/2031?',
        markers=('19 месяцев','указывается в сервисном паспорте'),
        prose='Срок сервисного обслуживания составляет 19 месяцев (п. 1.1).'),
    dict(files={
        'документы компании__Договор поставки П-4-2032.txt':
            'Договор поставки № П-4/2032\nСтороны: АО «Гамма-Тест» и ООО «Дельта-Тест».\n'
            '5. Гарантия\n5.1. Гарантия распространяется на поставленный товар.\n'
            '5.3. Срок гарантии устанавливается производителем и указывается в технической спецификации.\n',
        'документы компании__Техническая спецификация П-4-2032.txt':
            'Техническая спецификация к договору № П-4/2032\n2. Гарантия\n2.4. Срок гарантии составляет 27 месяцев.\n'},
        question='Какой срок гарантии по договору П-4/2032?',
        markers=('27 месяцев','указывается в технической спецификации'),
        prose='Срок гарантии составляет 27 месяцев (п. 2.4).'),
]

class ScriptedClient:
    """Selects provisions by marker text and approves every candidate."""
    def __init__(self,markers,prose):
        self.markers=markers;self.prose=prose
        self.events=[];self.attempts=0;self.usage=[];self.errors=[]
    def complete(self,system,payload):
        self.attempts+=1
        if 'candidate' in payload:
            c=payload['candidate']
            value=dict(approved=True,complete=True,status=c['status'],answer_supported=True,
                       claim_checks=[dict(index=i,supported=True,applicable=True) for i in range(len(c['claims']))])
        else:
            ids=[f['id'] for m in self.markers for f in payload['evidence'] if m in f['text']]
            value=dict(status='answer',answer=self.prose,source_ids=list(dict.fromkeys(ids)),requested_facts=[],issue='')
        self.events.append(dict(payload=payload,response=value))
        return value

def corpus(tmp,files):
    path=Path(tmp)/'knowledge-base.zip';archive(path,files)
    return path,*load_corpus(path,time.monotonic()+30)

class ObservationFidelityTests(unittest.TestCase):
    def test_wrapper_forwards_every_public_retriever_member(self):
        for s in SCENARIOS:
            with tempfile.TemporaryDirectory() as tmp:
                _,docs,frags=corpus(tmp,s['files'])
                direct=Retriever(docs,frags,time.monotonic()+30);traced=worker.TracedRetriever(direct)
                for name in [n for n in dir(direct) if not n.startswith('_')]:
                    self.assertTrue(hasattr(traced,name),name)
                self.assertIs(traced.documents,direct.documents)

    def test_observed_policy_equals_direct_policy(self):
        for s in SCENARIOS:
            with self.subTest(s['question']),tempfile.TemporaryDirectory() as tmp:
                _,docs,frags=corpus(tmp,s['files'])
                direct=answer_question(s['question'],Retriever(docs,frags,time.monotonic()+30),ScriptedClient(s['markers'],s['prose']))
                traced=worker.TracedRetriever(Retriever(docs,frags,time.monotonic()+30))
                observed=answer_question(s['question'],traced,ScriptedClient(s['markers'],s['prose']))
                # Precondition: the scenario exercises the delegated-value path.
                self.assertEqual(direct[1],'answer',direct[0])
                self.assertEqual(observed,direct)
                self.assertTrue(traced.calls)

    def test_worker_reports_cited_sources_from_accepted_evidence(self):
        for s in SCENARIOS:
            with self.subTest(s['question']),tempfile.TemporaryDirectory() as tmp:
                path,docs,frags=corpus(tmp,s['files'])
                direct=answer_question(s['question'],Retriever(docs,frags,time.monotonic()+30),ScriptedClient(s['markers'],s['prose']))
                inp=dict(archive=str(path),question=s['question'],history=[],
                         config=dict(engine='deepseek',top_k=6,case_seconds=60))
                stdout=io.StringIO()
                with patch.object(worker,'Client',lambda deadline,config:ScriptedClient(s['markers'],s['prose'])),\
                     patch.object(sys,'stdin',io.StringIO(json.dumps(inp,ensure_ascii=False))),\
                     contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(io.StringIO()):
                    worker.main()
                out=json.loads(stdout.getvalue())
                self.assertEqual((out['answer'],out['status']),direct)
                self.assertIsNotNone(out['candidate'])
                cited={c['fragment_id'] for claim in out['candidate']['claims'] for c in claim['sources']}
                # Precondition: runtime restored source blocks under new IDs.
                self.assertTrue(cited-{f.id for f in frags})
                reported={f['id']:f for f in out['fragments']}
                self.assertEqual(set(reported),cited)
                texts={d['name']:d['text'] for d in out['documents']}
                for f in reported.values():
                    self.assertEqual(f['text'],texts[f['document']][f['start']:f['end']])
                self.assertNotIn('unobserved_citations',out)
                steps=out['model_steps']
                self.assertEqual([x['stage'] for x in steps],['generate','verify'])
                self.assertTrue(steps[1]['approved']);self.assertEqual(steps[1]['rejected_claims'],[])
                # Diagnostics carry no model prose or evidence text.
                self.assertNotIn(s['prose'],json.dumps(steps,ensure_ascii=False))

    def test_model_steps_explain_a_rejected_candidate(self):
        events=[dict(payload=dict(question='q',evidence=[],expanded_search=False),response=dict(status='answer',answer='Секретный текст',source_ids=['a','b'])),
                dict(payload=dict(question='q',evidence=[],expanded_search=False,candidate=dict(status='answer',claims=[{},{}],answer='Секретный текст')),
                     response=dict(approved=True,complete=True,status='answer',claim_checks=[dict(index=0,supported=True,applicable=True),dict(index=1,supported=True,applicable=False)]))]
        steps=worker.model_steps(events)
        self.assertEqual(steps[0],dict(stage='generate',expanded=False,status='answer',selected=2,prose=True,retry_reason=None))
        self.assertFalse(steps[1]['approved']);self.assertEqual(steps[1]['rejected_claims'],[1])
        self.assertNotIn('Секретный',json.dumps(steps,ensure_ascii=False))

    def test_unobserved_citation_is_not_scored_as_runtime_failure(self):
        calls=[dict(fragments=[dict(id='seen',document='a.txt',start=0,end=1,text='x',heading='')])]
        candidate=dict(claims=[dict(sources=[dict(fragment_id='seen'),dict(fragment_id='ghost')])])
        found,missing=worker.cited_fragments(calls,candidate)
        self.assertEqual([f['id'] for f in found],['seen']);self.assertEqual(missing,['ghost'])
        c,g,r=fixture();r['unobserved_citations']=['ghost']
        v=validate(c,g,r)
        self.assertEqual(v['outcome'],'not_evaluated');self.assertIn('adapter_unobserved_citation',v['not_evaluated'])

class PublishedTextTests(unittest.TestCase):
    """The visible answer, not an intermediate structure, is what is judged."""
    def with_prose(self,prose,visible=None):
        c,g,r=fixture();visible=prose+'\nИсточник: a, п. 1.' if visible is None else visible
        r['candidate']['answer']=prose;r['answer']=r['rendered_answer']=visible
        return validate(c,g,r)

    def test_upstream_false_acceptance_mutation_does_not_pass(self):
        # Mutation recorded in results/external_evaluation_false_acceptance.json:
        # authentic claims kept, every visible field replaced by a contradiction.
        c,g,r=fixture();bad='Оплачивать товар вообще не требуется.'
        r['candidate']['answer']=r['answer']=r['rendered_answer']=bad
        v=validate(c,g,r)
        self.assertNotEqual(v['outcome'],'pass');self.assertIn('published_prose_semantics',v['not_evaluated'])

    def test_other_unrecognized_prose_is_not_evaluated(self):
        for prose in ['Срок оплаты — полтора месяца.','Оплата не позднее 45 дней, но только по пятницам.']:
            v=self.with_prose(prose)
            self.assertEqual(v['outcome'],'not_evaluated',prose);self.assertIn('published_prose_semantics',v['not_evaluated'])

    def test_recognized_wrong_prose_fails_despite_real_quote(self):
        for old,new in [('45','90'),('45','60'),('календарных','рабочих'),('TEST-D017','TEST-D018')]:
            v=self.with_prose(QUOTE.replace(old,new))
            self.assertEqual(v['outcome'],'fail',new);self.assertIn('generation_failure',v['failures'])
            self.assertIs(v['checks']['prose'],False)

    def test_recognized_correct_prose_passes(self):
        for prose in [QUOTE,'Объект TEST-D017: срок оплаты 45 календарных дней после подписания акта; условие: без исключений']:
            v=self.with_prose(prose)
            self.assertEqual(v['outcome'],'pass',v);self.assertIs(v['checks']['prose'],True)

    def test_visible_text_must_start_with_checked_prose(self):
        v=self.with_prose(QUOTE,visible='Срок оплаты 90 дней.\n'+QUOTE)
        self.assertNotEqual(v['outcome'],'pass');self.assertIn('published_text_not_bound_to_candidate',v['not_evaluated'])

    def test_source_only_answer_must_publish_the_cited_provisions(self):
        c,g,r=fixture();r['answer']=r['rendered_answer']='Оплачивать товар вообще не требуется.'
        v=validate(c,g,r)
        self.assertNotEqual(v['outcome'],'pass');self.assertIn('published_text_not_bound_to_candidate',v['not_evaluated'])
        c,g,r=fixture();r['answer']=r['rendered_answer']='«'+QUOTE+'» [1]\n[1] a.'
        self.assertEqual(validate(c,g,r)['outcome'],'pass')

class RestoredBlockTests(unittest.TestCase):
    """Smoke d0a0658 fact-0000/fact-0001: correct source-only answers whose
    cited block also carries a heading or a neighbouring provision."""
    def test_neighbouring_provision_in_cited_table_is_context(self):
        v=validate(*block_case(TABLE,{'p1':(STORE,F_STORE),'p2':(DUTY,F_DUTY)},['p2']))
        self.assertEqual(v['outcome'],'pass',v);self.assertEqual(v['counts']['context_facts'],1)
        self.assertTrue(v['checks']['completeness'])

    def test_heading_around_cited_decision_is_context(self):
        v=validate(*block_case(PROTOCOL,{'p1':(LIMIT,F_LIMIT)},['p1']))
        self.assertEqual(v['outcome'],'pass',v);self.assertNotIn('free_text_semantics',v['not_evaluated'])

    def test_block_without_required_provision_is_incomplete(self):
        # The required provision exists only in another document.
        only=TABLE.replace('| 2 | '+DUTY+' |\n','')
        case,gold,out=block_case(only,{'p1':(STORE,F_STORE)},[])
        gold['sources']['p2']=dict(id='p2',document='other.txt',start=0,end=len(DUTY),quote=DUTY,document_sha256='0'*64,revision='base',fact=F_DUTY)
        case['expected']['required_claims']=[dict(fact=F_DUTY,acceptable_evidence_sets=[['p2']])]
        v=validate(case,gold,out)
        self.assertEqual(v['outcome'],'fail');self.assertIn('incomplete_answer',v['failures'])

    def test_forbidden_provision_in_cited_block_still_fails(self):
        v=validate(*block_case(TABLE,{'p1':(STORE,F_STORE),'p2':(DUTY,F_DUTY)},['p2'],forbidden=[F_STORE]))
        self.assertEqual(v['outcome'],'fail');self.assertIn('generation_failure',v['failures'])

    def test_rewritten_quote_is_not_context(self):
        case,gold,out=block_case(TABLE,{'p1':(STORE,F_STORE),'p2':(DUTY,F_DUTY)},['p2'])
        out['candidate']['claims'][0]['text']=out['candidate']['claims'][0]['text'].replace('9 рабочих','90 рабочих')
        out['answer']=out['rendered_answer']=out['candidate']['claims'][0]['text']
        self.assertNotEqual(validate(case,gold,out)['outcome'],'pass')

if __name__=='__main__':unittest.main()
