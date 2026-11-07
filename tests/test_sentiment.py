"""Tests for backend/sentiment.py, backend/lexicon.py and Python/JavaScript parity."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import lexicon as lexmod  # noqa: E402
from backend.sentiment import classify, score_text, tokenize  # noqa: E402

LEX = lexmod.default_lexicon()
CASES = json.loads((ROOT / "data" / "parity_cases.json").read_text(encoding="utf-8"))["cases"]


class TestScoring(unittest.TestCase):
    def test_positive_review(self):
        r = score_text("Excellent product, fast delivery", LEX)
        self.assertEqual((r["score"], r["cls"]), (2, "positive"))
        self.assertEqual(r["pos"], ["excellent", "fast"])

    def test_negative_review(self):
        r = score_text("Terrible service and a broken box", LEX)
        self.assertEqual((r["score"], r["cls"]), (-2, "negative"))
        self.assertEqual(r["neg"], ["terrible", "broken"])

    def test_neutral_review_without_matches(self):
        r = score_text("I ordered a blue jacket", LEX)
        self.assertEqual((r["score"], r["cls"], r["pos"], r["neg"]), (0, "neutral", [], []))

    def test_mixed_review_is_neutral(self):
        r = score_text("The delivery was slow but the product was excellent.", LEX)
        self.assertEqual((r["score"], r["cls"]), (0, "neutral"))
        self.assertEqual((r["pos"], r["neg"]), (["excellent"], ["slow"]))

    def test_empty_and_missing_text(self):
        for text in ("", "   ", None):
            r = score_text(text, LEX)
            self.assertEqual((r["score"], r["cls"], r["pos"], r["neg"]), (0, "neutral", [], []))

    def test_word_boundaries(self):
        self.assertEqual(score_text("greatest", LEX)["score"], 0)   # not "great"
        self.assertEqual(score_text("slowly", LEX)["score"], 0)     # not "slow"
        self.assertEqual(score_text("misgood", LEX)["score"], 0)    # not "good"

    def test_case_insensitive_and_repeats_counted(self):
        r = score_text("AWFUL awful Awful", LEX)
        self.assertEqual(r["score"], -3)

    def test_known_limit_negation_not_handled(self):
        # Documented limitation: "not good" is scored as positive.
        self.assertEqual(score_text("not good", LEX)["score"], 1)

    def test_tokenize(self):
        self.assertEqual(tokenize("It's fast-ish!"), ["it's", "fast", "ish"])
        self.assertEqual(tokenize(""), [])

    def test_classify_thresholds(self):
        self.assertEqual([classify(-1), classify(0), classify(1)], ["negative", "neutral", "positive"])


class TestLexicon(unittest.TestCase):
    def test_default_lists_do_not_overlap(self):
        self.assertEqual(LEX["positive"] & LEX["negative"], set())

    def test_spec_example_words_present(self):
        for w in ["great", "amazing", "excellent", "wonderful", "fast", "helpful",
                  "reliable", "satisfied", "smooth", "perfect"]:
            self.assertIn(w, LEX["positive"])
        for w in ["terrible", "broken", "slow", "damaged", "delayed", "awful",
                  "poor", "frustrating", "disappointed", "useless"]:
            self.assertIn(w, LEX["negative"])

    def test_custom_lexicon_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "custom.json"
            p.write_text(json.dumps({"positive": ["Sparkly"], "negative": ["meh"]}), encoding="utf-8")
            lex = lexmod.load_lexicon(p)
            self.assertEqual(lex["positive"], {"sparkly"})
            self.assertEqual(score_text("sparkly but meh meh", lex)["score"], -1)

    def test_overlapping_custom_lexicon_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text(json.dumps({"positive": ["odd"], "negative": ["odd"]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                lexmod.load_lexicon(p)

    def test_version_changes_when_lexicon_changes(self):
        other = {"positive": LEX["positive"] | {"zzz"}, "negative": set(LEX["negative"])}
        self.assertNotEqual(lexmod.lexicon_version(LEX), lexmod.lexicon_version(other))


class TestParity(unittest.TestCase):
    """The same hand-written cases must pass in Python AND in JavaScript."""

    def test_python_matches_expected(self):
        for c in CASES:
            with self.subTest(text=c["text"]):
                got = score_text(c["text"], LEX)
                self.assertEqual(got["score"], c["score"])
                self.assertEqual(got["cls"], c["cls"])
                self.assertEqual(got["pos"], c["pos"])
                self.assertEqual(got["neg"], c["neg"])

    def test_javascript_matches_expected(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed - JS parity not checked")
        with tempfile.TemporaryDirectory() as tmp:
            lex_path = Path(tmp) / "lexicon.json"
            lex_path.write_text(json.dumps(lexmod.lexicon_to_json(LEX)), encoding="utf-8")
            out = subprocess.run(
                [node, str(ROOT / "tests" / "parity_check.js"), str(lex_path),
                 str(ROOT / "data" / "parity_cases.json")],
                capture_output=True, text=True, check=True,
            ).stdout
        self.assertEqual(json.loads(out), [], "JS scoring differs from the expected results")


if __name__ == "__main__":
    unittest.main()
