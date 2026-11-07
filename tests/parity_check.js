// Node helper for the Python/JS parity test.
// Usage: node tests/parity_check.js <lexicon.json> <parity_cases.json>
// Prints a JSON list of mismatches ([] = every case matches).
const fs = require("fs");
const path = require("path");
const scoring = require(path.join(__dirname, "..", "public", "js", "scoring.js"));

const lex = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8")).cases;
const lexicon = scoring.makeLexicon(lex.positive, lex.negative);

const mismatches = [];
cases.forEach((c) => {
  const got = scoring.scoreText(c.text, lexicon);
  const ok =
    got.score === c.score &&
    got.cls === c.cls &&
    JSON.stringify(got.pos) === JSON.stringify(c.pos) &&
    JSON.stringify(got.neg) === JSON.stringify(c.neg);
  if (!ok) mismatches.push({ text: c.text, expected: c, got: got });
});
console.log(JSON.stringify(mismatches));
