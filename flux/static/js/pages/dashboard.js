(function () {
  const { el, icon, api, inr, inr0, pageHead, txRow, deleteTx, addTransactionModal, onRefresh, CAT_COLORS } = window.Flux;
  const C = window.FluxCharts;

  function greeting(name) {
    const h = new Date().getHours();
    const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    return `${part}, ${name.split(" ")[0]}`;
  }

  async function render(main, user) {
    const content = el("div", { class: "stack", style: { gap: "16px" } });
    main.replaceChildren(content);
    const load = async () => {
      const [d, pending] = await Promise.all([api("/api/dashboard"), api("/api/pay/pending")]);
      content.replaceChildren(...build(d, user, pending).filter(Boolean));
    };
    onRefresh(load);
    await load();
  }

  function money(v) {
    const [whole, dec] = inr(v).split(".");
    return el("span", null, whole, dec ? el("span", { class: "dec" }, "." + dec) : null);
  }

  function pendingCard(p) {
    const done = async (status) => {
      try {
        const r = await api(`/api/pay/${p.id}/confirm`, { method: "POST", body: { status } });
        window.Flux.ok(status === "paid" ? `Logged ${inr(p.amount)} to ${p.payee_name}.` + (r.autosaved ? ` ${inr(r.autosaved)} auto-saved.` : "") : "Okay, not logged.");
        window.Flux.refresh();
      } catch (e) { window.Flux.err(e); }
    };
    return el("div", { class: "notice info", style: { alignItems: "center" } },
      el("div", { style: { flex: 1 } }, "Did your ", el("b", null, inr(p.amount)), " payment to ", el("b", null, p.payee_name || p.payee_vpa), " go through?"),
      el("button", { class: "btn sm primary", onclick: () => done("paid") }, "Yes, log it"),
      el("button", { class: "btn sm ghost", onclick: () => done("failed") }, "No"));
  }

  function build(d, user, pending) {
    const m = d.month;
    const sf = d.safe;
    const bankChip = d.bank
      ? el("span", { class: "delta", title: "Balance your bank reported in its latest SMS/statement" },
        "🏦 Bank says ", inr0(d.bank.balance), el("span", { class: "faint" }, " · " + window.Flux.dateFmt(d.bank.as_of)),
        d.reconcile.status === "in_sync" ? el("span", { class: "green" }, " · in sync") : d.reconcile.status === "drift" ? el("span", { class: "amber" }, " · check") : null)
      : null;
    const hero = el("section", { class: "hero" },
      el("div", null,
        el("div", { class: "eyebrow" }, greeting(user.name) + " · safe to spend today"),
        el("div", { class: "big" + (sf.status === "ok" ? "" : " amber"), style: { marginTop: "14px" } }, money(sf.left_today)),
        el("div", { class: "sub" }, sf.message),
        el("div", { class: "row wrap", style: { marginTop: "14px", gap: "8px" } },
          el("span", { class: "delta" }, "Available ", inr0(d.balance)),
          sf.bills_due ? el("span", { class: "delta" }, "Bills due ", inr0(sf.bills_due)) : null,
          sf.goal_reserve ? el("span", { class: "delta" }, "Goal plan ", inr0(sf.goal_reserve)) : null,
          bankChip)),
      el("div", { class: "actions" },
        el("a", { class: "btn primary lg", href: "/app/pay" }, icon("qr"), "Scan & Pay"),
        el("button", { class: "btn lg", onclick: () => addTransactionModal("expense") }, icon("plus"), "Add"),
        el("button", { class: "btn lg", onclick: () => window.FluxVoice && window.FluxVoice.open(true), "aria-label": "Ask Flux" }, icon("mic"))));
    const gap = d.bank_gap;
    const alignCard = d.bank && gap !== null && Math.abs(gap) >= 1 && d.reconcile.status !== "drift"
      ? el("div", { class: "notice info" }, "🏦 ", el("div", null,
          el("b", null, `Your bank shows ${inr0(d.bank.balance)}, Flux counts ${inr0(d.bank.balance - gap)} in the account. `),
          gap > 0 ? "Flux only knows money from after you started tracking. " : "Some spending before tracking, or cash, isn't in Flux yet. ",
          el("button", { class: "btn sm", style: { marginLeft: "6px" }, onclick: async () => {
            try { const r = await window.Flux.api("/api/ledger/align", { method: "POST" }); window.Flux.ok(`Matched to your bank. Available is now ${inr0(r.balance)}.`); window.Flux.refresh(); }
            catch (e) { window.Flux.err(e); } } }, "Match my bank")))
      : null;
    const recon = d.reconcile.status === "drift" ? el("div", { class: "notice caution" }, "🔎 ", el("div", null, el("b", null, "Something's missing. "), d.reconcile.message)) : null;
    const bills = sf.bills.length ? el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Coming up this month"), el("span", { class: "tiny faint" }, "detected from your history")),
      el("div", { class: "tx-list" }, sf.bills.map((b) => el("div", { class: "tx" },
        el("div", { class: "tx-icon" }, window.Flux.CAT_EMOJI[b.category] || "🔁"),
        el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, b.name), el("div", { class: "tx-sub" }, `${b.cadence} · due ${window.Flux.dateFmt(b.next_date)}`)),
        el("div", { class: "tx-amt" }, inr(b.amount)))))) : null;
    const stats = el("div", { class: "grid g-3" },
      el("div", { class: "card stat" }, el("div", { class: "label" }, "Spent in " + m.month.split(" ")[0]), el("div", { class: "value" }, inr0(m.expenses)),
        el("div", { class: "sub" }, `Projected ${inr0(d.forecast.projected_month_total)} by month end`)),
      el("div", { class: "card stat" }, el("div", { class: "label" }, "Saved in goals"), el("div", { class: "value green" }, inr0(d.total_saved)),
        el("div", { class: "sub" }, `${inr0(m.saved)} this month`)),
      el("div", { class: "card stat" }, el("div", { class: "label" }, "Money Health"),
        el("div", { class: "value" + (d.health.score == null ? "" : d.health.score >= 70 ? " green" : d.health.score >= 45 ? " amber" : " red") }, d.health.score == null ? "—" : d.health.score + "/100"),
        el("div", { class: "sub" }, m.savings_rate == null ? "Add income to see your savings rate" : `Savings rate ${m.savings_rate}% this month`)));


    // Spending chart + category donut
    const chartCard = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h2", null, "Last 30 days"), el("span", { class: "tiny faint" }, `Avg ${inr0(d.forecast.daily_average)}/day this month`)),
      d.series.some((x) => x.expense) ? C.bars(d.series) : el("div", { class: "empty" }, el("b", null, "No spending yet"), "Add an expense or import a statement to see your chart."));

    const cats = m.by_category.slice(0, 6);
    const catCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Where it went"), el("a", { class: "link", href: "/app/transactions" }, "See all")));
    if (cats.length) {
      catCard.appendChild(el("div", { class: "row", style: { gap: "20px", alignItems: "center" } },
        C.donut(cats, CAT_COLORS, { size: 132, label: inr0(m.expenses) }),
        el("div", { class: "legend", style: { flex: 1, minWidth: 0 } }, cats.map((c, i) =>
          el("div", { class: "row between" }, el("span", null, el("span", { class: "dot", style: { background: CAT_COLORS[i] } }), c.category),
            el("span", { class: "num muted" }, inr0(c.amount)))))));
    } else catCard.appendChild(el("div", { class: "empty" }, "Nothing spent this month yet."));

    // Health score
    const h = d.health;
    const healthCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Money Health"), el("a", { class: "link", href: "/app/coach" }, "Details")),
      el("div", { class: "row", style: { gap: "18px" } },
        el("div", { class: "score-ring" }, C.ring(h.score), el("div", { class: "center" }, el("div", null, el("div", { class: "big" }, h.score == null ? "—" : String(h.score)), el("div", { class: "tiny faint" }, "of 100")))),
        el("div", { class: "small muted", style: { flex: 1 } }, h.tips.length ? h.tips[0] : "You're doing great. Keep it up!")));

    // Budgets
    const budgetCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Budgets"), el("a", { class: "link", href: "/app/budgets" }, "Manage")));
    if (d.budgets.length) {
      d.budgets.slice(0, 4).forEach((b) => budgetCard.appendChild(el("div", { class: "budget-row" },
        el("div", { class: "row between small" }, el("span", null, b.category), el("span", { class: "num muted" }, `${inr0(b.spent)} / ${inr0(b.limit)}`)),
        el("div", { class: "bar " + b.state, style: { marginTop: "8px" } }, el("i", { style: { width: Math.min(100, b.percent) + "%" } })))));
    } else budgetCard.appendChild(el("div", { class: "empty" }, el("b", null, "No budgets yet"), 'Try saying "set food budget to 4000".'));

    // Goals
    const goalCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Goals"), el("a", { class: "link", href: "/app/goals" }, "View")));
    if (d.goals.length) {
      d.goals.slice(0, 3).forEach((g) => goalCard.appendChild(el("div", { class: "budget-row" },
        el("div", { class: "row between small" }, el("span", null, "🎯 " + g.title), el("span", { class: "num muted" }, g.percent + "%")),
        el("div", { class: "bar brand", style: { marginTop: "8px" } }, el("i", { style: { width: g.percent + "%" } })),
        el("div", { class: "tiny faint", style: { marginTop: "6px" } }, `${inr0(g.saved)} of ${inr0(g.target)}`))));
    } else goalCard.appendChild(el("div", { class: "empty" }, el("b", null, "No goals yet"), "Create one and every expense will round up into it."));

    // Recent
    const recent = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Recent activity"), el("a", { class: "link", href: "/app/transactions" }, "All transactions")));
    recent.appendChild(d.recent.length ? el("div", { class: "tx-list" }, d.recent.map((t) => txRow(t, deleteTx)))
      : el("div", { class: "empty" }, el("b", null, "Nothing here yet"), 'Tap the mic and say "spent 120 on lunch", or import your bank statement.'));

    const alerts = d.forecast.alerts.map((a) => el("div", { class: "notice caution" }, "⚠️ ", a));

    return [
      hero,
      ...pending.map(pendingCard),
      recon,
      alignCard,
      ...alerts,
      stats,
      bills,
      el("div", { class: "grid g-main" }, chartCard, catCard),
      el("div", { class: "grid g-3" }, healthCard, budgetCard, goalCard),
      recent,
    ];
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
