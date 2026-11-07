"""
aggregation.py - group scored reviews into weekly and monthly periods.

Week definition: ISO 8601 weeks. A week starts on MONDAY and ends on Sunday.
Its id is "YYYY-Www" using the ISO year (so 2025-12-29 belongs to "2026-W01").
A review belongs to a week/month according to its own date.

The list returned for each granularity is CONTINUOUS: every week (or month)
between the first and last review appears, even if it has no reviews.
An empty period has review_count 0 and avg_score None (null in JSON) - it is
never turned into a score of 0, because "no data" is not "neutral".

Each review passed in is a dict with at least: date (datetime.date), score, cls.
"""

from collections import defaultdict
from datetime import date, timedelta


# ---- period ids ------------------------------------------------------------

def week_start(d):
    """Monday of the ISO week containing date d."""
    return d - timedelta(days=d.weekday())


def week_id(d):
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def month_id(d):
    return f"{d.year}-{d.month:02d}"


def _week_label(start):
    return f"Week of {start.day} {start.strftime('%b %Y')}"


def _month_slots(first, last):
    """Yield (year, month) for every month from first to last (inclusive)."""
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def _slots(first, last, granularity):
    """List of (id, label, start_date, end_date) covering first..last without gaps."""
    slots = []
    if granularity == "week":
        current, final = week_start(first), week_start(last)
        while current <= final:
            slots.append((week_id(current), _week_label(current), current, current + timedelta(days=6)))
            current += timedelta(days=7)
    elif granularity == "month":
        for year, month in _month_slots(first, last):
            start = date(year, month, 1)
            nxt = date(year + (month == 12), month % 12 + 1, 1)
            slots.append((month_id(start), start.strftime("%B %Y"), start, nxt - timedelta(days=1)))
    else:
        raise ValueError("granularity must be 'week' or 'month'")
    return slots


# ---- aggregation -----------------------------------------------------------

def aggregate(reviews, granularity):
    """
    Build the continuous list of period dicts for 'week' or 'month'
    (field names match the timeseries.json contract).
    """
    if not reviews:
        return []
    key = week_id if granularity == "week" else month_id
    buckets = defaultdict(list)
    for r in reviews:
        buckets[key(r["date"])].append(r)

    dates = [r["date"] for r in reviews]
    periods, raw_avgs = [], []
    for pid, label, start, end in _slots(min(dates), max(dates), granularity):
        items = buckets.get(pid, [])
        n = len(items)
        raw = sum(r["score"] for r in items) / n if n else None   # review-weighted inside the period
        raw_avgs.append(raw)
        periods.append({
            "id": pid, "label": label, "start": start.isoformat(), "end": end.isoformat(),
            "review_count": n,
            "avg_score": None if raw is None else round(raw, 3) + 0.0,
            "positive": sum(1 for r in items if r["cls"] == "positive"),
            "negative": sum(1 for r in items if r["cls"] == "negative"),
            "neutral": sum(1 for r in items if r["cls"] == "neutral"),
            "prev_id": None, "prev_avg": None, "delta": None, "prev_adjacent": None,
            "is_outlier": False,
        })

    # Compare each non-empty period with the nearest EARLIER non-empty period.
    prev_index = None
    for i, period in enumerate(periods):
        if raw_avgs[i] is None:
            continue
        if prev_index is not None:
            period["prev_id"] = periods[prev_index]["id"]
            period["prev_avg"] = periods[prev_index]["avg_score"]
            period["delta"] = round(raw_avgs[i] - raw_avgs[prev_index], 3) + 0.0
            period["prev_adjacent"] = (i - prev_index == 1)   # False means a gap lies between them
        prev_index = i
    return periods


def _pct(count, total):
    return round(100.0 * count / total, 1) if total else 0.0


def summarize(reviews):
    """
    Overall numbers for the KPI cards. The average is taken over ALL reviews
    (review-weighted) - never as an average of period averages.
    Safe for an empty list: counts 0, percentages 0.0, avg_score None.
    """
    total = len(reviews)
    pos = sum(1 for r in reviews if r["cls"] == "positive")
    neg = sum(1 for r in reviews if r["cls"] == "negative")
    neu = total - pos - neg
    avg = round(sum(r["score"] for r in reviews) / total, 3) + 0.0 if total else None
    return {
        "total_reviews": total,
        "positive": {"count": pos, "pct": _pct(pos, total)},
        "negative": {"count": neg, "pct": _pct(neg, total)},
        "neutral": {"count": neu, "pct": _pct(neu, total)},
        "avg_score": avg,
    }
