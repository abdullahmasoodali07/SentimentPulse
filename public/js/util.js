/*
 * util.js - small helpers shared by the other scripts.
 *
 * SAFETY RULE: review text is only ever put on the page with textContent /
 * text nodes (never innerHTML), so HTML or JavaScript inside a review is
 * displayed as plain text and cannot run.
 */
(function (root) {
  "use strict";
  var SP = (root.SP = root.SP || {});

  // ---- DOM builder --------------------------------------------------------
  // h("div", {class: "card", onclick: fn}, "text", childNode, [more children])
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) return;
        if (key === "class") el.className = value;
        else if (key === "text") el.textContent = value;
        else if (key.indexOf("on") === 0 && typeof value === "function") el.addEventListener(key.slice(2), value);
        else if (value === true) el.setAttribute(key, "");
        else el.setAttribute(key, value);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }

  function append(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) child.forEach(function (c) { append(el, c); });
    else if (typeof child === "string" || typeof child === "number") el.appendChild(document.createTextNode(String(child)));
    else el.appendChild(child);
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
    return el;
  }

  // ---- formatting ---------------------------------------------------------
  var MINUS = "−";

  // 1.5 -> "1.50", -0.89 -> "-0.89" (real minus sign); null -> "n/a"
  function fmtScore(x, digits, withSign) {
    if (x === null || x === undefined) return "n/a";
    digits = digits === undefined ? 2 : digits;
    var s = Math.abs(x).toFixed(digits);
    if (x < 0 && Number(s) !== 0) return MINUS + s;
    return (withSign && x > 0 ? "+" : "") + s;
  }

  function fmtInt(x) { return Number(x).toLocaleString("en-US"); }
  function fmtPct(x) { return Number(x).toFixed(1) + "%"; }

  function parseISODate(iso) {          // "2026-05-11" -> local Date (no timezone shifting)
    var p = String(iso).slice(0, 10).split("-");
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  }
  function fmtDate(iso) {               // "11 May 2026"
    return parseISODate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  function fmtDay(iso) {                // "11 May"
    return parseISODate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }
  function fmtMonthShort(iso) {         // "May 26"
    return parseISODate(iso).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
  }

  function sentimentClass(score) { return score > 0 ? "positive" : score < 0 ? "negative" : "neutral"; }
  function titleCase(word) { return word.charAt(0).toUpperCase() + word.slice(1); }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function prefersReducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function scrollToEl(el) {
    el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  }

  // ---- review rendering ---------------------------------------------------

  // ["slow","slow","late"] -> [{word:"slow",count:2},{word:"late",count:1}] (first-seen order)
  function countWords(list) {
    var order = [], counts = {};
    list.forEach(function (w) {
      if (!(w in counts)) { counts[w] = 0; order.push(w); }
      counts[w] += 1;
    });
    return order.map(function (w) { return { word: w, count: counts[w] }; });
  }

  function wordChips(list, kind) {
    return countWords(list).map(function (item) {
      return h("span", { class: "chip chip-" + kind }, item.word + (item.count > 1 ? " ×" + item.count : ""));
    });
  }

  // Review text with matched words wrapped in <mark>. Tokenizing mirrors scoring.js.
  function highlight(text, pos, neg) {
    var frag = document.createDocumentFragment();
    var posSet = new Set(pos), negSet = new Set(neg);
    var lowered = text.toLowerCase().replace(/’/g, "'");
    if ((!posSet.size && !negSet.size) || lowered.length !== text.length) {
      frag.appendChild(document.createTextNode(text));
      return frag;
    }
    var re = /[a-z]+(?:'[a-z]+)?/g, last = 0, m;
    while ((m = re.exec(lowered)) !== null) {
      var cls = posSet.has(m[0]) ? "w-pos" : negSet.has(m[0]) ? "w-neg" : null;
      if (!cls) continue;
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      frag.appendChild(h("mark", { class: cls }, text.slice(m.index, m.index + m[0].length)));
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    return frag;
  }

  function scoreBadge(score) {
    var label = score > 0 ? "+" + score : score < 0 ? MINUS + Math.abs(score) : "0";
    return h("span", { class: "score score-" + sentimentClass(score), title: "Sentiment score" }, label);
  }

  function classPill(cls) {
    return h("span", { class: "pill pill-" + cls }, titleCase(cls));
  }

  // catLabels: {delivery: "Delivery & shipping", ...}
  function categoryTags(cats, catLabels) {
    return (cats || []).map(function (c) { return h("span", { class: "tag" }, catLabels[c] || c); });
  }

  // One review as a card: date, score, class, highlighted text, matched words, categories.
  function reviewItem(r, catLabels) {
    return h("article", { class: "review review-" + r.cls },
      h("header", { class: "review-head" },
        h("time", { datetime: r.date }, fmtDate(r.date)),
        scoreBadge(r.score), classPill(r.cls),
        h("span", { class: "rid" }, "#" + r.id)),
      h("p", { class: "review-text" }, highlight(r.text, r.pos, r.neg)),
      h("footer", { class: "review-words" },
        wordChips(r.pos, "pos"), wordChips(r.neg, "neg"), categoryTags(r.cats, catLabels)));
  }

  SP.util = {
    h: h, clear: clear, fmtScore: fmtScore, fmtInt: fmtInt, fmtPct: fmtPct, fmtDate: fmtDate, fmtDay: fmtDay,
    fmtMonthShort: fmtMonthShort, parseISODate: parseISODate, sentimentClass: sentimentClass, titleCase: titleCase,
    debounce: debounce, prefersReducedMotion: prefersReducedMotion, scrollToEl: scrollToEl, countWords: countWords,
    wordChips: wordChips, highlight: highlight, scoreBadge: scoreBadge, classPill: classPill,
    categoryTags: categoryTags, reviewItem: reviewItem, MINUS: MINUS
  };
})(window);
