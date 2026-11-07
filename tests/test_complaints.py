"""Tests for backend/complaint_analysis.py: keyword matching, distinct counts, explanations."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import complaint_analysis as ca  # noqa: E402

COMPILED = ca.compile_keywords()


def neg(rid, cats, score=-1):
    return {"id": rid, "score": score, "cls": "negative", "cats": cats}


def other(rid, cls="positive", score=2):
    return {"id": rid, "score": score, "cls": cls, "cats": []}


class TestKeywordMatching(unittest.TestCase):
    def test_simple_category(self):
        self.assertEqual(ca.find_categories("The courier lost my parcel", COMPILED), ["delivery"])

    def test_whole_word_only(self):
        self.assertEqual(ca.find_categories("The latest update is here", COMPILED), [])   # 'latest' is not 'late'
        self.assertEqual(ca.find_categories("It was late", COMPILED), ["delivery"])

    def test_prefix_wildcard(self):
        for word in ("delay", "delays", "delayed", "delaying"):
            self.assertEqual(ca.find_categories(f"my order {word}", COMPILED), ["delivery"], word)

    def test_phrase_needs_words_in_order(self):
        self.assertEqual(ca.find_categories("it never arrived", COMPILED), ["delivery"])
        self.assertEqual(ca.find_categories("arrived never", COMPILED), [])

    def test_one_review_can_match_several_categories(self):
        self.assertEqual(ca.find_categories("Late parcel and rude customer service", COMPILED), ["delivery", "support"])

    def test_case_insensitive(self):
        self.assertEqual(ca.find_categories("REFUND please", COMPILED), ["returns"])

    def test_unmatched_negative_review_falls_back_to_other(self):
        self.assertEqual(ca.assign_categories("Awful experience overall", COMPILED), ["other"])
        self.assertEqual(ca.assign_categories("", COMPILED), ["other"])

    def test_custom_keywords(self):
        compiled = ca.compile_keywords({"delivery": ["zeppelin"], "other": []})
        self.assertEqual(ca.find_categories("came by zeppelin", compiled), ["delivery"])


class TestFrequencies(unittest.TestCase):
    def test_distinct_reviews_not_keyword_occurrences(self):
        # Three keyword hits in ONE review must still count as one review.
        text = "late late delayed and still waiting"
        cats = ca.assign_categories(text, COMPILED)
        block = ca.analyze_group([neg(1, cats)], "test period")
        self.assertEqual(block["categories"][0]["count"], 1)

    def test_percentage_uses_negative_reviews_as_denominator(self):
        reviews = [neg(i, ["delivery"]) for i in range(1, 4)] + [neg(4, ["quality"]), neg(5, ["quality"])] \
                  + [other(i) for i in range(6, 11)]       # 5 positive reviews must be ignored
        block = ca.analyze_group(reviews, "test period")
        self.assertEqual(block["negative_reviews"], 5)
        by_id = {c["id"]: c for c in block["categories"]}
        self.assertEqual(by_id["delivery"]["count"], 3)
        self.assertEqual(by_id["delivery"]["pct"], 60.0)     # 3 of 5, not 3 of 10

    def test_review_in_two_categories_counts_in_both(self):
        reviews = [neg(1, ["delivery", "support"]), neg(2, ["delivery"]), neg(3, ["support"])]
        block = ca.analyze_group(reviews, "p")
        by_id = {c["id"]: c for c in block["categories"]}
        self.assertEqual((by_id["delivery"]["count"], by_id["support"]["count"]), (2, 2))
        self.assertGreater(sum(c["pct"] for c in block["categories"]), 100.0)

    def test_categories_sorted_by_count_and_zero_counts_omitted(self):
        reviews = [neg(1, ["support"]), neg(2, ["delivery"]), neg(3, ["delivery"])]
        block = ca.analyze_group(reviews, "p")
        self.assertEqual([c["id"] for c in block["categories"]], ["delivery", "support"])

    def test_example_ids_are_the_most_negative_first(self):
        reviews = [neg(1, ["delivery"], -1), neg(2, ["delivery"], -4), neg(3, ["delivery"], -2), neg(4, ["delivery"], -3)]
        block = ca.analyze_group(reviews, "p")
        self.assertEqual(block["categories"][0]["example_review_ids"], [2, 4, 3])

    def test_empty_group(self):
        block = ca.analyze_group([], "the whole dataset")
        self.assertEqual((block["negative_reviews"], block["evidence"], block["categories"]), (0, "insufficient", []))
        self.assertIn("no negative reviews", block["explanation"])


class TestExplanation(unittest.TestCase):
    def reviews(self):
        # 6 negative reviews: delivery 4, support 3, pricing 1
        return [neg(1, ["delivery", "support"]), neg(2, ["delivery", "support"]), neg(3, ["delivery"]),
                neg(4, ["delivery"]), neg(5, ["support"]), neg(6, ["pricing"])]

    def test_numbers_are_calculated_from_data(self):
        block = ca.analyze_group(self.reviews(), "May 2026")
        text = block["explanation"]
        self.assertEqual(block["evidence"], "sufficient")
        self.assertIn("67% of negative reviews (4 of 6)", text)     # delivery
        self.assertIn("50% (3 of 6)", text)                         # support
        self.assertIn("May 2026", text)

    def test_only_recurring_categories_are_named(self):
        text = ca.analyze_group(self.reviews(), "May 2026")["explanation"]
        self.assertIn("delivery/shipping", text)
        self.assertIn("customer support", text)
        self.assertNotIn("pricing", text)                           # appears in only 1 review

    def test_at_most_three_categories_named(self):
        reviews = [neg(i, ["delivery", "support", "pricing", "website"]) for i in range(1, 7)]
        text = ca.analyze_group(reviews, "p")["explanation"]
        named = [p for p in ("delivery/shipping", "customer support", "pricing/payments", "website/app performance") if p in text]
        self.assertEqual(len(named), 3)

    def test_insufficient_evidence_is_stated(self):
        block = ca.analyze_group([neg(1, ["delivery"]), neg(2, ["delivery"]), neg(3, ["delivery"])], "the week of 10 Aug 2026")
        self.assertEqual(block["evidence"], "insufficient")
        self.assertIn("Only 3 negative reviews were recorded", block["explanation"])
        self.assertNotIn("primarily associated", block["explanation"])

    def test_single_negative_review_grammar(self):
        self.assertIn("Only 1 negative review was recorded", ca.analyze_group([neg(1, ["delivery"])], "p")["explanation"])

    def test_no_recurring_theme(self):
        reviews = [neg(1, ["delivery"]), neg(2, ["support"]), neg(3, ["pricing"]), neg(4, ["website"]), neg(5, ["returns"])]
        text = ca.analyze_group(reviews, "p")["explanation"]
        self.assertIn("no clear recurring theme", text)

    def test_never_claims_causation(self):
        text = ca.analyze_group(self.reviews(), "p")["explanation"]
        self.assertIn("not a verified technical cause", text)
        self.assertNotIn("caused by", text)

    def test_deterministic(self):
        a = ca.analyze_group(self.reviews(), "p")
        b = ca.analyze_group(list(reversed(self.reviews())), "p")
        self.assertEqual(a["explanation"], b["explanation"])

    def test_phrase_for_periods(self):
        self.assertEqual(ca.phrase_for("week", {"label": "Week of 11 May 2026"}), "the week of 11 May 2026")
        self.assertEqual(ca.phrase_for("month", {"label": "May 2026"}), "May 2026")


if __name__ == "__main__":
    unittest.main()
