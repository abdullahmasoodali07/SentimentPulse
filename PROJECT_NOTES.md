# PROJECT_NOTES (for continuing in a new session)

Read this instead of re-reading the long specification.

## What this is
SentimentPulse: static dashboard. Python (stdlib only) reads `data/reviews.db` -> scores with a lexicon -> weekly/monthly
aggregation -> z-score outliers -> keyword complaint categories -> 8 JSON files in `public/data/` -> D3 front end.
No LLM, no backend server, no packages. Deploys as a static site (`public/`).

## Fixed decisions (do not change without the user's approval)
* Score = positive matches - negative matches; > 0 positive, < 0 negative, 0 neutral. Tokenizer `[a-z]+(?:'[a-z]+)?` on lowercased text.
* ISO weeks (Monday start), ids `YYYY-Www` / `YYYY-MM`, produced only by Python. Empty periods are gaps (`null`), never 0.
* Outliers: z <= -1.5, severe at z <= -2.0, min reviews 8 (week) / 20 (month), min 6 eligible periods, sample std. Weeks and months separate.
* Complaints: negative reviews only, whole-word/phrase keywords (`*` suffix wildcard), distinct reviews per category, % of negative reviews,
  evidence needs >= 5 negative reviews, a category is named only with >= 2 reviews (max 3 named), unmatched -> "other".
* Lexicon edits in the browser affect only the live analyzer; export -> `data/custom_lexicon.json` -> re-run `backend/main.py`.
* JSON contract: meta, summary, timeseries, outliers, reviews, complaints, lexicon, parity_cases (all `schema_version: 1`).

## Commands
    python scripts/generate_data.py          # data/reviews.db (seed 42)
    python backend/main.py                   # writes public/data/*.json
    python -m unittest discover -s tests     # 91 tests
    node tests/parity_check.js public/data/lexicon.json data/parity_cases.json   # [] = parity OK
    python -m http.server -d public 8000     # view at http://localhost:8000

## Status after Session 2
Done and tested: backend, 91 Python tests, Node parity check, all front-end features, README.
A headless-Chromium script (56 checks) passed against the dashboard; it lives outside the repo (not committed).
NOT done: `vercel.json`, production deployment check, real-device/browser testing beyond headless Chromium.

## Files added beyond the suggested structure
`public/js/util.js` (safe DOM helpers), `public/js/scoring.js` (browser scorer), `tests/test_export.py`, `tests/parity_check.js`,
`data/parity_cases.json`, `public/js/vendor/d3.min.js` (D3 7.9.0, ISC licence, bundled so no CDN is needed).
