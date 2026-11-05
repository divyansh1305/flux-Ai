(function () {
  const onDay = (iso) => { const t = window.Flux.dateFmt(iso); return t === "Today" ? "today" : t === "Yesterday" ? "yesterday" : "on " + t; };
  const { el, icon, api, inr0, txRow, addTransactionModal, planModal, onRefresh, CAT_COLORS, avatar, dateFmt } = window.Flux;
  const C = window.FluxCharts;

  function greeting(name) {
    const h = new Date().getHours();
    const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    return `${part}, ${name.split(" ")[0]}`;
  }
  const shortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });

  // Start loading Home's numbers in parallel with the sign-in check instead of after it.
  let early = api("/api/dashboard", { allow401: true }).catch(() => null);

  async function render(main, user) {
    const content = el("div", { class: "stack narrow", style: { gap: "18px" } });
    main.replaceChildren(content);
    const load = async () => {
      const pre = early;
      early = null;
      await window.Flux.live("/api/dashboard", (d) => content.replaceChildren(...build(d, user).filter(Boolean)), pre);
    };
    onRefresh(load);
    await load();
    fillWeek();
    fillRemind();
    window.Flux.prefetch(["/api/meta", "/api/transactions?page=1&size=30", "/api/plans", "/api/insights", "/api/goals"]);
    const params = new URLSearchParams(location.search);
    if (params.get("gmail") === "connected") {
      window.Flux.ok("Gmail connected. Your bank payments from the last 30 days are being added.");
      history.replaceState(null, "", "/app");
    }
    // Quietly check Gmail for new bank alerts (the server checks at most every 10 minutes).
    if ((window.Flux.config.features || {}).gmail) {
      // Small batches, one after another, so the page never waits on Gmail and nothing else gets stuck behind it.
      (async () => {
        let added = 0;
        for (let i = 0; i < 6; i++) {
          let r;
          try { r = await api("/api/gmail/sync", { method: "POST", body: { force: i > 0 } }); } catch (e) { return; }
          if (!r || !r.connected) return;
          added += r.logged || 0;
          if (r.needs_reconnect) { load(); return; }
          if (!r.more) break;
        }
        if (added) { window.Flux.ok(`${added} new payment${added === 1 ? "" : "s"} added from Gmail.`); load(); }
      })();
    }
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

  async function act(key, card) {
    if (card) card.remove();  // gone at once; the server catches up
    try { await api("/api/checks/dismiss", { method: "POST", body: { key } }); window.Flux.refresh(); } catch (e) { window.Flux.err(e); window.Flux.refresh(); }
  }

  function checkCard(c) {
    const card = el("div", { class: "notice " + (c.level === "caution" ? "caution" : "info"), style: { alignItems: "flex-start" } },
      icon(c.type === "refund" ? "repeat" : c.type === "price" ? "trend" : "alert"),
      el("div", { style: { flex: 1 } },
        el("b", null, c.title),
        el("div", { class: "small", style: { marginTop: "4px" } }, c.body),
        c.ref ? el("div", { class: "tiny faint", style: { marginTop: "4px" } }, "Bank reference: " + c.ref) : null,
        el("div", { class: "row", style: { gap: "8px", marginTop: "10px", flexWrap: "wrap" } },
          c.actions.map((a, i) => el("button", { class: "btn sm" + (i === 0 ? "" : " ghost"), onclick: () => act(a.key, card) }, a.label)))));
    return card;
  }

  function setupCard(s) {
    if (s.complete) return null;
    try { if (localStorage.getItem("flux_setup_hidden") === String(s.done)) return null; } catch (e) { /* storage blocked */ }
    const clickable = (st) => !st.done && (st.href || st.action || st.key === "plan");
    const run = (st) => {
      if (st.done) return;
      if (st.action === "align") alignBank();
      else if (st.key === "plan") planModal();
      else if (st.href) location.href = st.href;
    };
    const card = el("div", { class: "card" },
      el("div", { class: "row between", style: { marginBottom: "6px" } },
        el("div", null, el("h2", null, "Make today's number yours"), el("div", { class: "progress-text", style: { marginTop: "2px" } }, `${s.done} of ${s.total} done`)),
        el("button", { class: "btn sm ghost", onclick: () => { try { localStorage.setItem("flux_setup_hidden", String(s.done)); } catch (e) { /* ignore */ } card.remove(); } }, "Later")),
      el("div", { class: "bar ok", style: { margin: "10px 0 6px" } }, el("i", { style: { width: (s.done / s.total) * 100 + "%" } })),
      el("div", { class: "setup" }, s.steps.map((st) => el("div", {
        class: "setup-step" + (st.done ? " done" : ""), role: clickable(st) ? "button" : null, tabindex: clickable(st) ? "0" : null,
        style: { cursor: clickable(st) ? "pointer" : "default" },
        onclick: () => run(st), onkeydown: (e) => { if (e.key === "Enter") run(st); } },
        el("span", { class: "tick" }, icon("check")),
        el("div", { class: "s-main" }, el("div", { class: "s-title" }, st.title), st.done ? null : el("div", { class: "s-sub" }, st.sub)),
        clickable(st) ? el("span", { class: "faint", style: { display: "grid" } }, icon("arrow")) : null))));
    return card;
  }

  // ── The Sunday note (shown Sunday and Monday, or when opened from the reminder)
  const weekSlot = el("div");
  const remindSlot = el("div");
  async function fillWeek() {
    const forced = new URLSearchParams(location.search).get("week") === "1";
    const day = new Date().getDay();
    if (!forced && day !== 0 && day !== 1) return;
    let n;
    try { n = await api("/api/weekly"); } catch (e) { return; }
    try { if (!forced && localStorage.getItem("flux_week_seen") === n.start) return; } catch (e) { /* ignore */ }
    if (!n.has_data) return;
    const card = el("div", { class: "card" },
      el("div", { class: "row between" }, el("h2", null, "Your week"), el("span", { class: "tiny faint" }, `${dateFmt(n.start)} – ${dateFmt(n.end)}`)),
      el("p", { style: { margin: "10px 0 6px", fontSize: "16px" } }, n.headline),
      el("ul", { class: "small muted", style: { paddingLeft: "18px", margin: "6px 0 0", lineHeight: 1.8 } }, n.lines.map((l) => el("li", null, l))),
      el("button", { class: "btn sm ghost", style: { marginTop: "10px" }, onclick: () => { try { localStorage.setItem("flux_week_seen", n.start); } catch (e) { /* ignore */ } card.remove(); } }, "Got it"));
    weekSlot.replaceChildren(card);
  }
  // ── Offer reminders once, only where the phone can actually show them
  async function fillRemind() {
    const P = window.Flux.push;
    try { if (localStorage.getItem("flux_remind_offer") === "no") return; } catch (e) { /* ignore */ }
    if (!P.supported() && !P.needsHomeScreen()) return;
    if (P.supported() && Notification.permission === "denied") return;
    if (await P.current()) return;
    const card = el("div", { class: "notice info", style: { alignItems: "center" } }, icon("bell"),
      el("div", { style: { flex: 1 } }, el("b", null, "Get a heads-up on your phone"),
        el("div", { class: "small" }, P.needsHomeScreen()
          ? "On iPhone: tap Share → Add to Home Screen, open Flux from there, and turn on reminders for bills, late refunds and friends paying you back."
          : "Bills due tomorrow, late refunds, and when friends pay you back. At most 3 a day.")),
      P.needsHomeScreen() ? null : el("button", { class: "btn sm", onclick: async () => {
        try { const r = await P.enable(); card.remove(); window.Flux.ok(r.test_sent ? "Reminders are on. You should see a test notification now." : "Reminders are on."); } catch (e) { window.Flux.err(e); }
      } }, "Turn on"),
      el("button", { class: "icon-btn", "aria-label": "Not now", title: "Not now", onclick: () => { try { localStorage.setItem("flux_remind_offer", "no"); } catch (e) { /* ignore */ } card.remove(); } }, icon("x")));
    remindSlot.replaceChildren(card);
  }

  function build(d, user) {
    const m = d.month;
    const sf = d.safe;
    const safe = Math.max(0, Math.floor(sf.left_today));

    // ── Hero: one number that answers "can I spend today?", with the maths one tap away
    const why = el("div", { hidden: true, style: { marginTop: "12px" } },
      ...sf.lines.map((l) => el("div", { class: "row between small", style: { padding: "4px 0" } },
        el("span", { class: "muted" }, l.label), el("span", { class: "num" }, (l.amount < 0 ? "− " : "") + inr0(Math.abs(l.amount))))),
      el("div", { class: "row between small", style: { padding: "6px 0", borderTop: "1px solid var(--line)", marginTop: "4px" } },
        el("span", null, `÷ ${sf.days_left} day${sf.days_left === 1 ? "" : "s"} until ${shortDate(sf.until)}`), el("b", { class: "num" }, inr0(sf.daily) + " a day")),
      sf.spent_today ? el("div", { class: "row between small", style: { padding: "4px 0" } }, el("span", { class: "muted" }, "Spent today"), el("span", { class: "num" }, "− " + inr0(sf.spent_today))) : null,
      el("p", { class: "tiny faint", style: { marginTop: "6px" } }, "Whatever you don't spend today stays in the pool, so tomorrow's number goes up."));
    const whyBtn = el("button", { class: "link", type: "button", style: { background: "none", border: 0, padding: 0, cursor: "pointer", font: "inherit" },
      onclick: () => { why.hidden = !why.hidden; whyBtn.textContent = why.hidden ? "How is this worked out?" : "Hide the maths"; } }, "How is this worked out?");

    const heroText = sf.status === "ok"
      ? `Until ${shortDate(sf.until)}, ${sf.until_label}.` + (sf.bills_due || sf.plans_reserved ? " Bills and plans are already kept aside." : "")
      : sf.message;
    const hero = el("section", { class: "hero-card" },
      el("div", { class: "eyebrow" }, greeting(user.name)),
      el("div", { class: "hero-label", style: { marginTop: "14px" } }, sf.confirmed || sf.status === "setup" ? "Safe to spend today" : "Safe to spend today (about)"),
      el("div", { class: "hero" }, el("div", { class: "big" + (sf.status === "ok" ? "" : " amber"), style: { marginTop: "4px" } },
        sf.status === "setup" ? "—" : inr0(safe))),
      el("div", { class: "muted", style: { fontSize: "15px" } }, heroText),
      sf.maybe_extra_daily ? el("div", { class: "small muted", style: { marginTop: "6px" } }, `If the money you're not sure about arrives: about ${inr0(sf.maybe_extra_daily)} more a day.`) : null,
      sf.owed_to_you ? el("a", { href: "/app/friends", class: "small muted", style: { display: "block", marginTop: "6px" } },
        `Friends owe you ${inr0(sf.owed_to_you)}. Counted once it arrives →`) : null,
      sf.status === "setup" ? null : el("div", { style: { marginTop: "10px" } }, whyBtn, why),
      el("div", { class: "hero-actions" },
        el("button", { class: "btn primary", onclick: () => addTransactionModal("expense") }, icon("plus"), "Add expense"),
        el("button", { class: "btn", onclick: () => planModal() }, icon("calendar"), "Add a plan")));

    // ── Things that need the user (only when real)
    const g = d.gmail || {};
    const reconnect = g.connected && g.needs_reconnect
      ? el("div", { class: "notice caution", style: { alignItems: "center" } }, icon("alert"),
          el("div", { style: { flex: 1 } }, el("b", null, "Gmail stopped sharing bank emails with Flux. "), "New email payments won't show up until you reconnect. It takes one tap."),
          el("a", { class: "btn sm", href: "/gmail/connect" }, "Reconnect"))
      : null;
    const setupShowsBank = !d.setup.complete && d.setup.steps.some((s) => s.key === "bank" && !s.done && s.action === "align");
    const gap = d.bank_gap;
    const bankCard = d.bank && gap !== null && Math.abs(gap) >= 1 && d.reconcile.status !== "drift" && !setupShowsBank
      ? el("div", { class: "notice info", style: { alignItems: "center" } }, icon("bank"),
          el("div", { style: { flex: 1 } }, el("b", null, `Your bank shows ${inr0(d.bank.balance)}, Flux shows ${inr0(d.balance)}.`), " Flux started counting later. Match them in one tap."),
          el("button", { class: "btn sm", onclick: alignBank }, "Match"))
      : null;
    const drift = d.reconcile.status === "drift"
      ? el("div", { class: "notice caution" }, icon("alert"), el("div", null, el("b", null, "A payment may be missing. "), d.reconcile.message)) : null;
    const checks = (d.checks || []).slice(0, 4).map(checkCard);
    const asks = ((d.friends || {}).suggestions || []).map((x) => el("div", { class: "notice info", style: { alignItems: "flex-start" } }, icon("users"),
      el("div", { style: { flex: 1 } }, el("b", null, `Was the ${inr0(x.amount)} ${onDay(x.tx_date)} from ${x.person.split(" ")[0]}?`),
        el("div", { class: "small", style: { marginTop: "4px" } }, "Your bank didn't say who sent it."),
        el("div", { class: "row", style: { gap: "8px", marginTop: "10px" } },
          el("button", { class: "btn sm", onclick: async () => { try { await api(`/api/friends/${x.id}/settle`, { method: "POST", body: { transaction_id: x.suggested_tx_id } }); window.Flux.ok("Ticked off."); window.Flux.refresh(); } catch (e) { window.Flux.err(e); } } }, "Yes"),
          el("button", { class: "btn sm ghost", onclick: async () => { try { await api(`/api/friends/${x.id}/not-them`, { method: "POST" }); window.Flux.refresh(); } catch (e) { window.Flux.err(e); } } }, "No")))));

    // ── Coming up: plans + bills before the next money
    const upcoming = [
      ...sf.plans.map((p) => ({ date: p.date, name: p.title, amount: p.amount, sub: p.kind === "income" ? (p.sure ? "Money coming in" : "Maybe coming in") : "Your plan", income: p.kind === "income" })),
      ...sf.bills.map((b) => ({ date: b.next_date, name: b.name, amount: b.amount, sub: b.cadence === "monthly" ? "Repeats every month" : "Repeats every week" })),
    ].sort((a, b) => a.date.localeCompare(b.date)).slice(0, 6);
    const coming = sf.status === "setup" ? null : section("Coming up before " + shortDate(sf.until), el("a", { class: "link", href: "/app/plans" }, "Plans"),
      el("div", { class: "card", style: { padding: "4px 20px" } }, upcoming.length
        ? el("div", { class: "tx-list" }, upcoming.map((u) => el("div", { class: "tx" }, avatar(u.name),
            el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, u.name), el("div", { class: "tx-sub" }, `${u.sub} · ${dateFmt(u.date)}`)),
            el("div", { class: "tx-amt" + (u.income ? " green" : "") }, (u.income ? "+" : "") + inr0(u.amount)))))
        : el("div", { class: "empty" }, el("b", null, "Nothing planned yet"), "Going out on Friday? Add it as a plan and Flux keeps the money aside.")));

    const recent = section("Recent", el("a", { class: "link", href: "/app/transactions" }, "See all"),
      el("div", { class: "card", style: { padding: "4px 20px" } }, d.recent.length
        ? el("div", { class: "tx-list" }, d.recent.map((t) => txRow(t)))
        : el("div", { class: "empty" }, el("b", null, "No payments yet"), "Connect your payments in Settings, or tap Add expense.")));

    const month = section("This month", el("a", { class: "link", href: "/app/coach" }, "Details"),
      el("div", { class: "card", style: { padding: "6px 20px" } },
        el("div", { class: "kv" }, el("div", { class: "k" }, "Spent", el("small", null, m.expenses ? `About ${inr0(d.forecast.daily_average)} a day` : "Nothing yet this month")), el("div", { class: "v" }, inr0(m.expenses))),
        el("div", { class: "kv" }, el("div", { class: "k" }, "Money in"), el("div", { class: "v green" }, inr0(m.income))),
        m.saved ? el("div", { class: "kv" }, el("div", { class: "k" }, "Set aside for goals", el("small", null, "Still in your bank, not counted as spendable")), el("div", { class: "v" }, inr0(m.saved))) : null));

    const cats = m.by_category.slice(0, 5);
    const spending = cats.length || d.series.some((x) => x.expense) ? section("Where your money went", null,
      el("div", { class: "card" },
        d.series.some((x) => x.expense) ? el("div", null, el("div", { class: "tiny faint", style: { marginBottom: "6px" } }, `Last 30 days · about ${inr0(d.forecast.daily_average)} a day`), C.bars(d.series)) : null,
        cats.length ? el("div", { class: "row wrap", style: { gap: "22px", alignItems: "center", marginTop: "16px" } },
          C.donut(cats, CAT_COLORS, { size: 120, label: inr0(m.expenses) }),
          el("div", { class: "legend", style: { flex: 1, minWidth: "180px" } }, cats.map((c, i) =>
            el("div", { class: "row between" }, el("span", null, el("span", { class: "dot", style: { background: CAT_COLORS[i] } }), c.category),
              el("span", { class: "num muted" }, inr0(c.amount)))))) : null)) : null;

    return [hero, reconnect, ...checks, ...asks, weekSlot, remindSlot, setupCard(d.setup), bankCard, drift, coming, recent, month, spending];
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
