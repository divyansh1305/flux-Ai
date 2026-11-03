(function () {
  const { el, icon, api, inr, inr0, txRow, deleteTx, addTransactionModal, onRefresh, CAT_COLORS, avatar, dateFmt } = window.Flux;
  const C = window.FluxCharts;

  function greeting(name) {
    const h = new Date().getHours();
    const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    return `${part}, ${name.split(" ")[0]}`;
  }

  async function render(main, user) {
    const content = el("div", { class: "stack narrow", style: { gap: "18px" } });
    main.replaceChildren(content);
    const load = async () => {
      const payOn = (window.Flux.config.features || {}).pay;
      const [d, pending] = await Promise.all([api("/api/dashboard"), payOn ? api("/api/pay/pending") : Promise.resolve([])]);
      content.replaceChildren(...build(d, user, pending).filter(Boolean));
    };
    onRefresh(load);
    await load();
  }

  const section = (title, link, ...kids) => el("section", null,
    el("div", { class: "section-title" }, el("span", null, title), link || null), ...kids);

  async function alignBank() {
    try {
      const r = await api("/api/ledger/align", { method: "POST" });
      window.Flux.ok(`Done. Flux now matches your bank: ${inr0(r.balance)} available.`);
      window.Flux.refresh();
    } catch (e) { window.Flux.err(e); }
  }

  function pendingCard(p) {
    const done = async (status) => {
      try {
        const r = await api(`/api/pay/${p.id}/confirm`, { method: "POST", body: { status } });
        window.Flux.ok(status === "paid" ? `Saved ${inr(p.amount)} to ${p.payee_name}.` + (r.autosaved ? ` ${inr(r.autosaved)} put aside.` : "") : "Okay, not saved.");
        window.Flux.refresh();
      } catch (e) { window.Flux.err(e); }
    };
    return el("div", { class: "card row", style: { gap: "12px", alignItems: "center", flexWrap: "wrap" } },
      avatar(p.payee_name || p.payee_vpa),
      el("div", { style: { flex: 1, minWidth: "180px" } }, el("div", { style: { fontWeight: 600 } }, `Did your ${inr(p.amount)} payment go through?`),
        el("div", { class: "small muted" }, p.payee_name || p.payee_vpa)),
      el("div", { class: "row", style: { gap: "8px" } },
        el("button", { class: "btn sm ghost", onclick: () => done("failed") }, "No"),
        el("button", { class: "btn sm primary", onclick: () => done("paid") }, "Yes, it did")));
  }

  function setupCard(s) {
    if (s.complete) return null;
    try { if (localStorage.getItem("flux_setup_hidden") === String(s.done)) return null; } catch (e) { /* storage blocked */ }
    const run = (st) => {
      if (st.done) return;
      if (st.action === "income") addTransactionModal("income");
      else if (st.action === "align") alignBank();
      else if (st.href) location.href = st.href;
    };
    const card = el("div", { class: "card" },
      el("div", { class: "row between", style: { marginBottom: "6px" } },
        el("div", null, el("h2", null, "Let's get you set up"), el("div", { class: "progress-text", style: { marginTop: "2px" } }, `${s.done} of ${s.total} done · takes about 3 minutes`)),
        el("button", { class: "btn sm ghost", onclick: () => { try { localStorage.setItem("flux_setup_hidden", String(s.done)); } catch (e) { /* ignore */ } card.remove(); } }, "Later")),
      el("div", { class: "bar ok", style: { margin: "10px 0 6px" } }, el("i", { style: { width: (s.done / s.total) * 100 + "%" } })),
      el("div", { class: "setup" }, s.steps.map((st) => el("div", {
        class: "setup-step" + (st.done ? " done" : ""), role: st.done ? null : "button", tabindex: st.done ? null : "0",
        style: { cursor: st.done || (!st.href && !st.action) ? "default" : "pointer" },
        onclick: () => run(st), onkeydown: (e) => { if (e.key === "Enter") run(st); } },
        el("span", { class: "tick" }, icon("check")),
        el("div", { class: "s-main" }, el("div", { class: "s-title" }, st.title), st.done ? null : el("div", { class: "s-sub" }, st.sub)),
        st.done || (!st.href && !st.action) ? null : el("span", { class: "faint", style: { display: "grid" } }, icon("arrow"))))));
    return card;
  }

  function build(d, user, pending) {
    const m = d.month;
    const sf = d.safe;
    const safe = Math.max(0, Math.floor(sf.left_today));

    // ── Hero: one number that answers "can I spend today?"
    const meta = el("div", { class: "hero-meta" },
      el("span", null, "In your account ", el("b", null, inr0(d.balance))),
      sf.bills_due ? el("span", null, "Bills coming ", el("b", null, inr0(sf.bills_due))) : null,
      d.bank && d.reconcile.status === "in_sync" ? el("span", { class: "ok" }, icon("check"), "Matches your bank") : null);
    const hero = el("section", { class: "hero-card" },
      el("div", { class: "eyebrow" }, greeting(user.name)),
      el("div", { class: "hero-label", style: { marginTop: "14px" } }, "Safe to spend today"),
      el("div", { class: "hero" }, el("div", { class: "big" + (sf.status === "ok" ? "" : " amber"), style: { marginTop: "4px" } }, inr0(safe))),
      el("div", { class: "muted", style: { fontSize: "15px" } }, sf.status === "ok"
        ? (sf.bills_due ? "Your upcoming bills are already set aside." : "Spend up to this and you stay on track this month.")
        : sf.message),
      meta,
      el("div", { class: "hero-actions" },
        el("button", { class: "btn primary", onclick: () => addTransactionModal("expense") }, icon("plus"), "Add expense"),
        el("button", { class: "btn", onclick: () => window.FluxVoice && window.FluxVoice.open(false) }, icon("chat"), "Ask Flux")));

    // ── Bank match (gentle; the setup card covers it for brand-new users)
    const setupShowsBank = !d.setup.complete && d.setup.steps.some((s) => s.key === "bank" && !s.done && s.action === "align");
    const gap = d.bank_gap;
    const bankCard = d.bank && gap !== null && Math.abs(gap) >= 1 && d.reconcile.status !== "drift" && !setupShowsBank
      ? el("div", { class: "notice info", style: { alignItems: "center" } }, icon("bank"),
          el("div", { style: { flex: 1 } }, el("b", null, `Your bank says ${inr0(d.bank.balance)}.`), " Flux started counting later, so the numbers differ. Match them in one tap."),
          el("button", { class: "btn sm", onclick: alignBank }, "Match"))
      : null;
    const drift = d.reconcile.status === "drift"
      ? el("div", { class: "notice caution" }, icon("alert"), el("div", null, el("b", null, "A payment may be missing. "), d.reconcile.message)) : null;
    const alerts = d.forecast.alerts.slice(0, 2).map((a) => el("div", { class: "notice caution" }, icon("alert"), el("div", null, a)));

    // ── This month, as a simple list
    const h = d.health;
    const month = section("This month", el("a", { class: "link", href: "/app/coach" }, "Details"),
      el("div", { class: "card", style: { padding: "6px 20px" } },
        el("div", { class: "kv" }, el("div", { class: "k" }, "Spent", el("small", null, m.expenses ? `On track for ${inr0(d.forecast.projected_month_total)} by month end` : "Nothing yet this month")), el("div", { class: "v" }, inr0(m.expenses))),
        el("div", { class: "kv" }, el("div", { class: "k" }, "Money in"), el("div", { class: "v green" }, inr0(m.income))),
        el("div", { class: "kv" }, el("div", { class: "k" }, "Put aside for goals", el("small", null, `${inr0(d.total_saved)} saved in total`)), el("div", { class: "v" }, inr0(m.saved))),
        h.score != null ? el("div", { class: "kv" }, el("div", { class: "k" }, "Money health", el("small", null, h.tips[0] || "Looking good")),
          el("div", { class: "v " + (h.score >= 70 ? "green" : h.score >= 45 ? "amber" : "red") }, h.score + " / 100")) : null));

    const bills = sf.bills.length ? section("Coming up",
      el("span", { class: "tiny faint" }, "spotted from your history"),
      el("div", { class: "card", style: { padding: "4px 20px" } }, el("div", { class: "tx-list" }, sf.bills.map((b) => el("div", { class: "tx" },
        avatar(b.name),
        el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, b.name), el("div", { class: "tx-sub" }, `${b.cadence === "monthly" ? "Every month" : "Every week"} · next ${dateFmt(b.next_date)}`)),
        el("div", { class: "tx-amt" }, inr0(b.amount))))))) : null;

    const recent = section("Recent", el("a", { class: "link", href: "/app/transactions" }, "See all"),
      el("div", { class: "card", style: { padding: "4px 20px" } }, d.recent.length
        ? el("div", { class: "tx-list" }, d.recent.map((t) => txRow(t)))
        : el("div", { class: "empty" }, el("b", null, "No payments yet"), "Turn on automatic tracking, or tap Add expense.")));

    // ── Spending picture
    const cats = m.by_category.slice(0, 5);
    const spending = cats.length || d.series.some((x) => x.expense) ? section("Where your money went", null,
      el("div", { class: "card" },
        d.series.some((x) => x.expense) ? el("div", null, el("div", { class: "tiny faint", style: { marginBottom: "6px" } }, `Last 30 days · about ${inr0(d.forecast.daily_average)} a day`), C.bars(d.series)) : null,
        cats.length ? el("div", { class: "row wrap", style: { gap: "22px", alignItems: "center", marginTop: "16px" } },
          C.donut(cats, CAT_COLORS, { size: 120, label: inr0(m.expenses) }),
          el("div", { class: "legend", style: { flex: 1, minWidth: "180px" } }, cats.map((c, i) =>
            el("div", { class: "row between" }, el("span", null, el("span", { class: "dot", style: { background: CAT_COLORS[i] } }), c.category),
              el("span", { class: "num muted" }, inr0(c.amount)))))) : null)) : null;

    // ── Budgets & goals
    const budgetCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Budgets"), el("a", { class: "link", href: "/app/budgets" }, d.budgets.length ? "Manage" : "Set one")));
    if (d.budgets.length) {
      d.budgets.slice(0, 4).forEach((b) => budgetCard.appendChild(el("div", { class: "budget-row" },
        el("div", { class: "row between small" }, el("span", null, b.category), el("span", { class: "num muted" }, `${inr0(b.left > 0 ? b.left : 0)} left`)),
        el("div", { class: "bar " + b.state, style: { marginTop: "8px" } }, el("i", { style: { width: Math.min(100, b.percent) + "%" } })))));
    } else budgetCard.appendChild(el("p", { class: "small muted" }, "A budget tells Flux how much is okay to spend on something each month."));

    const goalCard = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Goals"), el("a", { class: "link", href: "/app/goals" }, d.goals.length ? "View" : "Add one")));
    if (d.goals.length) {
      d.goals.slice(0, 3).forEach((g) => goalCard.appendChild(el("div", { class: "budget-row" },
        el("div", { class: "row between small" }, el("span", null, g.title), el("span", { class: "num muted" }, `${inr0(g.saved)} of ${inr0(g.target)}`)),
        el("div", { class: "bar ok", style: { marginTop: "8px" } }, el("i", { style: { width: g.percent + "%" } })))));
    } else goalCard.appendChild(el("p", { class: "small muted" }, "Pick something to save for, and small round-ups from each payment go into it."));

    return [
      hero,
      ...pending.map(pendingCard),
      setupCard(d.setup),
      bankCard, drift, ...alerts,
      month,
      bills,
      recent,
      spending,
      el("div", { class: "grid g-2" }, budgetCard, goalCard),
    ];
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
