"""
sentiment.py - tokenizer and sentiment scorer.

Scoring formula (the whole idea in one line):

    score = (number of positive words) - (number of negative words)

Rules, in order:
  1. Lowercase the text (and turn curly apostrophes into straight ones).
  2. Split it into tokens with the regex  [a-z]+(?:'[a-z]+)?
     -> only a-z letters, with an optional single inner apostrophe.
        Digits, punctuation, hyphens and non-English letters split words.
  3. A token counts as POSITIVE if it is in the positive lexicon, otherwise
     NEGATIVE if it is in the negative lexicon. (Whole word only.)
  4. Repeated words count every time ("awful awful" = 2 negative matches).
  5. Classify: score > 0 positive, score < 0 negative, score == 0 neutral.

The browser version in public/js/scoring.js follows exactly the same rules.
tests/test_sentiment.py checks both against data/parity_cases.json.

Known limits (documented on purpose): no negation handling ("not good" still
scores +1), no sarcasm detection, no intensity words ("very", "extremely").
"""

import re

TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def tokenize(text):
    """Return the list of lowercase word tokens in `text` (empty list for ''/None)."""
    if not text:
        return []
    return TOKEN_RE.findall(text.lower().replace("’", "'"))


def classify(score):
    """Map a numeric score to 'positive', 'negative' or 'neutral'."""
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


def score_text(text, lexicon):
    """
    Score one piece of text.

    Returns a dict:
        {"score": int, "cls": str, "pos": [matched positive words],
         "neg": [matched negative words]}
    `pos` / `neg` keep the order of appearance and include repeats.
    """
    pos, neg = [], []
    for token in tokenize(text):
        if token in lexicon["positive"]:
            pos.append(token)
        elif token in lexicon["negative"]:
            neg.append(token)
    score = len(pos) - len(neg)
    return {"score": score, "cls": classify(score), "pos": pos, "neg": neg}
