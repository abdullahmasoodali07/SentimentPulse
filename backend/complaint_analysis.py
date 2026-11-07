"""
complaint_analysis.py - "Why did sentiment drop?"

For a group of reviews (one week, one month, or everything):

  1. Take only the NEGATIVE reviews (score < 0).
  2. Sort each one into complaint categories by keyword matching.
     One review can belong to several categories. A negative review that
     matches no keyword group goes to "other".
  3. Count DISTINCT REVIEWS per category (a review that says "late, late,
     delayed" still counts once for "delivery").
  4. percentage = reviews in category / number of negative reviews.
  5. Build a text explanation from a fixed template. Every number in it is
     calculated from the data - nothing is invented, and there is no AI.

The explanation says "associated with" and "reported by customers" on
purpose: this shows what customers wrote, not a verified technical cause.
"""

from backend.lexicon import COMPLAINT_CATEGORIES, COMPLAINT_KEYWORDS
from backend.sentiment import tokenize

MIN_NEGATIVE_REVIEWS = 5      # fewer negative reviews -> "insufficient evidence"
MIN_CATEGORY_COUNT = 2        # a category must appear in at least 2 reviews to be named
MAX_CATEGORIES_IN_TEXT = 3    # the explanation names at most 3 categories
MAX_EXAMPLES = 3              # example review ids kept per category

CATEGORY_ORDER = [c["id"] for c in COMPLAINT_CATEGORIES]

# Short lowercase names used inside explanation sentences
PHRASES = {
    "delivery": "delivery/shipping",
    "quality": "product quality/damage",
    "support": "customer support",
    "pricing": "pricing/payments",
    "website": "website/app performance",
    "returns": "returns/refunds",
    "other": "other (uncategorised)",
}


# ---- keyword matching ------------------------------------------------------

def compile_keywords(keywords=None):
    """Split each keyword phrase into words once: {"delivery": [["delay*"], ["never","arrived"], ...]}."""
    keywords = COMPLAINT_KEYWORDS if keywords is None else keywords
    return {cat: [phrase.lower().split() for phrase in phrases] for cat, phrases in keywords.items()}


def _word_matches(token, pattern):
    """'delay*' matches any token starting with 'delay'; otherwise the token must be identical."""
    if pattern.endswith("*"):
        return token.startswith(pattern[:-1])
    return token == pattern


def _phrase_in_tokens(tokens, phrase):
    n = len(phrase)
    for i in range(len(tokens) - n + 1):
        if all(_word_matches(tokens[i + j], phrase[j]) for j in range(n)):
            return True
    return False


def find_categories(text, compiled=None):
    """Category ids (except 'other') whose keywords appear in `text`, in display order."""
    compiled = compiled or compile_keywords()
    tokens = tokenize(text)
    return [cat for cat in CATEGORY_ORDER
            if any(_phrase_in_tokens(tokens, phrase) for phrase in compiled.get(cat, []))]


def assign_categories(text, compiled=None):
    """Categories for a NEGATIVE review: matched ones, or ['other'] if none matched."""
    return find_categories(text, compiled) or ["other"]


# ---- period analysis -------------------------------------------------------

def phrase_for(granularity, period):
    """'the week of 11 May 2026' / 'May 2026' - used inside explanation sentences."""
    if granularity == "week":
        label = period["label"]                       # "Week of 11 May 2026"
        return "the " + label[0].lower() + label[1:]
    return period["label"]


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def build_explanation(phrase, negative_count, rows):
    """
    Deterministic template text. `rows` are the category rows (sorted, count > 0).
    """
    n = negative_count
    if n == 0:
        return f"There were no negative reviews in {phrase}, so there are no complaints to analyse."
    if n < MIN_NEGATIVE_REVIEWS:
        verb = "was" if n == 1 else "were"
        return (f"Only {_plural(n, 'negative review')} {verb} recorded in {phrase}, fewer than the "
                f"{MIN_NEGATIVE_REVIEWS} needed for a reliable summary, so no explanation is offered. "
                f"The individual reviews can still be inspected.")

    named = [r for r in rows if r["count"] >= MIN_CATEGORY_COUNT][:MAX_CATEGORIES_IN_TEXT]
    if not named:
        return (f"{n} negative reviews were recorded in {phrase}, but no complaint category was "
                f"mentioned in at least {MIN_CATEGORY_COUNT} of them, so there is no clear recurring theme.")

    names = [PHRASES[r["id"]] for r in named]
    if len(names) == 1:
        listed = names[0]
    else:
        listed = ", ".join(names[:-1]) + " and " + names[-1]

    details = []
    for i, r in enumerate(named):
        name = names[i]
        if i == 0:
            details.append(f"{name[0].upper() + name[1:]} complaints appeared in {r['pct']:.0f}% of "
                           f"negative reviews ({r['count']} of {n})")
        else:
            details.append(f"{name} complaints in {r['pct']:.0f}% ({r['count']} of {n})")

    return (f"Negative sentiment in {phrase} was primarily associated with {listed}. "
            + "; ".join(details) + ". "
            "One review can mention several categories, so percentages may add up to more than 100%. "
            "These are complaints reported by customers in their review text: the pattern shows "
            "association, not a verified technical cause.")


def analyze_group(reviews, phrase):
    """
    Complaint block for a list of review dicts (each needs: id, score, cls, cats).
    Returns {"negative_reviews", "evidence", "categories": [...], "explanation"}.
    """
    negatives = [r for r in reviews if r["cls"] == "negative"]
    n = len(negatives)

    rows = []
    for cat in CATEGORY_ORDER:
        members = [r for r in negatives if cat in r["cats"]]
        if members:
            # examples: the most negative reviews first (ties -> lower id)
            examples = sorted(members, key=lambda r: (r["score"], r["id"]))[:MAX_EXAMPLES]
            rows.append({"id": cat, "count": len(members),
                         "pct": round(100.0 * len(members) / n, 1),
                         "example_review_ids": [r["id"] for r in examples]})
    rows.sort(key=lambda r: -r["count"])      # stable sort: ties keep category order

    return {
        "negative_reviews": n,
        "evidence": "sufficient" if n >= MIN_NEGATIVE_REVIEWS else "insufficient",
        "categories": rows,
        "explanation": build_explanation(phrase, n, rows),
    }
