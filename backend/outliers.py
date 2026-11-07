"""
outliers.py - find unusually NEGATIVE weeks / months with a z-score.

Method (plain statistics, no machine learning):

  1. Only periods with enough reviews are "eligible" (default: 8 per week,
     20 per month). A period with 3 reviews has a very noisy average.
  2. Need at least 6 eligible periods, otherwise we say "insufficient data".
     (With n periods the largest possible |z| is (n-1)/sqrt(n); for n=5 that
     is 1.79, so a threshold of -1.5 could barely fire. Six is the safe minimum.)
  3. baseline mean and standard deviation (sample std) of the eligible averages.
  4. z = (period average - mean) / std
  5. Flag a period if z <= -1.5. Label it "severe" if z <= -2.0, else "moderate".
     Only the NEGATIVE side is flagged - unusually happy periods are not outliers here.

Honest limits:
  * A very bad period is part of the data used for the mean/std, so it
    partly hides itself ("masking"). The method still works when bad periods
    are a minority, which is the case this dashboard is built for.
  * A flagged period means "unusually low sentiment compared with the rest of
    the data". It is NOT proof of an outage or of any specific cause.
"""

import statistics

Z_THRESHOLD = -1.5
SEVERE_Z = -2.0           # keep the dashboard's methodology text in sync with this value
MIN_REVIEWS = {"week": 8, "month": 20}
MIN_PERIODS = 6


def detect_outliers(periods, granularity, z_threshold=Z_THRESHOLD, min_reviews=None,
                    min_periods=MIN_PERIODS, severe_z=SEVERE_Z):
    """
    Returns the block stored in outliers.json for one granularity:
      {"status": "ok" | "insufficient_data", "reason": str|None,
       "baseline": {"mean","std","n_periods"} | None, "flagged": [ ... ]}
    """
    if min_reviews is None:
        min_reviews = MIN_REVIEWS[granularity]

    eligible = [p for p in periods if p["avg_score"] is not None and p["review_count"] >= min_reviews]

    def insufficient(reason):
        return {"status": "insufficient_data", "reason": reason, "baseline": None, "flagged": []}

    if len(eligible) < min_periods:
        return insufficient(
            f"Only {len(eligible)} {granularity}s have at least {min_reviews} reviews; "
            f"at least {min_periods} are needed for a reliable baseline.")

    scores = [p["avg_score"] for p in eligible]
    mean = statistics.mean(scores)
    std = statistics.stdev(scores)
    if std == 0:
        return insufficient(f"All eligible {granularity}s have the same average, so there is no variation to compare against.")

    flagged = []
    for p in eligible:
        z = (p["avg_score"] - mean) / std
        if z <= z_threshold:
            flagged.append({
                "period_id": p["id"],
                "avg_score": p["avg_score"],
                "review_count": p["review_count"],
                "z": round(z, 2) + 0.0,
                "deviation": round(p["avg_score"] - mean, 3) + 0.0,
                "severity": "severe" if z <= severe_z else "moderate",
                "why": (f"Average {p['avg_score']:.2f} is {abs(z):.1f} standard deviations below "
                        f"the mean of {mean:.2f} across {len(eligible)} eligible {granularity}s."),
            })
    return {
        "status": "ok",
        "reason": None,
        "baseline": {"mean": round(mean, 3) + 0.0, "std": round(std, 3) + 0.0, "n_periods": len(eligible)},
        "flagged": flagged,
    }


def mark_outliers(periods, block):
    """Set is_outlier=True on the periods listed in block['flagged']."""
    flagged_ids = {f["period_id"] for f in block["flagged"]}
    for p in periods:
        p["is_outlier"] = p["id"] in flagged_ids
