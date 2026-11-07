/*
 * scoring.js - the browser copy of backend/sentiment.py.
 *
 * It must behave EXACTLY like the Python version:
 *   score = positive matches - negative matches
 * Same tokenizer, same rules (see backend/sentiment.py for the explanation).
 * tests/test_sentiment.py runs both against data/parity_cases.json.
 *
 * This file has no DOM code, so Node can load it for testing.
 */
(function (root) {
  "use strict";

  // Same pattern as Python:  [a-z]+(?:'[a-z]+)?
  var TOKEN_RE = /[a-z]+(?:'[a-z]+)?/g;

  function tokenize(text) {
    if (!text) return [];
    var lowered = String(text).toLowerCase().replace(/’/g, "'");
    return lowered.match(TOKEN_RE) || [];
  }

  function classify(score) {
    if (score > 0) return "positive";
    if (score < 0) return "negative";
    return "neutral";
  }

  // lexicon = { positive: Set, negative: Set }
  function makeLexicon(positiveWords, negativeWords) {
    return { positive: new Set(positiveWords), negative: new Set(negativeWords) };
  }

  function scoreText(text, lexicon) {
    var pos = [];
    var neg = [];
    tokenize(text).forEach(function (token) {
      if (lexicon.positive.has(token)) pos.push(token);
      else if (lexicon.negative.has(token)) neg.push(token);
    });
    var score = pos.length - neg.length;
    return { score: score, cls: classify(score), pos: pos, neg: neg };
  }

  var api = { tokenize: tokenize, classify: classify, makeLexicon: makeLexicon, scoreText: scoreText };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api; // Node (tests)
  } else {
    root.SP = root.SP || {};
    root.SP.scoring = api; // browser
  }
})(typeof window !== "undefined" ? window : globalThis);
