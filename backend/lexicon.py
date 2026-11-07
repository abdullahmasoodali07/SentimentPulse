"""
lexicon.py - the word lists that drive SentimentPulse.

Two separate things live here:

1. SENTIMENT WORDS  - positive and negative words used to score a review.
2. COMPLAINT KEYWORDS - keyword groups used to sort NEGATIVE reviews into
   complaint categories (delivery, support, pricing, ...).

Everything is plain Python data, so you can read it, edit it and explain it.
This is a *lexicon* (a dictionary of words). It is NOT a trained ML model.

Matching rules (see sentiment.py / complaint_analysis.py):
  * whole words only      -> "slow" does not match "slowly"
  * no stemming           -> "delay" and "delays" are listed separately
  * complaint keywords may end with "*" to mean "starts with"
    e.g. "delay*" matches delay, delays, delayed, delaying
  * complaint keywords may be phrases, e.g. "never arrived"
"""

import hashlib
import json
from pathlib import Path

# --------------------------------------------------------------------------
# 1. Sentiment words (single lowercase words; a word must not be in both lists)
# --------------------------------------------------------------------------
POSITIVE_WORDS = [
    "great", "amazing", "excellent", "wonderful", "fast", "helpful",
    "reliable", "satisfied", "smooth", "perfect", "love", "loved", "good",
    "nice", "happy", "easy", "friendly", "quick", "recommend", "fantastic",
    "awesome", "superb", "brilliant", "impressed", "pleased", "delighted",
    "polite", "responsive", "durable", "sturdy", "comfortable", "convenient",
    "flawless", "outstanding", "best", "beautiful", "efficient", "effortless",
    "speedy", "prompt", "courteous", "intuitive", "seamless", "pleasant",
    "lovely", "thrilled", "glad", "enjoy", "enjoyed", "solid", "stellar",
    "affordable",
]

NEGATIVE_WORDS = [
    "terrible", "broken", "slow", "damaged", "delayed", "awful", "poor",
    "frustrating", "disappointed", "useless", "horrible", "bad", "worst",
    "rude", "unhelpful", "defective", "faulty", "late", "missing", "crashed",
    "buggy", "laggy", "overpriced", "unresponsive", "disappointing",
    "annoying", "frustrated", "angry", "waste", "scam", "refused", "ignored",
    "cracked", "flimsy", "unreliable", "lost", "wrong", "failed", "glitchy",
    "confusing", "hate", "hated", "worthless", "nightmare", "unacceptable",
    "dreadful", "mediocre", "shoddy", "expensive", "disaster", "pathetic",
    "unusable", "appalling", "delay", "delays", "crashes", "fails", "stuck",
]

# --------------------------------------------------------------------------
# 2. Complaint categories and their keyword groups
# --------------------------------------------------------------------------
# Order matters: it is the display order and the tie-break order.
# "other" has no keywords: it is the fallback for a negative review that
# matches none of the other categories.
COMPLAINT_CATEGORIES = [
    {"id": "delivery", "label": "Delivery & shipping"},
    {"id": "quality", "label": "Product quality & damage"},
    {"id": "support", "label": "Customer support"},
    {"id": "pricing", "label": "Pricing & payments"},
    {"id": "website", "label": "Website / app performance"},
    {"id": "returns", "label": "Returns & refunds"},
    {"id": "other", "label": "Other complaints"},
]

COMPLAINT_KEYWORDS = {
    "delivery": [
        "delay*", "late", "never arrived", "not arrived", "still waiting",
        "lost in transit", "shipping", "courier", "undelivered", "tracking",
        "missing package", "wrong address", "parcel", "dispatch*",
    ],
    "quality": [
        "broke*", "damaged", "defective", "faulty", "cracked", "poor quality",
        "flimsy", "stopped working", "fell apart", "scratched",
        "dead on arrival", "malfunction*", "cheaply made", "shoddy",
    ],
    "support": [
        "support", "customer service", "no response", "unresponsive",
        "ignored", "rude", "hung up", "on hold", "ticket", "no reply",
        "never replied", "helpline", "agent*", "nobody replied",
    ],
    "pricing": [
        "overpriced", "expensive", "charged twice", "overcharged",
        "double charged", "hidden fee*", "hidden charge*", "price hike",
        "billing", "payment failed", "payment declined", "extra charge*",
        "wrongly charged",
    ],
    "website": [
        "website", "app", "checkout", "crash*", "glitch*", "login", "loading",
        "error*", "bug*", "freez*", "froze", "timed out", "site",
    ],
    "returns": [
        "refund*", "return*", "exchange*", "replacement", "money back",
        "send it back", "rma",
    ],
    "other": [],
}

# --------------------------------------------------------------------------
# Loading / exporting helpers
# --------------------------------------------------------------------------


def default_lexicon():
    """Return the built-in lexicon as {"positive": set, "negative": set}."""
    return {"positive": set(POSITIVE_WORDS), "negative": set(NEGATIVE_WORDS)}


def load_lexicon(custom_path=None):
    """
    Return a lexicon dict {"positive": set, "negative": set}.

    If custom_path points to a JSON file like
        {"positive": ["great", ...], "negative": ["awful", ...]}
    (this is what the dashboard's "Export lexicon" button downloads),
    that file replaces the built-in lists. Raises ValueError for bad files.
    """
    if not custom_path:
        lex = default_lexicon()
    else:
        path = Path(custom_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            lex = {
                "positive": {str(w).strip().lower() for w in raw["positive"]},
                "negative": {str(w).strip().lower() for w in raw["negative"]},
            }
        except (OSError, ValueError, KeyError, TypeError) as err:
            raise ValueError(f"Could not read lexicon file {path}: {err}") from err

    lex["positive"].discard("")
    lex["negative"].discard("")
    overlap = lex["positive"] & lex["negative"]
    if overlap:
        raise ValueError(f"Words in both lexicons: {sorted(overlap)}")
    return lex


def lexicon_version(lexicon):
    """Short fingerprint (8 hex chars) so the site can show which lexicon was used."""
    text = "P:" + ",".join(sorted(lexicon["positive"])) + "|N:" + ",".join(sorted(lexicon["negative"]))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def lexicon_to_json(lexicon, complaint_keywords=None):
    """Build the lexicon.json document (see PROJECT_NOTES.md, file 7)."""
    return {
        "schema_version": 1,
        "version": lexicon_version(lexicon),
        "positive": sorted(lexicon["positive"]),
        "negative": sorted(lexicon["negative"]),
        "complaint_keywords": complaint_keywords or COMPLAINT_KEYWORDS,
    }
