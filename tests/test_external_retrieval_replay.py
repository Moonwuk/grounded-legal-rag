"""The external replay must not turn partial spans or missing labels into success."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))
from replay_external_retrieval import covers, coverage


class ExternalRetrievalReplayTests(unittest.TestCase):
    def test_span_requires_one_matching_document_and_continuous_exact_range(self):
        source = {'document':'a.txt', 'start':2, 'end':6, 'quote':'abcd'}
        valid = {'document':'a.txt', 'start':0, 'end':8, 'text':'--abcd--'}
        self.assertTrue(covers(source, [valid]))
        self.assertFalse(covers(source, [{**valid, 'document':'b.txt'}]))
        self.assertFalse(covers(source, [{**valid, 'text':'--abXd--'}]))
        split = [{'document':'a.txt','start':2,'end':4,'text':'ab'},
                 {'document':'a.txt','start':4,'end':6,'text':'cd'}]
        self.assertFalse(covers(source, split))

    def test_partial_evidence_and_alternative_full_sets_are_distinguished(self):
        sources = {n:{'document':n+'.txt','start':0,'end':1,'quote':n} for n in 'abc'}
        case = {'expected':{'required_claims':[{'acceptable_evidence_sets':[['a','b'],['c']]}]}}
        def hit(n):return {'document':n+'.txt','start':0,'end':1,'text':n}
        self.assertEqual(coverage(case,sources,[hit('a')]), (False, .5))
        self.assertEqual(coverage(case,sources,[hit('a'),hit('b')]), (True, 1.0))
        self.assertEqual(coverage(case,sources,[hit('c')]), (True, 1.0))

    def test_no_required_evidence_is_not_reported_as_hundred_percent(self):
        self.assertEqual(coverage({'expected':{'required_claims':[]}}, {}, []), (None, None))


if __name__ == '__main__':
    unittest.main()
