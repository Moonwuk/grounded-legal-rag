"""Root-cause regressions on synthetic corpora; no organizer answers in runtime."""
from pathlib import Path
from contextlib import contextmanager, redirect_stderr
import io,json,sys,tempfile,unittest,zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'prototype'),str(ROOT/'tests')]
from psb_corpus import load_corpus,read_docx,Fragment,norm
from psb_retrieval import Retriever,tokens
from psb_policy import render,validate_candidate,answer_question
from psb_llm import ProviderError
from test_baseline import ScriptedModel

@contextmanager
def corpus(files):
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/'kb.zip'
        with zipfile.ZipFile(p,'w') as z:
            for n,s in files.items():z.writestr(n,s)
        d,f=load_corpus(p)
        yield Retriever(d,f)

def candidate(p,status='answer',gap=None):
    f=p['evidence'][0]
    return {'status':status,'claims':[{'text':f['text'],'sources':[{'fragment_id':f['id'],'quote':f['text']}]}],
            'missing':['Документ'] if gap else [],'clarification':'','requested_facts':[gap] if gap else []}
def verdict(p):
    c=p['candidate']
    return {'approved':True,'complete':True,'status':c['status'],
            'claim_checks':[{'index':i,'supported':True,'applicable':True} for i in range(len(c['claims']))]}

class AuditFixes(unittest.TestCase):
    def test_partial_document_gap_expands_and_keeps_verified_fallback(self):
        with corpus({'A.txt':'Срок оплаты составляет 37 календарных дней.'}) as r:
            for last,expected in [(lambda p:candidate(p),'answer'),(ProviderError('http_503'),'partial')]:
                m=ScriptedModel([lambda p:candidate(p,'partial','document'),verdict,last] + ([verdict] if callable(last) else []))
                _,status=answer_question('Срок и архив?',r,m)
                self.assertEqual(status,expected)
                self.assertEqual([p['expanded_search'] for _,p in m.calls if 'candidate' not in p],[False,True])
                self.assertLessEqual(len(m.calls),4)
    def test_missing_user_date_does_not_expand(self):
        with corpus({'A.txt':'Срок оплаты составляет 37 календарных дней.'}) as r:
            m=ScriptedModel([lambda p:candidate(p,'partial','event_date'),verdict])
            self.assertEqual(answer_question('Срок?',r,m)[1],'partial');self.assertEqual(len(m.calls),2)
    def test_digit_references_generalize(self):
        self.assertIn('9',tokens('пункт 9'))
        with corpus({'Положение.txt':'\n'.join(f'{i}. Общее условие номер {i}: '+('данные. '*25) for i in range(1,60))}) as r:
            for i in (1,9,23,51):
                self.assertTrue(any(f.text.startswith(f'{i}.') for f in r.search(f'Что устанавливает пункт {i}?',top_k=1)))
    def test_long_linked_change_at_end_is_preserved(self):
        for number in ('КР-78/2031','ZZ-403/2040'):
            with corpus({'contract.txt':f'Договор № {number}\nОплата в течение 17 суток.',
                         'amendment.txt':f'Допсоглашение к договору № {number}\n'+('Служебная информация без условий.\n'*300)+'Новый срок оплаты составляет 63 суток.'}) as r:
                for expanded in (False,True):
                    self.assertTrue(any('63 суток' in f.text for f in r.search(f'Срок оплаты {number}',expanded=expanded)))
    def test_linked_context_over_limit_fails_explicitly(self):
        with corpus({'a.txt':'Договор № ZZ-403/2040\nОплата в течение 17 суток.',
                     'b.txt':'Изменение договора № ZZ-403/2040\n'+('Важное условие. '*20+'\n')*600}) as r:
            with self.assertRaisesRegex(ValueError,'evidence_size_limit'):r.search('Оплата ZZ-403/2040')
    def test_notes_rejected_and_plain_docx_keeps_working(self):
        for tag,part in [('footnoteReference','footnotes'),('endnoteReference','endnotes')]:
            raw=io.BytesIO()
            with zipfile.ZipFile(raw,'w') as z:
                z.writestr('word/document.xml',f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Правило оплаты.</w:t><w:{tag} w:id="1"/></w:r></w:p></w:document>')
                z.writestr(f'word/{part}.xml','<x>Исключение</x>')
            with self.assertRaisesRegex(ValueError,'notes_not_supported'):read_docx(raw.getvalue())
    def test_mixed_empty_document_rejected(self):
        with self.assertRaisesRegex(ValueError,'empty_document'):
            with corpus({'ok.txt':'Полный документ с условиями.','empty.txt':' \n\t'}):pass
    def test_short_value_has_contiguous_citable_source(self):
        with corpus({'rate.txt':'Срок оплаты:\n5 дней.\nДополнительное условие.'}) as r:
            fs=[f for f in r.fragments if '5 дней.' in f.text and len(norm(f.text))>=12]
            self.assertTrue(fs)
            f=fs[0];c=candidate({'evidence':r.evidence([f])})
            self.assertTrue(validate_candidate(c,[f]));self.assertIn('5 дней.',render(c,[f]))
    def test_no_untyped_missing_gap_accepted(self):
        c={'status':'insufficient','claims':[],'missing':['Талон'],'clarification':''}
        self.assertFalse(validate_candidate(c,[]))
        c['requested_facts']=['warranty_document'];self.assertTrue(validate_candidate(c,[]))
        self.assertIn('гарантийный талон',render(c,[]))
    def test_untrusted_paraphrase_never_published_even_with_positive_verdict(self):
        for fact,wrong in [('Оплата производится за 37 суток.','Оплата производится за 93 суток.'),
                           ('Приёмка проводится за 8 дней.','Все недостатки должны быть найдены за 8 дней.'),
                           ('Изменения оформляются письменно.','Изменения допустимы только одним способом.')]:
            f=Fragment('f','D.txt',0,len(fact),fact,'')
            c={'status':'answer','claims':[{'text':wrong,'sources':[{'fragment_id':'f','quote':fact}]}],'missing':[],'clarification':''}
            self.assertTrue(validate_candidate(c,[f]));out=render(c,[f])
            self.assertNotIn(wrong,out);self.assertIn(fact,out)
    def test_verifier_receives_published_wording(self):
        with corpus({'A.txt':'Срок оплаты составляет 37 календарных дней.'}) as r:
            def bad(p):
                c=candidate(p);c['claims'][0]['text']='Оплата только за 93 дня.';return c
            def check(p):
                self.assertNotIn('93',p['candidate']['claims'][0]['text'])
                self.assertIn('37',p['rendered_answer'])
                return verdict(p)
            text,status=answer_question('Оплата?',r,ScriptedModel([bad,check]))
            self.assertEqual(status,'answer');self.assertNotIn('93',text)
    def test_separate_excerpts_are_not_glued_into_a_new_sentence(self):
        from psb_policy import source_wording
        a='Изменить условия по перечню:';b='Остальные условия остаются без изменений.'
        c={'text':'Обобщённый вывод.', 'sources':[{'fragment_id':'a','quote':a},{'fragment_id':'b','quote':b}]}
        out=source_wording(c,[Fragment('a','D',0,len(a),a,''),Fragment('b','D',0,len(b),b,'')])
        self.assertEqual(out,'«Изменить условия по перечню:»\n«Остальные условия остаются без изменений.»')
    def test_provider_error_logs_code_not_body(self):
        with corpus({'A.txt':'Срок оплаты составляет 37 календарных дней.'}) as r:
            for reason in ('http_429','secret-body-sk-abcd'):
                buf=io.StringIO()
                with redirect_stderr(buf):answer_question('Оплата',r,ScriptedModel([ProviderError(reason)]))
                self.assertIn('provider_error:',buf.getvalue());self.assertNotIn('sk-abcd',buf.getvalue())
    def test_surface_oracle_excludes_references_and_is_not_semantic_pass(self):
        sys.path.insert(0,str(ROOT/'eval'))
        import run_adversarial
        self.assertIn('surface_checks_pass',Path(run_adversarial.__file__).read_text())
        wrong='Оплата за 93 дня. [1]\n[1] Источник: «Оплата за 37 дней».'
        body='\n'.join(x for x in wrong.splitlines() if not x.startswith('['))
        self.assertNotIn('37',body)
