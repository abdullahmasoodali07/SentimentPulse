/*
 * analyzer.js - the editable lexicon and the live review analyzer.
 *
 * IMPORTANT (also said on the page): edits only change THIS browser. The dashboard
 * numbers come from the Python pipeline and are not recomputed here. To apply an
 * edited lexicon to the real analysis, export it, save it as data/custom_lexicon.json
 * and run `python backend/main.py` again.
 */
(function (root) {
  "use strict";
  var SP = (root.SP = root.SP || {});
  var U = SP.util, h = U.h;
  var STORAGE_KEY = "sentimentpulse.lexicon.v1";
  var WORD_RE = /^[a-z]+(?:'[a-z]+)?$/; // same shape as one token in scoring.js

  var defaults = { version: "", positive: [], negative: [] };
  var lex = { positive: [], negative: [] };

  function $(id) { return document.getElementById(id); }

  // ---- saving in this browser only (optional; the page works without it) -----------
  function saveLocal() {
    try {
      if (isDefault()) localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: defaults.version, positive: lex.positive, negative: lex.negative }));
    } catch (e) { /* storage blocked: keep working in memory */ }
  }
  function loadLocal() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      // Ignore saved edits made against a different default lexicon (the data was regenerated).
      if (saved && saved.version === defaults.version && Array.isArray(saved.positive) && Array.isArray(saved.negative)) return saved;
    } catch (e) { /* nothing saved or storage blocked */ }
    return null;
  }

  function sameWords(a, b) {
    if (a.length !== b.length) return false;
    var s = new Set(a);
    return b.every(function (w) { return s.has(w); });
  }
  function isDefault() { return sameWords(lex.positive, defaults.positive) && sameWords(lex.negative, defaults.negative); }

  function sorted(list) { return list.slice().sort(); }

  // ---- lexicon editor ------------------------------------------------------------------
  function message(text) { $("lex-msg").textContent = text || ""; }

  function renderLexicon() {
    [["pos", "positive"], ["neg", "negative"]].forEach(function (pair) {
      var key = pair[0], name = pair[1];
      var box = U.clear($("lex-" + key + "-tags"));
      sorted(lex[name]).forEach(function (word) {
        box.appendChild(h("span", { class: "wtag wtag-" + key },
          word,
          h("button", {
            type: "button", "aria-label": "Remove " + word + " from the " + name + " list",
            onclick: function () { removeWord(name, word); }
          }, "×")));
      });
      $("lex-" + key + "-count").textContent = "(" + lex[name].length + ")";
    });
    var edited = !isDefault();
    var badge = $("lex-state");
    badge.textContent = edited ? "Edited in this browser" : "Default lexicon";
    badge.className = edited ? "badge badge-mod" : "badge";
    $("lex-version").textContent = edited
      ? "Edited from default version " + defaults.version + ". Dashboard figures are unchanged."
      : "Version " + defaults.version + " (same as the Python pipeline).";
    updateSelfCheck();
  }

  function addWord(name, raw) {
    var other = name === "positive" ? "negative" : "positive";
    var word = String(raw).trim().toLowerCase().replace(/’/g, "'");
    if (!word) return message("Type a word first.");
    if (!WORD_RE.test(word)) return message("One word at a time, using letters (and an apostrophe) only.");
    if (lex[name].indexOf(word) !== -1) return message("“" + word + "” is already in the " + name + " list.");
    if (lex[other].indexOf(word) !== -1) return message("“" + word + "” is in the " + other + " list. Remove it there first, because a word cannot be both.");
    lex[name].push(word);
    saveLocal();
    renderLexicon();
    message("Added “" + word + "” to the " + name + " list.");
    refreshResult();
  }

  function removeWord(name, word) {
    lex[name] = lex[name].filter(function (w) { return w !== word; });
    saveLocal();
    renderLexicon();
    message("Removed “" + word + "” from the " + name + " list.");
    refreshResult();
  }

  function exportLexicon() {
    var payload = { schema_version: 1, positive: sorted(lex.positive), negative: sorted(lex.negative) };
    var blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = h("a", { href: url, download: "custom_lexicon.json" });
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    message("Downloaded custom_lexicon.json. Save it in the data/ folder and re-run python backend/main.py to apply it.");
  }

  function resetLexicon() {
    lex = { positive: defaults.positive.slice(), negative: defaults.negative.slice() };
    saveLocal();
    renderLexicon();
    message("Lexicon reset to the default.");
    refreshResult();
  }

  // ---- live analyzer ----------------------------------------------------------------------
  var lastText = null;

  function currentScorer() {
    return SP.scoring.makeLexicon(lex.positive, lex.negative);
  }

  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  function analyze() {
    var text = $("an-text").value;
    var out = U.clear($("an-result"));
    if (!text.trim()) {
      lastText = null;
      out.appendChild(h("p", { class: "muted" }, "Enter some review text, then press Analyze."));
      return;
    }
    lastText = text;
    var res = SP.scoring.scoreText(text, currentScorer());
    var vclass = res.score > 0 ? "v-pos" : res.score < 0 ? "v-neg" : "v-neu";

    var explain = "Score = " + plural(res.pos.length, "positive match") + " − " + plural(res.neg.length, "negative match") +
      " = " + U.fmtScore(res.score, 0, false) + ". A score above 0 is positive, below 0 is negative, and exactly 0 is neutral.";
    if (!res.pos.length && !res.neg.length) explain += " No lexicon words were found, so the review is neutral. This does not mean the text has no sentiment, only that it uses no word from the lexicon.";
    else if (res.pos.length && res.neg.length && res.score === 0) explain += " Positive and negative words cancel out, so mixed reviews can score 0.";

    out.appendChild(h("div", { class: "an-box" },
      h("div", { class: "an-score" },
        h("span", { class: "big " + vclass }, U.fmtScore(res.score, 0, false)),
        U.classPill(res.cls), h("span", { class: "muted small" }, "sentiment score")),
      h("div", { class: "an-text" }, U.highlight(text, res.pos, res.neg)),
      h("div", { class: "an-words" },
        h("div", null, h("b", null, "Positive matches (" + res.pos.length + ")"),
          res.pos.length ? U.wordChips(res.pos, "pos") : h("span", { class: "muted small" }, "none")),
        h("div", null, h("b", null, "Negative matches (" + res.neg.length + ")"),
          res.neg.length ? U.wordChips(res.neg, "neg") : h("span", { class: "muted small" }, "none"))),
      h("p", { class: "small" }, explain),
      isDefault() ? null : h("p", { class: "small", style: "color:var(--warn)" },
        "This result uses your edited lexicon, so it can differ from what the Python pipeline would produce.")));
  }

  function refreshResult() { if (lastText !== null) analyze(); }

  // ---- self-check: does the browser reproduce Python's scores? -------------------------------
  var reviewsForCheck = [];
  function updateSelfCheck() {
    var el = $("an-selfcheck");
    if (!reviewsForCheck.length) { el.textContent = ""; return; }
    var scorer = SP.scoring.makeLexicon(defaults.positive, defaults.negative);
    var bad = 0;
    reviewsForCheck.forEach(function (r) {
      var res = SP.scoring.scoreText(r.text, scorer);
      if (res.score !== r.score || res.pos.join() !== r.pos.join() || res.neg.join() !== r.neg.join()) bad += 1;
    });
    el.textContent = "Self-check: with the default lexicon, this browser reproduces the Python score and matched words for " +
      U.fmtInt(reviewsForCheck.length - bad) + " of " + U.fmtInt(reviewsForCheck.length) + " dashboard reviews" +
      (bad ? " (" + bad + " differ: check that the data was regenerated)." : ".");
  }

  // ---- start-up ------------------------------------------------------------------------------
  function init(data) {
    defaults = { version: data.lexicon.version, positive: data.lexicon.positive.slice(), negative: data.lexicon.negative.slice() };
    var saved = loadLocal();
    lex = saved ? { positive: saved.positive.slice(), negative: saved.negative.slice() }
                : { positive: defaults.positive.slice(), negative: defaults.negative.slice() };
    reviewsForCheck = data.reviews.reviews;

    [["positive", "lex-pos"], ["negative", "lex-neg"]].forEach(function (pair) {
      $(pair[1] + "-form").addEventListener("submit", function (e) {
        e.preventDefault();
        var input = $(pair[1] + "-input");
        addWord(pair[0], input.value);
        if (lex[pair[0]].indexOf(String(input.value).trim().toLowerCase()) !== -1) input.value = "";
      });
    });
    $("lex-export").addEventListener("click", exportLexicon);
    $("lex-reset").addEventListener("click", resetLexicon);

    $("an-run").addEventListener("click", analyze);
    $("an-clear").addEventListener("click", function () { $("an-text").value = ""; U.clear($("an-result")); lastText = null; $("an-text").focus(); });
    $("an-text").addEventListener("keydown", function (e) { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") analyze(); });
    document.querySelectorAll("[data-example]").forEach(function (btn) {
      btn.addEventListener("click", function () { $("an-text").value = btn.getAttribute("data-example"); analyze(); });
    });

    renderLexicon();
    if (saved) message("Restored your earlier edits from this browser.");
  }

  SP.analyzer = { init: init };
})(window);
