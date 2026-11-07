"""Tests for backend/aggregation.py: ISO weeks, months, gaps, comparisons, weighted averages."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import aggregation as agg  # noqa: E402
from backend.sentiment import classify  # noqa: E402


def rev(day, score):
    return {"date": day, "score": score, "cls": classify(score)}


class TestPeriodIds(unittest.TestCase):
    def test_iso_week_year_boundary(self):
        self.assertEqual(agg.week_id(date(2025, 12, 29)), "2026-W01")  # Monday of ISO week 1 of 2026
        self.assertEqual(agg.week_id(date(2026, 1, 4)), "2026-W01")    # Sunday
        self.assertEqual(agg.week_id(date(2026, 1, 5)), "2026-W02")
        self.assertEqual(agg.week_id(date(2027, 1, 1)), "2026-W53")    # January date, previous ISO year

    def test_week_starts_on_monday(self):
        self.assertEqual(agg.week_start(date(2026, 5, 17)), date(2026, 5, 11))  # Sunday -> Monday before
        self.assertEqual(agg.week_start(date(2026, 5, 11)), date(2026, 5, 11))

    def test_month_id(self):
        self.assertEqual(agg.month_id(date(2026, 3, 9)), "2026-03")


class TestWeekly(unittest.TestCase):
    def test_counts_and_average(self):
        weeks = agg.aggregate([rev(date(2026, 5, 11), 2), rev(date(2026, 5, 13), -1), rev(date(2026, 5, 17), 0)], "week")
        self.assertEqual(len(weeks), 1)
        w = weeks[0]
        self.assertEqual((w["id"], w["review_count"]), ("2026-W20", 3))
        self.assertEqual((w["positive"], w["negative"], w["neutral"]), (1, 1, 1))
        self.assertAlmostEqual(w["avg_score"], 0.333, places=3)
        self.assertEqual((w["start"], w["end"]), ("2026-05-11", "2026-05-17"))
        self.assertEqual(w["label"], "Week of 11 May 2026")

    def test_missing_week_is_an_explicit_gap_not_zero(self):
        weeks = agg.aggregate([rev(date(2026, 5, 4), 1), rev(date(2026, 5, 20), 3)], "week")
        self.assertEqual([w["id"] for w in weeks], ["2026-W19", "2026-W20", "2026-W21"])
        gap = weeks[1]
        self.assertEqual(gap["review_count"], 0)
        self.assertIsNone(gap["avg_score"])
        self.assertIsNone(gap["delta"])
        self.assertEqual((gap["positive"], gap["negative"], gap["neutral"]), (0, 0, 0))

    def test_previous_period_comparison_skips_gaps(self):
        weeks = agg.aggregate([rev(date(2026, 5, 4), 1), rev(date(2026, 5, 20), 3)], "week")
        first, _, last = weeks
        self.assertIsNone(first["prev_id"])
        self.assertIsNone(first["prev_adjacent"])
        self.assertEqual(last["prev_id"], "2026-W19")      # nearest EARLIER week with data
        self.assertEqual(last["prev_avg"], 1.0)
        self.assertEqual(last["delta"], 2.0)
        self.assertIs(last["prev_adjacent"], False)         # a gap lies between them

    def test_adjacent_previous_period(self):
        weeks = agg.aggregate([rev(date(2026, 5, 4), 1), rev(date(2026, 5, 12), -1)], "week")
        self.assertIs(weeks[1]["prev_adjacent"], True)
        self.assertEqual(weeks[1]["delta"], -2.0)

    def test_empty_input(self):
        self.assertEqual(agg.aggregate([], "week"), [])
        self.assertEqual(agg.aggregate([], "month"), [])

    def test_invalid_granularity(self):
        with self.assertRaises(ValueError):
            agg.aggregate([rev(date(2026, 1, 1), 1)], "day")


class TestMonthly(unittest.TestCase):
    def test_missing_month_across_year_end(self):
        months = agg.aggregate([rev(date(2025, 12, 20), 1), rev(date(2026, 2, 3), -2)], "month")
        self.assertEqual([m["id"] for m in months], ["2025-12", "2026-01", "2026-02"])
        self.assertEqual(months[1]["review_count"], 0)
        self.assertIsNone(months[1]["avg_score"])
        self.assertEqual((months[1]["start"], months[1]["end"]), ("2026-01-01", "2026-01-31"))
        self.assertEqual(months[0]["label"], "December 2025")

    def test_leap_year_month_end(self):
        feb = agg.aggregate([rev(date(2028, 2, 10), 1)], "month")[0]
        self.assertEqual(feb["end"], "2028-02-29")


class TestSummary(unittest.TestCase):
    def test_overall_average_is_review_weighted(self):
        # period A: one review scoring +3; period B: three reviews scoring -1.
        reviews = [rev(date(2026, 1, 5), 3)] + [rev(date(2026, 2, 5), -1) for _ in range(3)]
        s = agg.summarize(reviews)
        self.assertEqual(s["avg_score"], 0.0)                       # (3 - 3) / 4
        months = agg.aggregate(reviews, "month")
        naive = sum(m["avg_score"] for m in months if m["avg_score"] is not None) / 2
        self.assertNotEqual(naive, s["avg_score"])                  # average of averages would be wrong (1.0)

    def test_counts_and_percentages(self):
        s = agg.summarize([rev(date(2026, 1, 1), 1), rev(date(2026, 1, 1), -1), rev(date(2026, 1, 1), 0), rev(date(2026, 1, 1), 2)])
        self.assertEqual(s["total_reviews"], 4)
        self.assertEqual(s["positive"], {"count": 2, "pct": 50.0})
        self.assertEqual(s["negative"], {"count": 1, "pct": 25.0})
        self.assertEqual(s["neutral"], {"count": 1, "pct": 25.0})

    def test_empty_dataset_is_safe(self):
        s = agg.summarize([])
        self.assertEqual(s["total_reviews"], 0)
        self.assertEqual(s["positive"], {"count": 0, "pct": 0.0})
        self.assertIsNone(s["avg_score"])


if __name__ == "__main__":
    unittest.main()
