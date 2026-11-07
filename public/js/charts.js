/*
 * charts.js - the two D3 charts.
 *
 *   SP.charts.drawTrend(container, periods, options)         time-series of average sentiment
 *   SP.charts.drawComplaintBars(container, cats, labels, o)  horizontal bar chart of complaint categories
 *
 * The functions only DRAW what they are given (numbers computed by the Python
 * pipeline). They never compute statistics themselves.
 */
(function (root) {
  "use strict";
  var SP = (root.SP = root.SP || {});
  var U = SP.util, h = U.h;
  var chartCounter = 0; // makes clip-path ids unique if a chart is drawn twice

  function colorFor(avg) {
    return avg > 0 ? "var(--pos)" : avg < 0 ? "var(--neg)" : "var(--neu)";
  }

  // ---- tooltip content (built with DOM nodes, never innerHTML) -----------------
  function row(label, value) {
    return h("div", { class: "tt-row" }, h("span", null, label), h("b", null, value));
  }

  function tooltipContent(p, opts) {
    var box = h("div");
    box.appendChild(h("div", { class: "tt-title" }, p.label));
    if (p.review_count === 0) {
      box.appendChild(h("div", { class: "tt-note" }, "No reviews in this period. Shown as a gap, not as zero."));
      return box;
    }
    box.appendChild(row("Average score", U.fmtScore(p.avg_score, 2, true)));
    box.appendChild(row("Reviews", U.fmtInt(p.review_count)));
    box.appendChild(row("Positive / neutral / negative", p.positive + " / " + p.neutral + " / " + p.negative));
    if (p.delta === null) box.appendChild(row("vs previous period", "no earlier data"));
    else box.appendChild(row("vs previous period", U.fmtScore(p.delta, 2, true) + (p.prev_adjacent ? "" : " (after a gap)")));
    if (p.is_outlier) box.appendChild(h("div", { class: "tt-flag" }, "Flagged: unusually negative period"));
    if (opts.minReviews && p.review_count < opts.minReviews) {
      box.appendChild(h("div", { class: "tt-note" }, "Only " + p.review_count + " reviews (minimum " + opts.minReviews + " for outlier detection)."));
    }
    box.appendChild(h("div", { class: "tt-note" }, "Click to inspect these reviews."));
    return box;
  }

  // =============================================================================
  // Trend chart
  // opts: { gran, minReviews, selectedId, animate, onSelect(periodId) }
  // =============================================================================
  function drawTrend(container, periods, opts) {
    opts = opts || {};
    U.clear(container);

    var withData = periods.filter(function (p) { return p.avg_score !== null; });
    if (!withData.length) {
      container.appendChild(h("div", { class: "chart-msg" }, "There are no reviews to plot."));
      return;
    }

    var W = Math.max(280, container.clientWidth || 800);
    var H = W < 520 ? 290 : 390;
    var m = { top: 14, right: 16, bottom: 32, left: 50 };
    var iw = W - m.left - m.right;
    var ih = H - m.top - m.bottom;
    var id = ++chartCounter;

    // ---- scales ------------------------------------------------------------
    function startOf(p) { return U.parseISODate(p.start); }
    function endOf(p) { return d3.timeDay.offset(U.parseISODate(p.end), 1); } // exclusive end
    function mid(p) { return new Date((startOf(p).getTime() + endOf(p).getTime()) / 2); }

    var x = d3.scaleTime()
      .domain([d3.min(periods, startOf), d3.max(periods, endOf)])
      .range([0, iw]);

    // The y-range always contains 0 so the zero baseline is always visible.
    var values = withData.map(function (p) { return p.avg_score; });
    var lo = Math.min(0, d3.min(values));
    var hi = Math.max(0, d3.max(values));
    var pad = (hi - lo) * 0.12 || 1;
    var y = d3.scaleLinear().domain([lo - pad, hi + pad]).nice().range([ih, 0]);
    var y0 = y(0);

    var svg = d3.select(container).append("svg")
      .attr("viewBox", "0 0 " + W + " " + H)
      .attr("role", "img")
      .attr("aria-label", "Line chart of average sentiment score per " + (opts.gran === "month" ? "month" : "week") +
        ". Each point can be selected to inspect its reviews.");
    var defs = svg.append("defs");
    defs.append("clipPath").attr("id", "clip-up-" + id).append("rect").attr("width", iw).attr("height", Math.max(0, y0));
    defs.append("clipPath").attr("id", "clip-dn-" + id).append("rect").attr("y", y0).attr("width", iw).attr("height", Math.max(0, ih - y0));

    var g = svg.append("g").attr("transform", "translate(" + m.left + "," + m.top + ")");
    if (opts.animate && !U.prefersReducedMotion()) {
      g.style("opacity", 0).transition().duration(350).style("opacity", 1);
    }

    // ---- tooltip -----------------------------------------------------------
    var tip = h("div", { class: "tooltip", role: "tooltip" });
    container.appendChild(tip);
    function placeTip(px, py) {
      var tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = px + 14;
      if (left + tw > container.clientWidth) left = px - tw - 14;
      tip.style.left = Math.max(0, left) + "px";
      tip.style.top = Math.max(0, py - th - 12) + "px";
    }
    function showTip(p, px, py) {
      U.clear(tip);
      tip.appendChild(tooltipContent(p, opts));
      tip.classList.add("show");
      placeTip(px, py);
    }
    function hideTip() { tip.classList.remove("show"); }
    function mouseXY(event) {
      var r = container.getBoundingClientRect();
      return [event.clientX - r.left, event.clientY - r.top];
    }

    // ---- grid and "no reviews" bands --------------------------------------------
    g.append("g").selectAll("line").data(y.ticks(6)).join("line")
      .attr("class", "grid-line").attr("x1", 0).attr("x2", iw)
      .attr("y1", function (d) { return y(d); }).attr("y2", function (d) { return y(d); });

    periods.filter(function (p) { return p.review_count === 0; }).forEach(function (p) {
      var x1 = x(startOf(p)), x2 = x(endOf(p));
      g.append("rect")
        .attr("x", x1).attr("y", 0).attr("width", Math.max(3, x2 - x1)).attr("height", ih)
        .style("fill", "var(--neu-bg)").style("stroke", "var(--faint)")
        .style("stroke-dasharray", "3 3").style("stroke-width", 1)
        .on("mouseenter mousemove", function (event) { var xy = mouseXY(event); showTip(p, xy[0], xy[1]); })
        .on("mouseleave", hideTip);
    });

    // ---- area + line: green above zero, red below (same path, two clip regions) --------
    var defined = function (d) { return d.avg_score !== null; };
    var area = d3.area().defined(defined)
      .x(function (d) { return x(mid(d)); }).y0(y0).y1(function (d) { return y(d.avg_score); });
    var line = d3.line().defined(defined)
      .x(function (d) { return x(mid(d)); }).y(function (d) { return y(d.avg_score); });

    var plot = g.append("g").attr("class", "plot");
    [["up", "var(--pos)"], ["dn", "var(--neg)"]].forEach(function (pair) {
      plot.append("path").datum(periods).attr("d", area)
        .attr("clip-path", "url(#clip-" + pair[0] + "-" + id + ")")
        .style("fill", pair[1]).style("opacity", 0.18);
    });
    plot.append("line").attr("class", "zero-line").attr("x1", 0).attr("x2", iw).attr("y1", y0).attr("y2", y0);
    plot.append("text").attr("class", "zero-label").attr("text-anchor", "end").attr("x", iw - 2).attr("y", y0 + 13).text("0 = neutral");
    [["up", "var(--pos)"], ["dn", "var(--neg)"]].forEach(function (pair) {
      plot.append("path").datum(periods).attr("d", line)
        .attr("clip-path", "url(#clip-" + pair[0] + "-" + id + ")")
        .style("fill", "none").style("stroke", pair[1]).style("stroke-width", 2).style("stroke-linejoin", "round");
    });

    // ---- points ------------------------------------------------------------------------
    var R = opts.gran === "month" ? 7 : 4.5;
    function cx(p) { return x(mid(p)); }
    function cy(p) { return y(p.avg_score); }

    // ring around flagged outliers
    plot.selectAll("circle.ring").data(withData.filter(function (p) { return p.is_outlier; })).join("circle")
      .attr("class", "ring").attr("cx", cx).attr("cy", cy).attr("r", R + 7)
      .style("fill", "var(--neg-bg)").style("stroke", "var(--neg)").style("stroke-width", 1.5).style("pointer-events", "none");

    // ring around the selected point
    plot.selectAll("circle.sel").data(withData.filter(function (p) { return p.id === opts.selectedId; })).join("circle")
      .attr("class", "sel").attr("cx", cx).attr("cy", cy).attr("r", R + 5)
      .style("fill", "none").style("stroke", "#ffffff").style("stroke-width", 2).style("pointer-events", "none");

    var lowVolume = function (p) { return opts.minReviews && p.review_count < opts.minReviews; };
    plot.selectAll("circle.dot").data(withData).join("circle")
      .attr("class", "dot").attr("cx", cx).attr("cy", cy)
      .attr("r", function (p) { return p.is_outlier ? R + 1.5 : R; })
      .style("pointer-events", "none")
      .style("fill", function (p) { return lowVolume(p) ? "var(--panel)" : colorFor(p.avg_score); })
      .style("stroke", function (p) { return lowVolume(p) ? colorFor(p.avg_score) : "var(--panel)"; })
      .style("stroke-width", function (p) { return lowVolume(p) ? 2 : 1.5; });

    // ---- axes ----------------------------------------------------------------------------
    var monthStep = iw < 380 ? 2 : 1;
    var fmtMonth = d3.timeFormat("%b"), fmtMonthYear = d3.timeFormat("%b %Y");
    var xAxis = g.append("g").attr("class", "axis").attr("transform", "translate(0," + ih + ")")
      .call(d3.axisBottom(x).ticks(d3.timeMonth.every(monthStep)).tickSizeOuter(0)
        .tickFormat(function (d) { return d.getMonth() === 0 ? fmtMonthYear(d) : fmtMonth(d); }));
    xAxis.select(".domain").attr("class", "axis-line");
    xAxis.selectAll(".tick line").attr("class", "axis-line");

    g.append("g").attr("class", "axis")
      .call(d3.axisLeft(y).ticks(6).tickSize(0).tickPadding(8).tickFormat(function (d) { return U.fmtScore(d, 1); }))
      .select(".domain").remove();
    g.append("text").attr("class", "tick-label").attr("text-anchor", "middle")
      .attr("transform", "rotate(-90)").attr("x", -ih / 2).attr("y", -m.left + 12).text("Average sentiment score");

    // ---- interaction: one transparent, focusable hit circle per point (on top) ----------
    function activate(p) { if (opts.onSelect) opts.onSelect(p.id); }
    g.append("g").selectAll("circle").data(withData).join("circle")
      .attr("class", "pt hit").attr("cx", cx).attr("cy", cy).attr("r", 13)
      .attr("tabindex", 0).attr("role", "button")
      .attr("aria-label", function (p) {
        return p.label + ": average " + U.fmtScore(p.avg_score, 2, true) + ", " + p.review_count + " reviews" +
          (p.is_outlier ? ", flagged negative outlier" : "") + ". Press Enter to inspect.";
      })
      .on("mouseenter mousemove", function (event, p) { var xy = mouseXY(event); showTip(p, xy[0], xy[1]); })
      .on("mouseleave blur", hideTip)
      .on("focus", function (event, p) { showTip(p, cx(p) + m.left, cy(p) + m.top); })
      .on("click", function (event, p) { activate(p); })
      .on("keydown", function (event, p) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(p); }
      });
  }

  // =============================================================================
  // Complaint bar chart: bar length = share of negative reviews (0-100 %)
  // cats: [{id, count, pct}], labels: {id: "Delivery & shipping"}
  // opts: { activeId, onSelect(categoryId) }
  // =============================================================================
  function truncate(text, max) {
    return text.length > max ? text.slice(0, Math.max(1, max - 1)) + "…" : text;
  }

  function drawComplaintBars(container, cats, labels, opts) {
    opts = opts || {};
    U.clear(container);
    if (!cats.length) {
      container.appendChild(h("div", { class: "chart-msg" }, "No complaint categories to show."));
      return;
    }
    var W = Math.max(260, container.clientWidth || 400);
    var rowH = 32;
    var labelW = Math.min(190, Math.round(W * 0.42));
    var valueW = 86;
    var barX = labelW + 8;
    var barW = Math.max(40, W - barX - valueW);
    var H = cats.length * rowH + 8;
    var x = d3.scaleLinear().domain([0, 100]).range([0, barW]);

    var svg = d3.select(container).append("svg")
      .attr("viewBox", "0 0 " + W + " " + H).attr("role", "group")
      .attr("aria-label", "Complaint categories as a share of negative reviews");

    var rows = svg.selectAll("g.bar-row").data(cats).join("g")
      .attr("class", "bar-row")
      .attr("transform", function (d, i) { return "translate(0," + (i * rowH + 4) + ")"; })
      .attr("tabindex", 0).attr("role", "button")
      .attr("aria-pressed", function (d) { return String(d.id === opts.activeId); })
      .attr("aria-label", function (d) {
        return (labels[d.id] || d.id) + ": " + d.count + " negative reviews, " + d.pct +
          " percent. Activate to filter the reviews below.";
      })
      .on("click", function (event, d) { if (opts.onSelect) opts.onSelect(d.id); })
      .on("keydown", function (event, d) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (opts.onSelect) opts.onSelect(d.id); }
      });

    rows.append("title").text(function (d) { return labels[d.id] || d.id; });
    rows.append("text").attr("class", "bar-label").attr("x", 0).attr("y", 15)
      .text(function (d) { return truncate(labels[d.id] || d.id, Math.floor(labelW / 6.6)); });
    rows.append("rect").attr("class", "bar-track").attr("x", barX).attr("y", 3).attr("width", barW)
      .attr("height", 16).attr("rx", 8)
      .style("stroke", function (d) { return d.id === opts.activeId ? "var(--accent)" : "none"; })
      .style("stroke-width", 2);
    rows.append("rect").attr("class", "bar-fill").attr("x", barX).attr("y", 3).attr("height", 16).attr("rx", 8)
      .attr("width", function (d) { return Math.max(4, x(d.pct)); })
      .style("fill", function (d) { return d.id === "other" ? "var(--neu)" : null; });
    rows.append("text").attr("class", "bar-value").attr("x", W).attr("y", 15).attr("text-anchor", "end")
      .text(function (d) { return d.count + " · " + U.fmtPct(d.pct); });
  }

  SP.charts = { drawTrend: drawTrend, drawComplaintBars: drawComplaintBars };
})(window);
