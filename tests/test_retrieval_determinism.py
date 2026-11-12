"""Retrieval does not depend on PYTHONHASHSEED; a question naming two parties keeps both.

Diagnostic set on the organizer base (PSB_AB_20_vs_24, N12): the question
compares the П-17/2024 contract with «Альфа-Трейд» and the ПТ-05/2023 contract
with «Альфа-Трейдинг». Only one party got the boost: the choice used
str.rfind, which also finds «альфа-трейд» inside «альфа-трейдинг» (a tie at the
same position), and the tie was broken by set order, i.e. by the hash seed.
With seeds 2/3 the expanded search lost the П-17/2024 contract.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from psb_corpus import load_corpus
from psb_retrieval import Retriever
docs, frags = load_corpus(Path(sys.argv[2]))
r = Retriever(docs, frags)
out = {}
for i, q in enumerate(json.loads(sys.argv[3])):
    for expanded in (False, True):
        out[f"{i}{expanded}"] = [[f.document, f.start, f.end] for f in r.search(q, top_k=6, expanded=expanded)]
print(json.dumps(out))
'''
QUESTIONS = [
    'Сопоставьте сроки уведомления: расторжение договора П-17/2024 с «Альфа-Трейд» и отказ от продления ПТ-05/2023 с «Альфа-Трейдинг».',
    'Какие сроки уведомления у «Альфа-Трейдинг» по ПТ-05/2023 и у «Альфа-Трейд» по П-17/2024?',
    'Какая неустойка за просрочку оплаты по договору с «Альфа-Трейд»?',
]


def run(seed):
    env = {**os.environ, 'PYTHONHASHSEED': str(seed)}
    out = subprocess.run([sys.executable, '-c', PROBE, str(ROOT / 'prototype'), str(ROOT / 'organizer' / 'knowledge-base.zip'),
                          json.dumps(QUESTIONS, ensure_ascii=False)], env=env, capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise AssertionError(out.stderr[-800:])
    return json.loads(out.stdout)


class RetrievalDeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = [run(seed) for seed in (0, 1, 2, 3)]

    def test_same_hits_for_every_hash_seed(self):
        for other in self.runs[1:]:
            self.assertEqual(other, self.runs[0])

    def test_comparison_keeps_both_contracts(self):
        for key in ('0False', '0True', '1False', '1True'):
            names = {doc for doc, _, _ in self.runs[0][key]}
            with self.subTest(key):
                self.assertTrue(any('П-17-2024' in n and 'Договор' in n for n in names), names)
                self.assertTrue(any('ПТ-05-2023' in n for n in names), names)


if __name__ == '__main__':
    unittest.main()
