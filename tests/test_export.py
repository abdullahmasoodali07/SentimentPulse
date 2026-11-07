"""Tests for the whole pipeline (backend/main.py): the 8 JSON files and their contract."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_data  # noqa: E402
from backend import main as pipeline  # noqa: E402

FILES = ["meta", "summary", "timeseries", "outliers", "reviews", "complaints", "lexicon", "parity_cases"]
PERIOD_KEYS = ["id", "label", "start", "end", "review_count", "avg_score", "positive", "negative", "neutral",
               "prev_id", "prev_avg", "delta", "prev_adjacent", "is_outlier"]
REVIEW_KEYS = ["id", "date", "text", "score", "cls", "pos", "neg", "cats", "week", "month"]
FIXED_TIME = "2026-11-12T10:15:00"


def load(folder, name):
    return json.loads((Path(folder) / f"{name}.json").read_text(encoding="utf-8"))


def make_db(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE reviews (id INTEGER PRIMARY KEY, review_date TEXT, review_text TEXT)")
    conn.executemany("INSERT INTO reviews VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()


class TestEmptyDatabase(unittest.TestCase):
    def test_empty_database_produces_valid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, out = Path(tmp) / "empty.db", Path(tmp) / "out"
            make_db(db, [])
            report = pipeline.run_pipeline(db, out, generated_at=FIXED_TIME)
            self.assertEqual(report["reviews"], 0)
            for name in FILES:
                self.assertTrue((out / f"{name}.json").is_file(), name)
                load(out, name)                                   # must be valid JSON
            summary = load(out, "summary")
            self.assertEqual(summary["total_reviews"], 0)
            self.assertIsNone(summary["avg_score"])
            self.assertEqual(summary["positive"], {"count": 0, "pct": 0.0})
            ts = load(out, "timeseries")
            self.assertEqual((ts["week"], ts["month"]), ([], []))
            self.assertEqual(load(out, "outliers")["week"]["status"], "insufficient_data")
            self.assertEqual(load(out, "reviews")["count"], 0)
            self.assertIn("no negative reviews", load(out, "complaints")["overall"]["explanation"])
            meta = load(out, "meta")
            self.assertEqual(meta["date_range"], {"first": None, "last": None})
            self.assertFalse(meta["dataset"]["is_synthetic"])


class TestBadInput(unittest.TestCase):
    def test_unreadable_rows_are_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, out = Path(tmp) / "x.db", Path(tmp) / "out"
            make_db(db, [(1, "2026-03-02 10:00:00", "Great and fast"), (2, "not a date", "Awful"),
                         (3, None, "Terrible"), (4, "2026-03-03", None), (5, "2026-03-04T08:30:00Z", "")])
            pipeline.run_pipeline(db, out, generated_at=FIXED_TIME)
            self.assertEqual(load(out, "meta")["skipped_rows"], 3)
            reviews = load(out, "reviews")["reviews"]
            self.assertEqual([r["id"] for r in reviews], [1, 5])
            self.assertEqual(reviews[1]["score"], 0)               # empty text = neutral, not skipped

    def test_missing_database_file(self):
        with self.assertRaises(FileNotFoundError):
            pipeline.run_pipeline("does_not_exist.db", tempfile.gettempdir())

    def test_wrong_table_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.db"
            make_db(db, [])
            with self.assertRaises(ValueError):
                pipeline.run_pipeline(db, Path(tmp) / "out", table="nope")

    def test_unsafe_identifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.db"
            make_db(db, [])
            with self.assertRaises(ValueError):
                pipeline.run_pipeline(db, Path(tmp) / "out", table="reviews; DROP TABLE reviews")


class TestSampleDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "reviews.db"
        cls.out = Path(cls.tmp.name) / "out"
        generate_data.build_database(cls.db, seed=42)
        cls.report = pipeline.run_pipeline(cls.db, cls.out, generated_at=FIXED_TIME)
        cls.d = {name: load(cls.out, name) for name in FILES}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # ---- contract ----
    def test_all_eight_files_exist_with_schema_version(self):
        for name in FILES:
            self.assertEqual(self.d[name]["schema_version"], 1, name)

    def test_top_level_keys(self):
        d = self.d
        self.assertEqual(set(d["meta"]), {"schema_version", "generated_at", "dataset", "date_range", "week_definition",
                                          "scoring", "outlier_method", "complaints_method", "skipped_rows"})
        self.assertEqual(set(d["summary"]), {"schema_version", "total_reviews", "positive", "negative", "neutral",
                                             "avg_score", "outlier_periods"})
        self.assertEqual(set(d["timeseries"]), {"schema_version", "week", "month"})
        self.assertEqual(set(d["outliers"]), {"schema_version", "week", "month"})
        self.assertEqual(set(d["reviews"]), {"schema_version", "count", "reviews"})
        self.assertEqual(set(d["complaints"]), {"schema_version", "categories", "overall", "week", "month"})
        self.assertEqual(set(d["lexicon"]), {"schema_version", "version", "positive", "negative", "complaint_keywords"})
        self.assertEqual(set(d["outliers"]["week"]), {"status", "reason", "baseline", "flagged"})

    def test_period_and_review_field_names(self):
        for g in ("week", "month"):
            for p in self.d["timeseries"][g]:
                self.assertEqual(list(p), PERIOD_KEYS)
        for r in self.d["reviews"]["reviews"][:50]:
            self.assertEqual(list(r), REVIEW_KEYS)

    def test_meta_values(self):
        meta = self.d["meta"]
        self.assertEqual(meta["generated_at"], FIXED_TIME)
        self.assertEqual(meta["outlier_method"], {"z_threshold": -1.5, "min_reviews": {"week": 8, "month": 20}, "min_periods": 6})
        self.assertEqual(meta["complaints_method"],
                         {"min_negative_reviews": 5, "min_category_count": 2, "max_categories_in_text": 3})
        self.assertEqual(meta["week_definition"], "ISO 8601, Monday start; id = YYYY-Www")
        self.assertEqual(meta["scoring"]["lexicon_version"], self.d["lexicon"]["version"])

    # ---- synthetic labelling ----
    def test_dataset_is_labelled_synthetic(self):
        ds = self.d["meta"]["dataset"]
        self.assertTrue(ds["is_synthetic"])
        self.assertIn("not real customer reviews", ds["notice"])

    # ---- consistency ----
    def test_totals_agree_everywhere(self):
        n = self.d["reviews"]["count"]
        s = self.d["summary"]
        self.assertEqual(n, len(self.d["reviews"]["reviews"]))
        self.assertEqual(s["total_reviews"], n)
        self.assertEqual(s["positive"]["count"] + s["negative"]["count"] + s["neutral"]["count"], n)
        for g in ("week", "month"):
            self.assertEqual(sum(p["review_count"] for p in self.d["timeseries"][g]), n)

    def test_overall_average_matches_reviews(self):
        scores = [r["score"] for r in self.d["reviews"]["reviews"]]
        self.assertAlmostEqual(self.d["summary"]["avg_score"], sum(scores) / len(scores), places=3)

    def test_every_review_links_to_its_period(self):
        for g in ("week", "month"):
            by_id = {p["id"]: p for p in self.d["timeseries"][g]}
            counts = {}
            for r in self.d["reviews"]["reviews"]:
                self.assertIn(r[g], by_id)
                self.assertTrue(by_id[r[g]]["start"] <= r["date"] <= by_id[r[g]]["end"])
                counts[r[g]] = counts.get(r[g], 0) + 1
            for pid, p in by_id.items():
                self.assertEqual(p["review_count"], counts.get(pid, 0))

    def test_period_averages_match_their_reviews(self):
        for g in ("week", "month"):
            for p in self.d["timeseries"][g]:
                scores = [r["score"] for r in self.d["reviews"]["reviews"] if r[g] == p["id"]]
                if scores:
                    self.assertAlmostEqual(p["avg_score"], sum(scores) / len(scores), places=3)
                else:
                    self.assertIsNone(p["avg_score"])

    def test_classification_and_cats_rules(self):
        for r in self.d["reviews"]["reviews"]:
            self.assertEqual(r["cls"], "positive" if r["score"] > 0 else "negative" if r["score"] < 0 else "neutral")
            self.assertEqual(r["score"], len(r["pos"]) - len(r["neg"]))
            if r["cls"] == "negative":
                self.assertTrue(r["cats"])
            else:
                self.assertEqual(r["cats"], [])

    def test_complaint_blocks_exist_for_exactly_the_periods_with_data(self):
        for g in ("week", "month"):
            with_data = {p["id"] for p in self.d["timeseries"][g] if p["review_count"] > 0}
            self.assertEqual(set(self.d["complaints"][g]), with_data)

    def test_complaint_counts_match_reviews(self):
        block = self.d["complaints"]["overall"]
        negatives = [r for r in self.d["reviews"]["reviews"] if r["cls"] == "negative"]
        self.assertEqual(block["negative_reviews"], len(negatives))
        for c in block["categories"]:
            self.assertEqual(c["count"], sum(1 for r in negatives if c["id"] in r["cats"]))
            self.assertAlmostEqual(c["pct"], 100 * c["count"] / len(negatives), places=1)
            for rid in c["example_review_ids"]:
                self.assertIn(rid, [r["id"] for r in negatives])

    # ---- the demo story ----
    def test_bad_period_is_flagged_and_explained(self):
        weeks = self.d["outliers"]["week"]
        self.assertEqual(weeks["status"], "ok")
        flagged = {f["period_id"] for f in weeks["flagged"]}
        self.assertTrue({"2026-W20", "2026-W21"} <= flagged)
        self.assertEqual({f["period_id"] for f in self.d["outliers"]["month"]["flagged"]}, {"2026-05"})
        text = self.d["complaints"]["month"]["2026-05"]["explanation"]
        self.assertIn("delivery/shipping", text)
        self.assertIn("customer support", text)

    def test_low_volume_week_is_not_flagged(self):
        w33 = next(p for p in self.d["timeseries"]["week"] if p["id"] == "2026-W33")
        self.assertEqual((w33["review_count"], w33["is_outlier"]), (4, False))
        self.assertLess(w33["avg_score"], -1)                      # very negative, but only 4 reviews
        self.assertEqual(self.d["complaints"]["week"]["2026-W33"]["evidence"], "insufficient")

    def test_empty_week_is_a_gap(self):
        w27 = next(p for p in self.d["timeseries"]["week"] if p["id"] == "2026-W27")
        self.assertEqual((w27["review_count"], w27["avg_score"], w27["delta"]), (0, None, None))
        w28 = next(p for p in self.d["timeseries"]["week"] if p["id"] == "2026-W28")
        self.assertEqual((w28["prev_id"], w28["prev_adjacent"]), ("2026-W26", False))

    def test_flags_in_timeseries_match_outliers_file(self):
        for g in ("week", "month"):
            flagged = {f["period_id"] for f in self.d["outliers"][g]["flagged"]}
            self.assertEqual({p["id"] for p in self.d["timeseries"][g] if p["is_outlier"]}, flagged)
            self.assertEqual(self.d["summary"]["outlier_periods"][g], len(flagged))

    def test_dataset_has_neutral_and_mixed_reviews(self):
        rows = self.d["reviews"]["reviews"]
        self.assertTrue(any(r["cls"] == "neutral" and not r["pos"] and not r["neg"] for r in rows))
        self.assertTrue(any(r["cls"] == "neutral" and r["pos"] and r["neg"] for r in rows))

    def test_generation_is_reproducible(self):
        again = Path(self.tmp.name) / "again.db"
        generate_data.build_database(again, seed=42)
        read = lambda p: sqlite3.connect(str(p)).execute("SELECT * FROM reviews").fetchall()  # noqa: E731
        self.assertEqual(read(self.db), read(again))


if __name__ == "__main__":
    unittest.main()
