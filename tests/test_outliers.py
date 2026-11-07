"""Tests for backend/outliers.py: z-score detection with guard rails."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import outliers  # noqa: E402


def periods(avgs, counts=None):
    counts = counts or [20] * len(avgs)
    return [{"id": f"p{i + 1}", "avg_score": a, "review_count": c, "is_outlier": False}
            for i, (a, c) in enumerate(zip(avgs, counts))]


NORMAL = [0.6, 0.5, 0.7, 0.6, 0.5, 0.6, 0.7, 0.55, 0.65]


class TestDetection(unittest.TestCase):
    def test_flags_unusually_low_period(self):
        block = outliers.detect_outliers(periods(NORMAL + [-1.0]), "month")
        self.assertEqual(block["status"], "ok")
        self.assertEqual([f["period_id"] for f in block["flagged"]], ["p10"])
        f = block["flagged"][0]
        self.assertEqual(f["severity"], "severe")
        self.assertLessEqual(f["z"], -2.0)
        self.assertLess(f["deviation"], 0)
        self.assertIn("standard deviations below", f["why"])

    def test_normal_variation_is_not_flagged(self):
        block = outliers.detect_outliers(periods(NORMAL + [0.58]), "month")
        self.assertEqual(block["flagged"], [])

    def test_high_outlier_is_not_flagged(self):
        block = outliers.detect_outliers(periods(NORMAL + [3.0]), "month")
        self.assertEqual(block["flagged"], [])           # only the negative side counts

    def test_moderate_severity(self):
        values = [1, -1] * 10 + [-1.9]                    # z of the last value is about -1.67
        block = outliers.detect_outliers(periods(values), "month")
        last = [f for f in block["flagged"] if f["period_id"] == "p21"]
        self.assertEqual(len(last), 1)
        self.assertEqual(last[0]["severity"], "moderate")
        self.assertGreater(last[0]["z"], -2.0)

    def test_baseline_values(self):
        block = outliers.detect_outliers(periods(NORMAL + [-1.0]), "month")
        self.assertEqual(block["baseline"]["n_periods"], 10)
        self.assertAlmostEqual(block["baseline"]["mean"], sum(NORMAL + [-1.0]) / 10, places=3)

    def test_flagged_are_in_chronological_order(self):
        vals = [-1.0] + NORMAL * 2 + [-1.0]
        block = outliers.detect_outliers(periods(vals), "month")
        ids = [f["period_id"] for f in block["flagged"]]
        self.assertEqual(ids, sorted(ids, key=lambda s: int(s[1:])))


class TestGuardRails(unittest.TestCase):
    def test_minimum_review_count_excludes_noisy_periods(self):
        counts = [20] * 9 + [3]                           # the very negative period has only 3 reviews
        block = outliers.detect_outliers(periods(NORMAL + [-1.0], counts), "month")
        self.assertEqual(block["flagged"], [])
        self.assertEqual(block["baseline"]["n_periods"], 9)   # and it is not part of the baseline

    def test_min_reviews_differs_for_weeks_and_months(self):
        self.assertEqual(outliers.MIN_REVIEWS, {"week": 8, "month": 20})
        counts = [10] * 10                                # 10 reviews: enough for a week, not for a month
        self.assertEqual(outliers.detect_outliers(periods(NORMAL + [-1.0], counts), "week")["status"], "ok")
        self.assertEqual(outliers.detect_outliers(periods(NORMAL + [-1.0], counts), "month")["status"], "insufficient_data")

    def test_too_few_periods_is_insufficient_data(self):
        block = outliers.detect_outliers(periods([0.5, 0.6, 0.5, 0.6, -2.0]), "month")   # only 5 periods
        self.assertEqual(block["status"], "insufficient_data")
        self.assertEqual(block["flagged"], [])
        self.assertIsNone(block["baseline"])
        self.assertIn("at least 6", block["reason"])

    def test_no_variation_is_insufficient_data(self):
        block = outliers.detect_outliers(periods([0.5] * 8), "month")
        self.assertEqual(block["status"], "insufficient_data")
        self.assertIn("no variation", block["reason"])

    def test_empty_periods_are_ignored(self):
        data = periods(NORMAL + [-1.0])
        data.insert(3, {"id": "gap", "avg_score": None, "review_count": 0, "is_outlier": False})
        block = outliers.detect_outliers(data, "month")
        self.assertEqual(block["baseline"]["n_periods"], 10)

    def test_empty_list(self):
        self.assertEqual(outliers.detect_outliers([], "week")["status"], "insufficient_data")

    def test_threshold_is_reachable_with_minimum_periods(self):
        # With n periods the largest possible |z| is (n-1)/sqrt(n); it must exceed 1.5 for n = MIN_PERIODS.
        n = outliers.MIN_PERIODS
        self.assertGreater((n - 1) / n ** 0.5, abs(outliers.Z_THRESHOLD))


class TestMarking(unittest.TestCase):
    def test_mark_outliers_sets_flag(self):
        data = periods(NORMAL + [-1.0])
        outliers.mark_outliers(data, outliers.detect_outliers(data, "month"))
        self.assertEqual([p["id"] for p in data if p["is_outlier"]], ["p10"])


if __name__ == "__main__":
    unittest.main()
