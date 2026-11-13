"""Score arithmetic of evaluation.judge_score against the regulation, section 8."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.judge_score import question_score, summarize  # noqa: E402


class JudgeScoreTests(unittest.TestCase):
    def test_question_is_mean_of_rounds_and_fabrication_zeroes_it(self):
        self.assertEqual(question_score(0.75, 0.25, False), 0.5)
        self.assertEqual(question_score(1, 0.75, False), 0.875)
        self.assertEqual(question_score(1, 1, True), 0.0)

    def test_match_win_and_score(self):
        r = summarize([1.0, 0.75, 0.5, 0.25, 0.0])
        self.assertEqual((r['wins'], r['losses'], r['ties']), (2, 2, 1))
        self.assertEqual(r['match_rate'], 0.5)
        self.assertEqual(r['win_rate'], 0.5)
        self.assertEqual(r['score'], 0.5)
        r = summarize([0.875, 0.5, 0.25])
        self.assertAlmostEqual(r['match_rate'], 0.542, places=3)
        self.assertEqual(r['win_rate'], 0.5)
        self.assertAlmostEqual(r['score'], round(0.7 * (1.625 / 3) + 0.15, 3))

    def test_all_ties_give_neutral_win_rate(self):
        r = summarize([0.5, 0.5])
        self.assertEqual(r['win_rate'], 0.5)
        self.assertEqual(r['score'], 0.5)

    def test_wins_only(self):
        r = summarize([0.75, 1.0])
        self.assertEqual(r['win_rate'], 1.0)
        self.assertEqual(r['score'], round(0.7 * 0.875 + 0.3, 3))

    def test_nothing_judged(self):
        r = summarize([])
        self.assertIsNone(r['score'])
        self.assertEqual(r['judged'], 0)


if __name__ == '__main__':
    unittest.main()
