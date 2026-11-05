(function () {
  const { el, icon, api, download, err, inr0, pageHead, onRefresh, CAT_COLORS } = window.Kitna;
  const C = window.FluxCharts;

  async function render(main) {
    const top = el("div", { class: "stack" });
    const log = el("div", { class: "coach-log", "aria-live": "polite" });
    const q = el("input", { class: "input", maxlength: "500", placeholder: "Ask anything: “Why am I broke this month?”", "aria-label": "Ask the coach" });
    const askBtn = el("button", { class: "btn primary", type: "submit", "aria-label": "Ask" }, icon("send"));
    const ask = async (text) => {
      if (!text) return;
      log.appendChild(el("div", { class: "bubble me" }, text));
      const thinking = el("div", { class: "bubble flux" }, "Thinking…");
      log.appendChild(thinking);
      log.scrollTop = log.scrollHeight;
      askBtn.disabled = true;
      try {
        const r = await api("/api/coach", { method: "POST", body: { question: text } });
        thinking.textContent = r.answer;
      } catch (e) { thinking.textContent = e.message; }
      askBtn.disabled = false;
      log.scrollTop = log.scrollHeight;
    };
    const form = el("form", { class: "row", style: { marginTop: "12px" }, onsubmit: (e) => { e.preventDefault(); const t = q.value.trim(); q.value = ""; ask(t); } }, q, askBtn);
    const starters = ["How am I doing this month?", "Where can I cut spending?", "How long until I reach my goal?", "Is mahine ka summary do"];
    const coachCard = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h2", null, "Ask your coach"), el("span", { class: "tiny faint", id: "ai-state" })),
      el("p", { class: "small muted", style: { marginBottom: "12px" } }, "Answers use your real numbers. English, Hindi or Hinglish. Not financial advice."),
      log, el("div", { class: "chips", style: { marginTop: "10px" } }, starters.map((s) => el("button", { class: "chip", type: "button", onclick: () => ask(s) }, s))), form);

    main.replaceChildren(pageHead("Coach", "See how you're doing, and ask anything about your money.",
      el("button", { class: "btn", onclick: () => download("/api/reports/monthly.pdf", "flux-monthly-report.pdf").catch(err) }, icon("download"), "Monthly report (PDF)")),
      el("div", { class: "grid g-main" }, top, coachCard));

    async function load() { await window.Kitna.live("/api/insights", (ins) => paint(ins, window.Kitna.config)); }
    function paint(ins, me) {
      document.getElementById("ai-state").textContent = me.ai_available ? "AI coach on" : "Quick answers";
      const h = ins.health, f = ins.forecast, tm = ins.this_month, lm = ins.last_month;
      const scoreCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Money health")),
        el("div", { class: "row wrap", style: { gap: "24px", alignItems: "flex-start" } },
          el("div", { class: "score-ring" }, C.ring(h.score), el("div", { class: "center" }, el("div", null, el("div", { class: "big" }, h.score == null ? "—" : String(h.score)), el("div", { class: "tiny faint" }, "of 100")))),
          el("div", { style: { flex: 1, minWidth: "220px" } }, h.parts.map((p) => el("div", { class: "budget-row" },
            el("div", { class: "row between small" }, el("b", null, p.name), el("span", { class: "num muted" }, `${p.points}/${p.max}`)),
            el("div", { class: "bar " + (p.points / p.max >= 0.7 ? "ok" : p.points / p.max >= 0.4 ? "ahead" : "over"), style: { margin: "6px 0 4px" } }, el("i", { style: { width: (p.points / p.max) * 100 + "%" } })),
            el("div", { class: "tiny faint" }, p.detail))))),
        h.tips.length ? el("div", { class: "stack", style: { marginTop: "14px", gap: "8px" } }, h.tips.map((t) => el("div", { class: "notice info" }, icon("info"), el("div", null, t)))) : null,
        el("details", { class: "tiny faint", style: { marginTop: "12px" } }, el("summary", { style: { cursor: "pointer" } }, "How is this score worked out?"),
          el("p", { style: { marginTop: "6px" } }, "Savings (40) + budgets on track (25) + tracking habit (15) + safety buffer (20). It looks at your habits only. It is not a credit score.")));

      const fc = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Month-end forecast")),
        el("div", { class: "grid g-2" },
          el("div", { class: "stat" }, el("div", { class: "label" }, "Projected spending"), el("div", { class: "value" }, inr0(f.projected_month_total)), el("div", { class: "sub" }, `${inr0(f.spent_so_far)} spent so far · ${f.days_left} days left`)),
          el("div", { class: "stat" }, el("div", { class: "label" }, "Last month"), el("div", { class: "value muted" }, inr0(f.last_month_total)),
            el("div", { class: "sub" }, f.projected_left_over == null ? "Add income to see what's left" : `Projected left over: ${inr0(f.projected_left_over)}`))),
        f.alerts.length ? el("div", { class: "stack", style: { marginTop: "12px", gap: "8px" } }, f.alerts.map((a) => el("div", { class: "notice caution" }, icon("alert"), el("div", null, a)))) : null,
        null);

      const compare = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "This month vs last month")));
      const allCats = [...new Set([...tm.by_category, ...lm.by_category].map((c) => c.category))].slice(0, 8);
      if (allCats.length) {
        compare.appendChild(el("table", { class: "table" }, el("thead", null, el("tr", null, el("th", null, "Category"), el("th", { class: "right" }, "Last"), el("th", { class: "right" }, "This"), el("th", { class: "right" }, "Change"))),
          el("tbody", null, allCats.map((c, i) => {
            const a = (lm.by_category.find((x) => x.category === c) || { amount: 0 }).amount;
            const b = (tm.by_category.find((x) => x.category === c) || { amount: 0 }).amount;
            const d = b - a;
            return el("tr", null, el("td", null, el("span", { class: "dot", style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "2px", marginRight: "8px", background: CAT_COLORS[i % CAT_COLORS.length] } }), c),
              el("td", { class: "right num muted" }, inr0(a)), el("td", { class: "right num" }, inr0(b)),
              el("td", { class: "right num " + (d > 0 ? "red" : "green") }, (d > 0 ? "+" : "") + inr0(d)));
          }))));
      } else compare.appendChild(el("div", { class: "empty" }, "Not enough data yet."));
      const cb = ins.cashback;
      const cbCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Cashback vs spending"), el("span", { class: "tiny faint" }, `last ${cb.days} days`)),
        el("div", { class: "grid g-2" },
          el("div", { class: "stat" }, el("div", { class: "label" }, "Cashback received"), el("div", { class: "value" }, inr0(cb.cashback)), el("div", { class: "sub" }, `${cb.cashback_rate}% of spending`)),
          el("div", { class: "stat" }, el("div", { class: "label" }, "Everyday spending"), el("div", { class: "value" }, inr0(cb.spend)))),
        el("p", { class: "small muted", style: { marginTop: "14px" } }, cb.verdict));
      const rec = ins.recurring;
      const recCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Regular payments"),
        el("span", { class: "tiny faint" }, rec.length ? `≈ ${inr0(rec.reduce((a, b) => a + b.monthly_cost, 0))}/month` : "")),
        rec.length ? el("div", { class: "tx-list" }, rec.map((b) => el("div", { class: "tx" },
          window.Kitna.avatar(b.name),
          el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, b.name), el("div", { class: "tx-sub" }, `${b.cadence} · seen ${b.times_seen}× · next ${b.next_date}`)),
          el("div", { class: "tx-amt" }, inr0(b.amount)))))
          : el("div", { class: "empty" }, "Bills and subscriptions appear here once Kitna sees them repeat."));
      const ac = ins.accuracy;
      const accCard = ac.auto_logged ? el("div", { class: "card" },
        el("div", { class: "card-head" }, el("h2", null, "How well Kitna files your payments"), el("span", { class: "tiny faint" }, "measured from your fixes")),
        el("div", { class: "grid g-3" },
          el("div", { class: "stat" }, el("div", { class: "label" }, "Auto-logged"), el("div", { class: "value" }, String(ac.auto_logged))),
          el("div", { class: "stat" }, el("div", { class: "label" }, "You corrected"), el("div", { class: "value" }, String(ac.corrected))),
          el("div", { class: "stat" }, el("div", { class: "label" }, "Kept as filed"), el("div", { class: "value " + (ac.accuracy >= 90 ? "green" : "amber") }, ac.accuracy + "%"))),
        el("p", { class: "small muted", style: { marginTop: "14px" } }, "Tap any transaction to fix its category. Tick “always use this” and Kitna learns that merchant for good.")) : null;
      top.replaceChildren(scoreCard, fc, cbCard, recCard, ...(accCard ? [accCard] : []), compare);
    }
    onRefresh(load);
    await load();
    if (!log.children.length) log.appendChild(el("div", { class: "bubble flux" }, "Hi! I'm your Kitna coach. Ask me about your spending, budgets or goals."));
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
