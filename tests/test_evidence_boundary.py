"""Negative controls: a positive judge cannot authorize cropped source wording."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'prototype'),str(ROOT/'tests')]
from psb_corpus import Fragment
from psb_policy import render,validate_candidate,answer_question
from test_baseline import ScriptedModel
from test_audit_fixes import corpus,verdict

def draft(text,quote,fid='f'):
    return {'status':'answer','claims':[{'text':text,'sources':[{'fragment_id':fid,'quote':quote}]}],
            'missing':[],'clarification':''}

class EvidenceBoundaryTests(unittest.TestCase):
    def test_negation_and_conditions_survive_every_crop(self):
        for source,crop in [
            ('Арендатор не вправе передавать помещение третьим лицам.','вправе передавать помещение третьим лицам.'),
            ('При письменном согласии арендодателя арендатор вправе передать помещение.','арендатор вправе передать помещение.'),
            ('Поставщик обязан заменить товар, кроме случая повреждения покупателем.','Поставщик обязан заменить товар'),
            ('Срок составляет не менее 47 календарных дней.','менее 47 календарных дней.')]:
            f=Fragment('f','conditions.txt',0,len(source),source,'')
            c=draft(crop,crop)
            self.assertTrue(validate_candidate(c,[f]))
            self.assertIn('«'+source+'»',render(c,[f]))
            self.assertNotIn('\n'+crop+' [',render(c,[f]))

    def test_positive_stub_cannot_release_opposite_wording(self):
        with corpus({'terms.txt':'Арендатор не вправе передавать помещение третьим лицам.'}) as r:
            def malicious(p):
                f=p['evidence'][0]
                return draft('вправе передавать помещение третьим лицам.',
                             'вправе передавать помещение третьим лицам.',f['id'])
            def approving(p):
                self.assertIn('не вправе',p['candidate']['claims'][0]['text'])
                self.assertIn('не вправе',p['candidate']['claims'][0]['sources'][0]['quote'])
                return verdict(p)
            text,status=answer_question('Можно передать помещение?',r,ScriptedModel([malicious,approving]))
            self.assertEqual(status,'answer')
            self.assertIn('«Арендатор не вправе передавать помещение третьим лицам.»',text)

    def test_long_source_paragraph_is_not_published_from_the_middle(self):
        source='Без письменного разрешения запрещено следующее: '+('Условие договора. '*200)+'передавать имущество третьим лицам.'
        with corpus({'long.txt':source}) as r:
            hits=r.search('передавать имущество третьим лицам')
            self.assertTrue(hits)
            self.assertTrue(all(f.text==source for f in hits))

    def test_wrapped_negation_and_condition_stay_in_the_source_block(self):
        for source in ['Арендатор не\nвправе передавать имущество третьим лицам.',
                       'При наличии письменного согласия\nарендатор вправе передавать имущество третьим лицам.']:
            with corpus({'wrap.txt':source}) as r:
                hits=r.search('передавать имущество третьим лицам')
                self.assertTrue(hits)
                self.assertTrue(all(f.text==source for f in hits))
    def test_selected_missing_same_law_reference_has_program_owned_disclaimer(self):
        files={'law.txt':'Источник: Статья 4. Федеральный закон от 01.01.2030 N 987-ФЗ\nСтатья 4. Условия обработки\nОбработка допускается при наличии оснований части 2 статьи 17 настоящего Федерального закона.'}
        with corpus(files) as r:
            def select(p):
                f=next(f for f in p['evidence'] if 'оснований' in f['text'])
                return draft('Обработка всегда допускается.',f['text'],f['id'])
            text,status=answer_question('Когда обработка допускается?',r,ScriptedModel([select,verdict]))
            self.assertEqual(status,'partial')
            self.assertIn('17',text)
            self.assertIn('отсылоч',text)
            self.assertIn('не',text)

    def test_present_reference_is_not_reported_missing(self):
        header='Федеральный закон от 01.01.2030 N 987-ФЗ'
        with corpus({'a.txt':f'Источник: Статья 4. {header}\nСтатья 4. Условия\nОбработка допускается при наличии оснований статьи 17 настоящего Федерального закона.',
                     'b.txt':f'Источник: Статья 17. {header}\nСтатья 17. Основания\nОснованием является письменное заявление.'}) as r:
            self.assertEqual(r.reference_gaps(r.search('Обработка допускается')),[])

    def test_other_law_does_not_satisfy_reference(self):
        with corpus({'a.txt':'Источник: Статья 4. Федеральный закон от 01.01.2030 N 987-ФЗ\nСтатья 4. Условия\nОбработка допускается при наличии оснований статьи 17 настоящего Федерального закона.',
                     'b.txt':'Источник: Статья 17. Федеральный закон от 02.02.2030 N 654-ФЗ\nСтатья 17. Иные основания\nИные основания применяются к другому документу.'}) as r:
            self.assertTrue(r.reference_gaps(r.search('Обработка допускается')))

if __name__=='__main__':unittest.main()

class CompactSelectionTests(unittest.TestCase):
    def test_selector_cannot_inject_body_or_unknown_ids(self):
        from psb_policy import expand_selection
        f=Fragment('f','A',0,25,'Обработка не допускается.','')
        self.assertEqual(expand_selection({'source_ids':['unknown']},[f]),{})
        self.assertEqual(expand_selection({'source_ids':['f'],'claims':[]},[f]),{})
        c=expand_selection({'status':'answer','source_ids':['f']},[f])
        self.assertEqual(c['claims'][0]['text'],f.text)

    def test_truncated_response_retries_once_then_recovers(self):
        import time
        from test_security import proxy
        from psb_llm import ProxyClient
        with proxy('length_then_stop') as (_,calls):
            out=ProxyClient(time.monotonic()+15).complete('Fixed policy',{})
            self.assertEqual(out['status'],'out_of_scope')
            self.assertEqual(len(calls),2)
            self.assertIn('Повтор после обрезки',calls[1]['body']['messages'][0]['content'])
            self.assertEqual(calls[0]['body']['max_tokens'],calls[1]['body']['max_tokens'])

    def test_configured_token_budget_is_not_silently_clamped_to_8192(self):
        import time,os
        from unittest.mock import patch
        from test_security import proxy
        from psb_llm import ProxyClient
        with proxy() as (_,calls),patch.dict(os.environ,{'MAX_TOKENS':'16384'}):
            ProxyClient(time.monotonic()+10).complete('Fixed policy',{})
            self.assertEqual(calls[0]['body']['max_tokens'],16384)
            self.assertEqual(calls[0]['body']['reasoning_effort'],'low')

    def test_catalog_gap_in_real_corpus_is_derived_not_named_in_code(self):
        from psb_corpus import load_corpus
        from psb_retrieval import Retriever
        docs,fs=load_corpus(ROOT/'organizer/knowledge-base.zip');r=Retriever(docs,fs)
        selected=[f for f in r.search('Отзыв согласия на обработку персональных данных') if f.text.startswith('2. Согласие')]
        gaps=r.reference_gaps(selected)
        self.assertEqual(set(gaps[0]['articles']),{'6','10','11'})

class SafeTelemetryTests(unittest.TestCase):
    def test_provider_failure_has_safe_kind_and_position(self):
        import io,json,time
        from contextlib import redirect_stderr
        from test_security import proxy,TEST_KEY
        from psb_llm import ProxyClient,ProviderError
        with proxy('401') as (_,calls):
            log=io.StringIO()
            with redirect_stderr(log),self.assertRaises(ProviderError):
                ProxyClient(time.monotonic()+10,position=7).complete('policy',{})
            event=json.loads(log.getvalue())
            self.assertEqual(event['kind'],'http_401')
            self.assertEqual(event['position'],7)
            self.assertNotIn(TEST_KEY,log.getvalue())
