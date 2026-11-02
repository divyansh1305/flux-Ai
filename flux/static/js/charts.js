/* Tiny dependency-free SVG charts (no CDN scripts, works with a strict CSP). */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, ...kids) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    kids.forEach((k) => n.appendChild(typeof k === "string" ? document.createTextNode(k) : k));
    return n;
  }

  // Daily spending bars for the last N days.
  function bars(series, { height = 170 } = {}) {
    const W = 640, H = height, padB = 22, padT = 10, padL = 48;
    const max = Math.max(1, ...series.map((d) => d.expense));
    const bw = (W - padL) / series.length;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Daily spending, last 30 days" });
    [0.5, 1].forEach((f) => {
      const y = padT + (H - padB - padT) * (1 - f);
      svg.appendChild(s("line", { x1: padL, x2: W, y1: y, y2: y, stroke: "#1f1f1f" }));
      svg.appendChild(s("text", { x: padL - 6, y: y + 3, "text-anchor": "end" }, "₹" + Math.round(max * f).toLocaleString("en-IN")));
    });
    series.forEach((d, i) => {
      const h = (d.expense / max) * (H - padB - padT);
      const x = padL + i * bw + bw * 0.18;
      const r = s("rect", { x, y: H - padB - h, width: bw * 0.64, height: Math.max(h, d.expense ? 2 : 0), rx: 3,
        fill: i === series.length - 1 ? "#ff5a1f" : "#f5f5f4", opacity: d.expense ? 0.92 : 0.12 });
      r.appendChild(s("title", {}, `${d.date}: ₹${d.expense.toLocaleString("en-IN")}`));
      svg.appendChild(r);
      if ((series.length - 1 - i) % 7 === 0) {
        const dt = new Date(d.date + "T00:00:00");
        svg.appendChild(s("text", { x: x + bw * 0.32, y: H - 6, "text-anchor": "middle" }, dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" })));
      }
    });
    return svg;
  }

  // Category donut.
  function donut(items, colors, { size = 150, label = "" } = {}) {
    const total = items.reduce((a, b) => a + b.amount, 0) || 1;
    const R = 60, C = 2 * Math.PI * R;
    const svg = s("svg", { viewBox: "0 0 160 160", width: size, height: size, role: "img", "aria-label": "Spending by category" });
    svg.appendChild(s("circle", { cx: 80, cy: 80, r: R, fill: "none", stroke: "#242424", "stroke-width": 18 }));
    let offset = 0;
    items.forEach((it, i) => {
      const len = (it.amount / total) * C;
      const c = s("circle", { cx: 80, cy: 80, r: R, fill: "none", stroke: colors[i % colors.length], "stroke-width": 18,
        "stroke-dasharray": `${Math.max(len - 2, 0.1)} ${C}`, "stroke-dashoffset": -offset, transform: "rotate(-90 80 80)" });
      c.appendChild(s("title", {}, `${it.category}: ₹${it.amount.toLocaleString("en-IN")}`));
      svg.appendChild(c);
      offset += len;
    });
    if (label) {
      svg.appendChild(s("text", { x: 80, y: 78, "text-anchor": "middle", style: "font-size:17px;font-weight:800;fill:#f5f5f4" }, label));
      svg.appendChild(s("text", { x: 80, y: 96, "text-anchor": "middle", style: "font-size:10px;fill:#a3a3a3" }, "spent"));
    }
    return svg;
  }

  // Score ring 0–100.
  function ring(score) {
    const R = 56, C = 2 * Math.PI * R;
    const pct = score == null ? 0 : score / 100;
    const color = score == null ? "#333" : score >= 70 ? "#3ecf8e" : score >= 45 ? "#f5a623" : "#ff5c5c";
    const svg = s("svg", { viewBox: "0 0 132 132", width: 132, height: 132, "aria-hidden": "true" });
    svg.appendChild(s("circle", { cx: 66, cy: 66, r: R, fill: "none", stroke: "#242424", "stroke-width": 11 }));
    svg.appendChild(s("circle", { cx: 66, cy: 66, r: R, fill: "none", stroke: color, "stroke-width": 11, "stroke-linecap": "round",
      "stroke-dasharray": `${C * pct} ${C}`, transform: "rotate(-90 66 66)" }));
    return svg;
  }

  window.FluxCharts = { bars, donut, ring };
})();
