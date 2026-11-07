/*
 * review_explorer.js - the searchable review table and the single-review dialog.
 *
 *   SP.explorer.init(data, catLabels)   build the filters and the first page
 *   SP.explorer.setPeriod(gran, id)     filter to one week/month (used by the inspector)
 *   SP.explorer.openReview(review)      open the detail dialog for one review
 *
 * All filtering happens in the browser on the reviews that Python exported.
 */
(function (root) {
  "use strict";
  var SP = (root.SP = root.SP || {});
  var U = SP.util, h = U.h;
  var PAGE_SIZE = 15;

  var reviews = [];
  var catLabels = {};
  var periodLists = { week: [], month: [] };
  var periodLabels = { week: {}, month: {} };
  var filters, page;

  function $(id) { return document.getElementById(id); }

  function defaultFilters() {
    return { search: "", sentiment: "all", category: "all", gran: "all", period: "all", sort: "newest" };
  }

  // ---- filtering and sorting -----------------------------------------------------
  function matches(r) {
    if (filters.sentiment !== "all" && r.cls !== filters.sentiment) return false;
    if (filters.category !== "all" && r.cats.indexOf(filters.category) === -1) return false;
    if (filters.gran !== "all" && filters.period !== "all" && r[filters.gran] !== filters.period) return false;
    if (filters.search && r.text.toLowerCase().indexOf(filters.search) === -1) return false;
    return true;
  }

  var SORTS = {
    newest: function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id; },
    oldest: function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id; },
    negative: function (a, b) { return a.score - b.score || SORTS.oldest(a, b); },
    positive: function (a, b) { return b.score - a.score || SORTS.oldest(a, b); }
  };

  // ---- rendering ------------------------------------------------------------------
  function render() {
    var list = reviews.filter(matches).sort(SORTS[filters.sort]);
    var pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
    page = Math.min(Math.max(1, page), pages);
    var from = (page - 1) * PAGE_SIZE;
    var slice = list.slice(from, from + PAGE_SIZE);

    $("ex-count").textContent = list.length
      ? "Showing " + (from + 1) + "–" + (from + slice.length) + " of " + U.fmtInt(list.length) +
        " matching reviews (" + U.fmtInt(reviews.length) + " in total)."
      : "No reviews match these filters (" + U.fmtInt(reviews.length) + " in total).";
    $("ex-page").textContent = "Page " + page + " of " + pages;
    $("ex-prev").disabled = page <= 1;
    $("ex-next").disabled = page >= pages;

    var body = U.clear($("ex-body"));
    if (!slice.length) {
      body.appendChild(h("tr", { class: "table-empty" }, h("td", { colspan: 7 }, "Nothing to show. Try clearing a filter.")));
      return;
    }
    slice.forEach(function (r) {
      var tr = h("tr", { tabindex: 0, "aria-label": "Review " + r.id + ", open details" },
        h("td", { class: "date" }, U.fmtDate(r.date)),
        h("td", { class: "text" }, U.highlight(r.text, r.pos, r.neg)),
        h("td", { class: "num" }, U.scoreBadge(r.score)),
        h("td", null, U.classPill(r.cls)),
        h("td", null, h("div", { class: "cell-chips" }, U.wordChips(r.pos, "pos"))),
        h("td", null, h("div", { class: "cell-chips" }, U.wordChips(r.neg, "neg"))),
        h("td", null, r.cats.length
          ? h("div", { class: "cell-chips" }, U.categoryTags(r.cats, catLabels))
          : h("span", { class: "muted" }, "–")));
      tr.addEventListener("click", function () { openReview(r); });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openReview(r); }
      });
      body.appendChild(tr);
    });
  }

  function fillPeriodSelect() {
    var sel = U.clear($("ex-period"));
    sel.appendChild(h("option", { value: "all" }, "All"));
    if (filters.gran === "all") { sel.disabled = true; return; }
    periodLists[filters.gran].forEach(function (p) {
      if (p.review_count > 0) sel.appendChild(h("option", { value: p.id }, p.label + " (" + p.review_count + ")"));
    });
    sel.disabled = false;
    sel.value = filters.period;
  }

  function syncControls() {
    $("ex-search").value = filters.search;
    $("ex-sentiment").value = filters.sentiment;
    $("ex-category").value = filters.category;
    $("ex-gran").value = filters.gran;
    fillPeriodSelect();
    $("ex-sort").value = filters.sort;
  }

  // ---- detail dialog -----------------------------------------------------------------
  function openReview(r) {
    var dlg = $("review-dialog");
    $("dialog-title").textContent = "Review #" + r.id;
    var posN = r.pos.length, negN = r.neg.length;
    var body = U.clear($("dialog-body"));
    body.appendChild(h("p", { class: "review-text" }, U.highlight(r.text, r.pos, r.neg)));
    body.appendChild(h("dl", { class: "kv" },
      h("dt", null, "Date"), h("dd", null, U.fmtDate(r.date)),
      h("dt", null, "Week / month"), h("dd", null,
        (periodLabels.week[r.week] || r.week) + " · " + (periodLabels.month[r.month] || r.month)),
      h("dt", null, "Sentiment score"), h("dd", null, U.scoreBadge(r.score), U.classPill(r.cls)),
      h("dt", null, "How it was scored"), h("dd", null,
        posN + " positive match" + (posN === 1 ? "" : "es") + " − " + negN + " negative match" + (negN === 1 ? "" : "es") + " = " + U.fmtScore(r.score, 0, false)),
      h("dt", null, "Positive words"), h("dd", null, posN ? U.wordChips(r.pos, "pos") : h("span", { class: "muted" }, "none")),
      h("dt", null, "Negative words"), h("dd", null, negN ? U.wordChips(r.neg, "neg") : h("span", { class: "muted" }, "none")),
      h("dt", null, "Complaint categories"), h("dd", null, r.cats.length
        ? U.categoryTags(r.cats, catLabels)
        : h("span", { class: "muted" }, r.cls === "negative" ? "none" : "only negative reviews are categorised"))));
    if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); }
    else dlg.setAttribute("open", "");
  }

  // ---- public API ------------------------------------------------------------------------
  function setPeriod(gran, id) {
    filters = defaultFilters();
    filters.gran = gran;
    filters.period = id;
    page = 1;
    syncControls();
    render();
  }

  function init(data, labels) {
    reviews = data.reviews.reviews;
    catLabels = labels;
    periodLists = { week: data.timeseries.week, month: data.timeseries.month };
    ["week", "month"].forEach(function (g) {
      periodLists[g].forEach(function (p) { periodLabels[g][p.id] = p.label; });
    });
    filters = defaultFilters();
    page = 1;

    var catSel = $("ex-category");
    data.complaints.categories.forEach(function (c) { catSel.appendChild(h("option", { value: c.id }, c.label)); });

    function bind(id, key, event) {
      $(id).addEventListener(event || "change", function (e) {
        filters[key] = key === "search" ? e.target.value.trim().toLowerCase() : e.target.value;
        if (key === "gran") { filters.period = "all"; fillPeriodSelect(); }
        page = 1;
        render();
      });
    }
    $("ex-search").addEventListener("input", U.debounce(function (e) {
      filters.search = e.target.value.trim().toLowerCase();
      page = 1;
      render();
    }, 180));
    bind("ex-sentiment", "sentiment");
    bind("ex-category", "category");
    bind("ex-gran", "gran");
    bind("ex-period", "period");
    bind("ex-sort", "sort");
    $("ex-reset").addEventListener("click", function () { filters = defaultFilters(); page = 1; syncControls(); render(); });
    $("ex-prev").addEventListener("click", function () { page -= 1; render(); });
    $("ex-next").addEventListener("click", function () { page += 1; render(); });

    var dlg = $("review-dialog");
    $("dialog-close").addEventListener("click", function () { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg && dlg.close) dlg.close(); }); // click on backdrop

    syncControls();
    render();
  }

  SP.explorer = { init: init, setPeriod: setPeriod, openReview: openReview };
})(window);
