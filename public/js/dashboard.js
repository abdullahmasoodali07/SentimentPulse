/*
 * dashboard.js - the "main program" of the page.
 *
 *  1. loads the JSON files written by backend/main.py
 *  2. fills the KPI cards and the sentiment mix bar
 *  3. draws the trend chart (weekly / monthly) and handles clicks on points
 *  4. fills the period inspector: stats, complaint explanation, bar chart, original reviews
 *  5. starts the explorer, lexicon editor and live analyzer (their own files)
 *
 * Every number shown here was computed by Python. This file only displays it.
 */
(function (root) {
  "use strict";
  var SP = root.SP, U = SP.util, h = U.h;

  var FILES = ["meta", "summary", "timeseries", "outliers", "reviews", "complaints", "lexicon"];
  var REVIEWS_PER_STEP = 20;

  var state = {
    data: null,
    gran: "week",            // "week" or "month"
    selectedId: null,        // id of the selected period, or null = whole dataset
    clsFilter: "all",        // sentiment filter inside the inspector
    catFilter: "all",        // complaint-category filter inside the inspector
    shown: REVIEWS_PER_STEP,
    catLabels: {},
    periodsById: { week: {}, month: {} },
    reviewsByPeriod: { week: {}, month: {} },
    reviewById: {},
    barCats: [],
    barHost: null
  };

  function $(id) { return document.getElementById(id); }
  function setText(id, text) { $(id).textContent = text; }

  // ============================================================================
  // 1. Loading
  // ============================================================================
  function loadFile(name) {
    return fetch("data/" + name + ".json", { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (json) { return { name: name, json: json }; },
            function (err) { return { name: name, error: err }; });
  }

  function showFatal(messages) {
    var box = $("fatal");
    U.clear(box);
    box.hidden = false;
    box.appendChild(h("strong", null, "SentimentPulse could not load its data."));
    box.appendChild(h("ul", null, messages.map(function (m) { return h("li", null, m); })));
    box.appendChild(h("p", { class: "small" }, location.protocol === "file:"
      ? "This page was opened directly from a file, and browsers block data loading that way. Start a local server with: python -m http.server -d public 8000 (then open http://localhost:8000)."
      : "Run python backend/main.py to (re)generate the files in public/data/, then reload this page."));
  }

  function boot() {
    if (typeof d3 === "undefined") {
      showFatal(["The D3 library (js/vendor/d3.min.js) did not load."]);
      return;
    }
    Promise.all(FILES.map(loadFile)).then(function (results) {
      var data = {}, errors = [];
      results.forEach(function (r) {
        if (r.error) errors.push("data/" + r.name + ".json: " + r.error.message);
        else if (r.json.schema_version !== 1) errors.push("data/" + r.name + ".json has an unsupported schema_version.");
        else data[r.name] = r.json;
      });
      if (errors.length) { setText("overview-sub", "Data could not be loaded."); showFatal(errors); return; }
      try { init(data); }
      catch (err) { console.error(err); showFatal(["Unexpected error while building the page: " + err.message]); }
    });
  }

  // ============================================================================
  // 2. Start-up
  // ============================================================================
  function init(data) {
    state.data = data;
    data.complaints.categories.forEach(function (c) { state.catLabels[c.id] = c.label; });
    ["week", "month"].forEach(function (g) {
      data.timeseries[g].forEach(function (p) { state.periodsById[g][p.id] = p; });
    });
    data.reviews.reviews.forEach(function (r) {
      state.reviewById[r.id] = r;
      (state.reviewsByPeriod.week[r.week] = state.reviewsByPeriod.week[r.week] || []).push(r);
      (state.reviewsByPeriod.month[r.month] = state.reviewsByPeriod.month[r.month] || []).push(r);
    });

    renderHeader();
    renderKpis();
    renderMethodNumbers();
    renderFooter();

    selectDefaultFor(state.gran);
    renderTrend(false);
    renderFlagged();
    renderDetail();

    document.querySelectorAll("#gran-toggle button").forEach(function (btn) {
      btn.addEventListener("click", function () { setGranularity(btn.getAttribute("data-gran")); });
    });
    root.addEventListener("resize", U.debounce(function () { renderTrend(false); drawBars(); }, 150));

    // The other parts of the page. One failing must not take down the rest.
    [["explorer", function () { SP.explorer.init(data, state.catLabels); }],
     ["analyzer", function () { SP.analyzer.init(data); }]].forEach(function (part) {
      try { part[1](); } catch (err) { console.error(part[0], err); }
    });
  }

  // ============================================================================
  // 3. Header, KPIs, footer
  // ============================================================================
  function renderHeader() {
    var meta = state.data.meta, s = state.data.summary;
    if (meta.dataset.is_synthetic) {
      $("dataset-badge").hidden = false;
      var notice = $("notice");
      notice.hidden = false;
      notice.textContent = meta.dataset.notice;
    }
    setText("overview-sub", s.total_reviews
      ? U.fmtInt(s.total_reviews) + " reviews from " + U.fmtDate(meta.date_range.first) + " to " + U.fmtDate(meta.date_range.last) +
        ". Dataset: " + meta.dataset.name + "."
      : "The database contains no reviews, so there is nothing to analyse yet.");
  }

  function renderKpis() {
    var s = state.data.summary;
    setText("kpi-total", U.fmtInt(s.total_reviews));
    setText("kpi-total-sub", "reviews analysed");
    [["pos", s.positive], ["neg", s.negative], ["neu", s.neutral]].forEach(function (pair) {
      setText("kpi-" + pair[0], U.fmtInt(pair[1].count));
      setText("kpi-" + pair[0] + "-sub", U.fmtPct(pair[1].pct) + " of reviews");
    });
    var avg = s.avg_score;
    setText("kpi-avg", avg === null ? "n/a" : U.fmtScore(avg, 2, true));
    $("kpi-avg").className = "kpi-value " + (avg === null ? "" : avg > 0 ? "v-pos" : avg < 0 ? "v-neg" : "v-neu");
    renderOutlierKpi();

    var bar = U.clear($("mix-bar"));
    var legend = U.clear($("mix-legend"));
    [["pos", "Positive", s.positive], ["neu", "Neutral", s.neutral], ["neg", "Negative", s.negative]].forEach(function (seg) {
      bar.appendChild(h("div", { class: "mix-seg " + seg[0], style: "width:" + seg[2].pct + "%", title: seg[1] + " " + U.fmtPct(seg[2].pct) }));
      legend.appendChild(h("span", null, h("i", { style: "background:var(--" + (seg[0] === "pos" ? "pos" : seg[0] === "neg" ? "neg" : "neu") + ")" }),
        seg[1] + " " + U.fmtInt(seg[2].count) + " (" + U.fmtPct(seg[2].pct) + ")"));
    });
    bar.setAttribute("aria-label", "Sentiment mix: positive " + U.fmtPct(s.positive.pct) + ", neutral " + U.fmtPct(s.neutral.pct) +
      ", negative " + U.fmtPct(s.negative.pct));
  }

  function renderOutlierKpi() {
    var o = state.data.summary.outlier_periods;
    var other = state.gran === "week" ? "month" : "week";
    setText("kpi-out", U.fmtInt(o[state.gran]));
    setText("kpi-out-sub", "in the " + (state.gran === "week" ? "weekly" : "monthly") + " view · " + o[other] + " " + other + (o[other] === 1 ? "" : "s") + " in the other");
  }

  function renderMethodNumbers() {
    var m = state.data.meta, om = m.outlier_method, cm = m.complaints_method;
    var fills = {
      lexicon_version: m.scoring.lexicon_version, week_definition: m.week_definition,
      min_reviews_week: om.min_reviews.week, min_reviews_month: om.min_reviews.month, min_periods: om.min_periods,
      z_threshold: U.fmtScore(om.z_threshold, 1), min_negative: cm.min_negative_reviews,
      min_category: cm.min_category_count, max_categories: cm.max_categories_in_text
    };
    document.querySelectorAll("[data-fill]").forEach(function (el) {
      var key = el.getAttribute("data-fill");
      if (key in fills) el.textContent = fills[key];
    });
  }

  function renderFooter() {
    var m = state.data.meta, f = U.clear($("footer"));
    f.appendChild(h("p", null, "SentimentPulse · college engineering project · lexicon-based scoring, no AI model or external service."));
    f.appendChild(h("p", null, "Data generated " + m.generated_at.replace("T", " ") + " · lexicon version " + m.scoring.lexicon_version +
      " · rows skipped as unreadable: " + m.skipped_rows + "."));
    if (m.dataset.is_synthetic) f.appendChild(h("p", null, m.dataset.notice));
  }

  // ============================================================================
  // 4. Trend chart and selection
  // ============================================================================
  function currentPeriods() { return state.data.timeseries[state.gran]; }
  function currentOutliers() { return state.data.outliers[state.gran]; }
  function selectedPeriod() { return state.selectedId ? state.periodsById[state.gran][state.selectedId] : null; }
  function minReviews() { return state.data.meta.outlier_method.min_reviews[state.gran]; }

  function renderTrend(animate) {
    setText("trend-sub", state.gran === "week"
      ? "Average sentiment score per week (ISO weeks, Monday start)"
      : "Average sentiment score per calendar month");
    SP.charts.drawTrend($("trend-chart"), currentPeriods(), {
      gran: state.gran, minReviews: minReviews(), selectedId: state.selectedId, animate: animate,
      onSelect: function (id) { selectPeriod(id, true); }
    });
  }

  function renderFlagged() {
    var box = U.clear($("flagged"));
    var o = currentOutliers(), om = state.data.meta.outlier_method;
    var unit = state.gran === "week" ? "weeks" : "months";
    box.appendChild(h("h3", null, "Detected negative outlier " + unit));
    box.appendChild(h("p", { class: "muted small" },
      "Method: z-score of each " + state.gran + "'s average score against the other " + unit + ". A period is flagged when z ≤ " +
      U.fmtScore(om.z_threshold, 1) + ", it has at least " + om.min_reviews[state.gran] + " reviews, and at least " + om.min_periods +
      " periods are eligible. “Unusually low” is a statistical statement, not proof of an outage or of any cause."));

    if (o.status !== "ok") {
      box.appendChild(h("div", { class: "callout" }, "No outlier detection for this view: " + o.reason));
      return;
    }
    box.appendChild(h("p", { class: "muted small" },
      "Baseline: mean " + U.fmtScore(o.baseline.mean, 2, true) + ", standard deviation " + U.fmtScore(o.baseline.std, 2) +
      " across " + o.baseline.n_periods + " eligible " + unit + "."));
    if (!o.flagged.length) {
      box.appendChild(h("p", null, "No " + state.gran + " fell far enough below the baseline to be flagged."));
      return;
    }
    box.appendChild(h("div", { class: "flag-list" }, o.flagged.map(function (f) {
      var p = state.periodsById[state.gran][f.period_id];
      return h("button", {
        type: "button", class: "flag-btn", title: f.why,
        "aria-current": f.period_id === state.selectedId ? "true" : null,
        onclick: function () { selectPeriod(f.period_id, true); }
      },
        h("b", null, p ? p.label : f.period_id),
        h("span", null, "avg " + U.fmtScore(f.avg_score, 2, true) + " · " + f.review_count + " reviews"),
        h("span", null, "z = " + U.fmtScore(f.z, 2) + " · " + f.severity));
    })));
  }

  function selectDefaultFor(gran) {
    // Start on the most severe flagged period so the page opens on its main story.
    var o = state.data.outliers[gran];
    state.selectedId = null;
    if (o.status === "ok" && o.flagged.length) {
      state.selectedId = o.flagged.slice().sort(function (a, b) { return a.z - b.z; })[0].period_id;
    }
    resetInspectorFilters();
  }

  function resetInspectorFilters() { state.clsFilter = "all"; state.catFilter = "all"; state.shown = REVIEWS_PER_STEP; }

  function setGranularity(gran) {
    if (gran === state.gran) return;
    state.gran = gran;
    document.querySelectorAll("#gran-toggle button").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-gran") === gran));
    });
    selectDefaultFor(gran);
    renderOutlierKpi();
    renderTrend(true);
    renderFlagged();
    renderDetail();
  }

  function selectPeriod(id, fromUser) {
    state.selectedId = id;
    resetInspectorFilters();
    renderTrend(false);
    renderFlagged();
    renderDetail();
    // On small screens the inspector can be below the fold: bring it into view.
    if (fromUser) {
      var top = $("detail").getBoundingClientRect().top;
      if (top > root.innerHeight * 0.6) U.scrollToEl($("detail"));
    }
  }

  function clearSelection() {
    state.selectedId = null;
    resetInspectorFilters();
    renderTrend(false);
    renderFlagged();
    renderDetail();
  }

  // ============================================================================
  // 5. Period inspector
  // ============================================================================
  function renderDetail() {
    var empty = state.data.summary.total_reviews === 0;
    $("detail-empty").hidden = !empty;
    $("detail-content").hidden = empty;
    if (empty) return;
    var p = selectedPeriod();
    setText("detail-sub", p
      ? "Inspecting " + p.label + ". Every number and review below belongs to this period."
      : "Showing the whole dataset. Select a point on the trend chart to inspect one period.");
    renderPeriodCard();
    renderWhy();
    renderReviews();
  }

  function statBox(label, value, sub, cls) {
    return h("div", { class: "stat" }, h("span", null, label), h("b", { class: cls }, value), sub ? h("small", null, sub) : null);
  }
  function pctOf(n, total) { return total ? U.fmtPct(100 * n / total) : "–"; }

  function compareNode(p) {
    if (p.prev_id === null) return h("div", { class: "compare" }, "No earlier period with reviews to compare against.");
    var prev = state.periodsById[state.gran][p.prev_id];
    var cls = p.delta < 0 ? "v-neg" : p.delta > 0 ? "v-pos" : "v-neu";
    return h("div", { class: "compare" },
      "Compared with the previous available period (", prev ? prev.label : p.prev_id, ", average ", U.fmtScore(p.prev_avg, 2, true), "): ",
      h("b", { class: cls }, U.fmtScore(p.delta, 2, true)),
      p.prev_adjacent ? "." : ". There were periods with no reviews in between.");
  }

  function renderPeriodCard() {
    var host = U.clear($("period-card"));
    var p = selectedPeriod();
    var avgClass = function (a) { return a > 0 ? "v-pos" : a < 0 ? "v-neg" : "v-neu"; };

    if (!p) {
      var s = state.data.summary;
      host.appendChild(h("div", { class: "pc-head" }, h("div", null, h("h3", null, "Whole dataset"),
        h("span", { class: "muted small" }, U.fmtDate(state.data.meta.date_range.first) + " – " + U.fmtDate(state.data.meta.date_range.last)))));
      host.appendChild(h("div", { class: "stats" },
        statBox("Average", U.fmtScore(s.avg_score, 2, true), "all reviews", avgClass(s.avg_score)),
        statBox("Reviews", U.fmtInt(s.total_reviews)),
        statBox("Positive", U.fmtInt(s.positive.count), U.fmtPct(s.positive.pct), "v-pos"),
        statBox("Neutral", U.fmtInt(s.neutral.count), U.fmtPct(s.neutral.pct), "v-neu"),
        statBox("Negative", U.fmtInt(s.negative.count), U.fmtPct(s.negative.pct), "v-neg")));
      host.appendChild(h("div", { class: "compare" }, "Select a point on the trend chart (or a flagged period above it) to inspect one week or month."));
      return;
    }

    var flagged = currentOutliers().flagged.filter(function (f) { return f.period_id === p.id; })[0];
    var badges = h("div", { class: "badges" });
    if (flagged) badges.appendChild(h("span", { class: "badge badge-neg" }, "Flagged · " + flagged.severity));
    if (p.review_count < minReviews()) badges.appendChild(h("span", { class: "badge badge-warn" }, "Few reviews"));

    host.appendChild(h("div", { class: "pc-head" },
      h("div", null, h("h3", null, p.label), h("span", { class: "muted small" }, U.fmtDate(p.start) + " – " + U.fmtDate(p.end))),
      badges));
    host.appendChild(h("div", { class: "stats" },
      statBox("Average", U.fmtScore(p.avg_score, 2, true), "mean score", avgClass(p.avg_score)),
      statBox("Reviews", U.fmtInt(p.review_count)),
      statBox("Positive", U.fmtInt(p.positive), pctOf(p.positive, p.review_count), "v-pos"),
      statBox("Neutral", U.fmtInt(p.neutral), pctOf(p.neutral, p.review_count), "v-neu"),
      statBox("Negative", U.fmtInt(p.negative), pctOf(p.negative, p.review_count), "v-neg")));
    host.appendChild(compareNode(p));
    if (flagged) {
      host.appendChild(h("div", { class: "callout callout-neg" },
        h("p", null, flagged.why),
        h("p", null, "This marks the period as statistically unusual compared with the others. It does not prove an outage or any specific cause.")));
    } else if (p.review_count < minReviews()) {
      host.appendChild(h("div", { class: "callout" }, "This period has only " + p.review_count + " reviews, below the " + minReviews() +
        " needed for outlier detection, so its average is not tested."));
    }
    host.appendChild(h("div", { class: "an-actions" },
      h("button", { type: "button", class: "btn", onclick: function () {
        SP.explorer.setPeriod(state.gran, p.id);
        U.scrollToEl($("reviews"));
      } }, "Open in review explorer"),
      h("button", { type: "button", class: "btn btn-ghost", onclick: clearSelection }, "Show whole dataset")));
  }

  // ---- "Why did sentiment drop?" ---------------------------------------------------------
  function currentBlock() {
    var c = state.data.complaints;
    return state.selectedId ? c[state.gran][state.selectedId] : c.overall;
  }

  function renderWhy() {
    var host = U.clear($("why-card"));
    var block = currentBlock();
    var p = selectedPeriod();
    host.appendChild(h("div", { class: "why-head" },
      h("h3", null, p ? "Why did sentiment drop here?" : "Most reported complaints (whole dataset)"),
      block ? h("span", { class: "badge " + (block.evidence === "sufficient" ? "" : "badge-warn") },
        block.evidence === "sufficient" ? "Evidence: " + block.negative_reviews + " negative reviews" : "Insufficient evidence") : null));

    if (!block) {
      host.appendChild(h("p", { class: "muted" }, "There is no complaint analysis for this period."));
      state.barHost = null;
      return;
    }
    host.appendChild(h("div", { class: "explain" }, block.explanation));

    state.barCats = block.categories;
    if (!block.categories.length) { state.barHost = null; return; }
    host.appendChild(h("p", { class: "bars-title" }, "Share of negative reviews that mention each category. Click a bar to filter the reviews below."));
    state.barHost = h("div", { class: "chart-wrap", style: "min-height:0" });
    host.appendChild(state.barHost);
    drawBars();

    host.appendChild(h("p", { class: "bars-title" }, "Example reviews per category"));
    block.categories.forEach(function (c) {
      var examples = (c.example_review_ids || []).map(function (id) { return state.reviewById[id]; }).filter(Boolean);
      if (!examples.length) return;
      host.appendChild(h("details", { class: "cat-examples" },
        h("summary", null, (state.catLabels[c.id] || c.id) + " (" + c.count + ")"),
        h("div", { class: "review-list" }, examples.map(function (r) { return U.reviewItem(r, state.catLabels); }))));
    });
  }

  function drawBars() {
    if (!state.barHost) return;
    SP.charts.drawComplaintBars(state.barHost, state.barCats, state.catLabels, {
      activeId: state.catFilter === "all" ? null : state.catFilter,
      onSelect: function (id) {
        state.catFilter = state.catFilter === id ? "all" : id;
        state.shown = REVIEWS_PER_STEP;
        drawBars();
        renderReviews();
      }
    });
  }

  // ---- the original reviews of the selected period ------------------------------------------
  function renderReviews() {
    var host = U.clear($("period-reviews"));
    var p = selectedPeriod();
    if (!p) {
      host.appendChild(h("div", { class: "empty-state" }, "Select a point on the trend chart to see the original reviews behind it."));
      return;
    }
    var all = (state.reviewsByPeriod[state.gran][p.id] || []).slice().sort(function (a, b) {
      return a.score - b.score || (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id);
    });
    var counts = { all: all.length, negative: 0, neutral: 0, positive: 0 };
    all.forEach(function (r) { counts[r.cls] += 1; });

    var list = all.filter(function (r) {
      return (state.clsFilter === "all" || r.cls === state.clsFilter) &&
             (state.catFilter === "all" || r.cats.indexOf(state.catFilter) !== -1);
    });

    var chips = h("div", { class: "chips-row" });
    [["all", "All"], ["negative", "Negative"], ["neutral", "Neutral"], ["positive", "Positive"]].forEach(function (f) {
      chips.appendChild(h("button", {
        type: "button", class: "fchip", "aria-pressed": String(state.clsFilter === f[0]),
        onclick: function () { state.clsFilter = f[0]; state.shown = REVIEWS_PER_STEP; renderReviews(); }
      }, f[1] + " (" + counts[f[0]] + ")"));
    });
    if (state.catFilter !== "all") {
      chips.appendChild(h("button", {
        type: "button", class: "fchip fchip-cat", title: "Remove this filter",
        onclick: function () { state.catFilter = "all"; state.shown = REVIEWS_PER_STEP; drawBars(); renderReviews(); }
      }, "Category: " + (state.catLabels[state.catFilter] || state.catFilter) + " ✕"));
    }

    host.appendChild(h("div", { class: "pr-head" },
      h("div", null, h("h3", null, "Original reviews · " + p.label),
        h("span", { class: "muted small" }, "Showing " + Math.min(state.shown, list.length) + " of " + list.length +
          " (lowest scores first). These are the database records counted in this period.")),
      chips));

    if (!list.length) {
      host.appendChild(h("p", { class: "muted" }, "No reviews match this filter."));
      return;
    }
    host.appendChild(h("div", { class: "review-list" }, list.slice(0, state.shown).map(function (r) {
      return U.reviewItem(r, state.catLabels);
    })));
    if (list.length > state.shown) {
      host.appendChild(h("div", { class: "more-row" }, h("button", {
        type: "button", class: "btn",
        onclick: function () { state.shown += REVIEWS_PER_STEP; renderReviews(); }
      }, "Show " + Math.min(REVIEWS_PER_STEP, list.length - state.shown) + " more")));
    }
  }

  // ============================================================================
  boot();
})(window);
