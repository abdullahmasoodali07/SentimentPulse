"""
main.py - runs the whole SentimentPulse pipeline.

    SQLite  ->  read  ->  score  ->  aggregate  ->  outliers  ->  complaints  ->  8 JSON files

Run from the project root:
    python backend/main.py                       # data/reviews.db -> public/data/
    python backend/main.py --db other.db         # use another database
    python backend/main.py --help                # all options

Only the Python standard library is used.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:          # lets `python backend/main.py` import the `backend` package
    sys.path.insert(0, str(ROOT))

from backend import aggregation, complaint_analysis, database, lexicon as lexmod, outliers  # noqa: E402
from backend.sentiment import score_text  # noqa: E402

SCHEMA_VERSION = 1
GRANULARITIES = ("week", "month")


def write_json(path, data, compact=False):
    """Write UTF-8 JSON. Large files are compact; small ones are indented so they are readable."""
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_records(rows, lexicon, compiled_keywords):
    """
    Turn raw database rows into scored review records.
    Rows with an unreadable date or a NULL text are skipped (and counted).
    Returns (records, skipped_count). Records are sorted by (date, id).
    """
    records, skipped = [], 0
    for review_id, raw_date, raw_text in rows:
        day = database.parse_date(raw_date)
        if day is None or raw_text is None:
            skipped += 1
            continue
        text = str(raw_text)
        scored = score_text(text, lexicon)
        cats = (complaint_analysis.assign_categories(text, compiled_keywords)
                if scored["cls"] == "negative" else [])
        records.append({
            "id": review_id, "date": day, "text": text,
            "score": scored["score"], "cls": scored["cls"],
            "pos": scored["pos"], "neg": scored["neg"], "cats": cats,
            "week": aggregation.week_id(day), "month": aggregation.month_id(day),
        })
    records.sort(key=lambda r: (r["date"], r["id"]))
    return records, skipped


def run_pipeline(db_path, out_dir, table="reviews", id_col="id", date_col="review_date",
                 text_col="review_text", lexicon_path=None, generated_at=None):
    """Run every step and write the 8 JSON files into out_dir. Returns a small report dict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. read
    conn = database.connect_readonly(db_path)
    try:
        rows = database.read_reviews(conn, table, id_col, date_col, text_col)
        dataset = database.read_dataset_info(conn)
    finally:
        conn.close()

    # 2. score + categorise
    lexicon = lexmod.load_lexicon(lexicon_path)
    compiled = complaint_analysis.compile_keywords()
    records, skipped = build_records(rows, lexicon, compiled)

    # 3. aggregate + 4. outliers
    periods, outlier_blocks = {}, {}
    for g in GRANULARITIES:
        periods[g] = aggregation.aggregate(records, g)
        outlier_blocks[g] = outliers.detect_outliers(periods[g], g)
        outliers.mark_outliers(periods[g], outlier_blocks[g])

    # 5. complaints: one block per period that has reviews, plus an overall block
    complaints = {
        "schema_version": SCHEMA_VERSION,
        "categories": lexmod.COMPLAINT_CATEGORIES,
        "overall": complaint_analysis.analyze_group(records, "the whole dataset"),
    }
    for g in GRANULARITIES:
        groups = {}
        for r in records:
            groups.setdefault(r[g], []).append(r)
        complaints[g] = {
            p["id"]: complaint_analysis.analyze_group(groups[p["id"]], complaint_analysis.phrase_for(g, p))
            for p in periods[g] if p["review_count"] > 0
        }

    # 6. assemble the remaining documents
    summary = aggregation.summarize(records)
    summary["outlier_periods"] = {g: len(outlier_blocks[g]["flagged"]) for g in GRANULARITIES}

    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now().replace(microsecond=0).isoformat(),
        "dataset": dataset,
        "date_range": {"first": records[0]["date"].isoformat() if records else None,
                       "last": records[-1]["date"].isoformat() if records else None},
        "week_definition": "ISO 8601, Monday start; id = YYYY-Www",
        "scoring": {"formula": "positive matches - negative matches",
                    "lexicon_version": lexmod.lexicon_version(lexicon)},
        "outlier_method": {"z_threshold": outliers.Z_THRESHOLD,
                           "min_reviews": dict(outliers.MIN_REVIEWS),
                           "min_periods": outliers.MIN_PERIODS},
        "complaints_method": {"min_negative_reviews": complaint_analysis.MIN_NEGATIVE_REVIEWS,
                              "min_category_count": complaint_analysis.MIN_CATEGORY_COUNT,
                              "max_categories_in_text": complaint_analysis.MAX_CATEGORIES_IN_TEXT},
        "skipped_rows": skipped,
    }

    reviews_doc = {
        "schema_version": SCHEMA_VERSION,
        "count": len(records),
        "reviews": [{**r, "date": r["date"].isoformat()} for r in records],
    }
    # keep the documented field order
    reviews_doc["reviews"] = [
        {k: r[k] for k in ("id", "date", "text", "score", "cls", "pos", "neg", "cats", "week", "month")}
        for r in reviews_doc["reviews"]
    ]

    # 7. write
    write_json(out_dir / "meta.json", meta)
    write_json(out_dir / "summary.json", {"schema_version": SCHEMA_VERSION, **summary})
    write_json(out_dir / "timeseries.json", {"schema_version": SCHEMA_VERSION, **periods})
    write_json(out_dir / "outliers.json", {"schema_version": SCHEMA_VERSION, **outlier_blocks})
    write_json(out_dir / "reviews.json", reviews_doc, compact=True)
    write_json(out_dir / "complaints.json", complaints)
    write_json(out_dir / "lexicon.json", lexmod.lexicon_to_json(lexicon))

    parity_src = ROOT / "data" / "parity_cases.json"
    if parity_src.is_file():
        shutil.copyfile(parity_src, out_dir / "parity_cases.json")
    else:
        print(f"WARNING: {parity_src} not found; the browser self-check will be unavailable.")

    return {"reviews": len(records), "skipped": skipped, "summary": summary,
            "flagged": {g: [f["period_id"] for f in outlier_blocks[g]["flagged"]] for g in GRANULARITIES}}


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate the SentimentPulse JSON files from a SQLite database.")
    p.add_argument("--db", default=str(ROOT / "data" / "reviews.db"), help="SQLite file (default data/reviews.db)")
    p.add_argument("--out", default=str(ROOT / "public" / "data"), help="output folder (default public/data)")
    p.add_argument("--table", default="reviews")
    p.add_argument("--id-col", default="id")
    p.add_argument("--date-col", default="review_date")
    p.add_argument("--text-col", default="review_text")
    p.add_argument("--lexicon", default=None,
                   help="custom lexicon JSON (default: data/custom_lexicon.json if it exists)")
    args = p.parse_args(argv)

    lexicon_path = args.lexicon
    default_custom = ROOT / "data" / "custom_lexicon.json"
    if lexicon_path is None and default_custom.is_file():
        lexicon_path = default_custom
    print(f"Lexicon: {lexicon_path or 'built-in default'}")

    try:
        report = run_pipeline(args.db, args.out, args.table, args.id_col, args.date_col,
                              args.text_col, lexicon_path)
    except (FileNotFoundError, ValueError) as err:
        print(f"ERROR: {err}")
        return 1

    s = report["summary"]
    print(f"Read {report['reviews']} reviews ({report['skipped']} skipped).")
    print(f"Positive {s['positive']['count']}, negative {s['negative']['count']}, "
          f"neutral {s['neutral']['count']}; average score {s['avg_score']}.")
    for g in GRANULARITIES:
        print(f"Negative outlier {g}s: {report['flagged'][g] or 'none'}")
    print(f"JSON files written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
