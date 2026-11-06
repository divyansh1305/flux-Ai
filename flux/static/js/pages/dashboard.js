(function () {
  const onDay = (iso) => { const t = window.Kitna.dateFmt(iso); return t === "Today" ? "today" : t === "Yesterday" ? "yesterday" : "on " + t; };
  const { el, icon, api, inr0, txRow, addTransactionModal, planModal, onRefresh, CAT_COLORS, avatar, dateFmt } = window.Kitna;
  const C = window.FluxCharts;

  function greeting(name) {
    const h = new Date().getHours();
    const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    return `Hi, ${name.split(" ")[0]}`;
  }
  const shortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });

  // Start loading Home's numbers in parallel with the sign-in check instead of after it.
  let early = api("/api/dashboard", { allow401: true }).catch(() => null);

  async function render(main, user) {
    const content = el("div", { class: "stack narrow home" });
    content.replaceChildren(el("div", { class: "today" }, el("div", { class: "skeleton", style: { width: "40%", height: "14px" } }),
      el("div", { class: "skeleton", style: { width: "60%", height: "48px", marginTop: "12px" } }), el("div", { class: "skeleton", style: { width: "70%", height: "13px", marginTop: "12px" } })),
      window.Kitna.skeleton(3));
    main.replaceChildren(content);
    const load = async () => {
      const pre = early;
      early = null;
      try {
        await window.Kitna.live("/api/dashboard", (d) => content.replaceChildren(...build(d, user).filter(Boolean)), pre);
        markFresh(true);
      } catch (e) { markFresh(false); throw e; }
    };
    onRefresh(load);
    await load();
    fillWeek();
    window.Kitna.prefetch(["/api/meta", "/api/transactions?page=1&size=30", "/api/plans", "/api/insights", "/api/goals"]);
    const params = new URLSearchParams(location.search);
    if (params.get("gmail") === "connected") {
      window.Kitna.ok("Gmail connected. Your bank payments from the last 30 days are being added.");
      history.replaceState(null, "", "/app");
    }
    // Quietly check Gmail for new bank alerts (the server checks at most every 10 minutes).
    if ((window.Kitna.config.features || {}).gmail) {
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
        if (added) { window.Kitna.ok(`${added} new payment${added === 1 ? "" : "s"} added from Gmail.`); load(); }
      })();
    }
  }

  const section = (title, link, ...kids) => el("section", null,
    el("div", { class: "section-title" }, el("span", null, title), link || null), ...kids);

  async function alignBank() {
    try {
      const r = await api("/api/ledger/align", { method: "POST" });
      window.Kitna.ok(`Done. Kitna now matches your bank: ${inr0(r.balance)} available.`);
      window.Kitna.refresh();
    } catch (e) { window.Kitna.err(e); }
  }

  async function act(key, card) {
    if (card) card.remove();  // gone at once; the server catches up
    try { await api("/api/checks/dismiss", { method: "POST", body: { key } }); window.Kitna.refresh(); } catch (e) { window.Kitna.err(e); window.Kitna.refresh(); }
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

  // Setup: one clear next step at a time, never a checklist
  function nextStep(s) {
    if (s.complete) return null;
    const st = s.steps.find((x) => !x.done && (x.href || x.action || x.key === "plan"));
    if (!st) return null;
    try { if (localStorage.getItem("flux_setup_hidden") === st.key) return null; } catch (e) { /* storage blocked */ }
    const run = () => { if (st.action === "align") alignBank(); else if (st.key === "plan") planModal(); else if (st.href) location.href = st.href; };
    const card = el("div", { class: "next-step" },
      el("button", { type: "button", class: "next-main", onclick: run },
        el("span", { class: "next-ic" }, icon(st.key === "gmail" ? "msg" : st.key === "bank" ? "bank" : st.key === "plan" ? "calendar" : "check")),
        el("span", { class: "next-text" }, el("b", null, st.title), el("span", null, st.sub)),
        icon("chev")),
      el("button", { type: "button", class: "next-x", "aria-label": "Not now", onclick: () => { try { localStorage.setItem("flux_setup_hidden", st.key); } catch (e) { /* ignore */ } card.remove(); } }, icon("x")));
    return card;
  }

  // "How is this worked out?" in a sheet, in plain words
  function howSheet(sf) {
    const row = (label, amount) => el("div", { class: "how-row" }, el("span", null, label), el("b", { class: "num" }, amount));
    window.Kitna.modal("How Kitna works it out", el("div", { class: "how" },
      ...sf.lines.map((l) => row(l.label, (l.amount < 0 ? "− " : "") + inr0(Math.abs(l.amount)))),
      el("div", { class: "how-total" }, row(`Shared over ${sf.days_left} day${sf.days_left === 1 ? "" : "s"} till ${shortDate(sf.until)}`, inr0(sf.daily) + " a day")),
      sf.spent_today ? row("Already spent today", "− " + inr0(sf.spent_today)) : null,
      el("p", { class: "small muted" }, "Whatever you don't spend today is added to tomorrow."),
      sf.owed_to_you ? el("p", { class: "small muted" }, `Friends owe you ${inr0(sf.owed_to_you)}. It's added when they pay.`) : null),
      [{ label: "Got it", value: null, cls: "primary" }]);
  }

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
    const P = window.Kitna.push;
    try { if (localStorage.getItem("flux_remind_offer") === "no") return; } catch (e) { /* ignore */ }
    if (!P.supported() && !P.needsHomeScreen()) return;
    if (P.supported() && Notification.permission === "denied") return;
    if (await P.current()) return;
    const card = el("div", { class: "notice info", style: { alignItems: "center" } }, icon("bell"),
      el("div", { style: { flex: 1 } }, el("b", null, "Get a heads-up on your phone"),
        el("div", { class: "small" }, P.needsHomeScreen()
          ? "On iPhone: tap Share → Add to Home Screen, open Kitna from there, and turn on reminders for bills, late refunds and friends paying you back."
          : "Bills due tomorrow, late refunds, and when friends pay you back. At most 3 a day.")),
      P.needsHomeScreen() ? null : el("button", { class: "btn sm", onclick: async () => {
        try { const r = await P.enable(); card.remove(); window.Kitna.ok(r.test_sent ? "Reminders are on. You should see a test notification now." : "Reminders are on."); } catch (e) { window.Kitna.err(e); }
      } }, "Turn on"),
      el("button", { class: "icon-btn", "aria-label": "Not now", title: "Not now", onclick: () => { try { localStorage.setItem("flux_remind_offer", "no"); } catch (e) { /* ignore */ } card.remove(); } }, icon("x")));
    remindSlot.replaceChildren(card);
  }

  // "Updated 2:25 am": only once the server has answered; saved numbers say so.
  const asOfEl = el("div", { class: "as-of" }, el("span", { class: "dot-live wait" }), el("span", null, "Updating…"));
  function markFresh(ok) {
    asOfEl.firstChild.className = "dot-live" + (ok ? "" : " off");
    asOfEl.lastChild.textContent = ok ? "Updated " + new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })
      : "Offline. Showing your last saved numbers.";
  }

  function build(d, user) {
    const sf = d.safe;
    const safe = Math.max(0, Math.floor(sf.left_today));
    const setup = sf.status === "setup";

    // ── 1. One sentence: how much you can spend today
    const today = el("section", { class: "today" + (sf.status === "ok" || setup ? "" : " careful") },
      el("div", { class: "today-label" }, setup ? "Let's find out how much you can spend" : "You can spend today"),
      setup ? null : el("div", { class: "today-num num", "aria-label": inr0(safe) + " today" },
        el("span", { class: "cur", "aria-hidden": "true" }, "₹"), el("span", { "aria-hidden": "true" }, inr0(safe).replace("₹", ""))),
      el("div", { class: "today-sub" }, setup ? sf.message : sf.status === "ok" ? `Money for ${sf.days_left} more days, till ${shortDate(sf.until)}` : sf.message),
      setup ? el("a", { class: "btn primary block", href: "/onboarding" }, "Start (takes 1 minute)")
        : el("div", { class: "today-foot" }, asOfEl, el("button", { type: "button", class: "today-how", onclick: () => howSheet(sf) }, "How?")));

    // ── 2. Four big buttons
    const big = (ic, label, fn, main) => el("button", { class: "big-act" + (main ? " main" : ""), type: "button", onclick: fn },
      el("span", { class: "big-ic" }, icon(ic)), el("span", { class: "big-label" }, label));
    const actions = el("div", { class: "big-acts" },
      big("qr", "Scan & Pay", () => { location.href = "/app/pay"; }, true),
      big("plus", "Add payment", () => addTransactionModal("expense")),
      big("split", "Split bill", () => window.Kitna.splitModal()),
      big("calendar", "Upcoming", () => { location.href = "/app/plans"; }));

    // ── Only things that truly need you
    const g = d.gmail || {};
    const reconnect = g.connected && g.needs_reconnect
      ? el("div", { class: "notice caution", style: { alignItems: "center" } }, icon("alert"),
          el("div", { style: { flex: 1 } }, el("b", null, "Reconnect Gmail. "), "New payments from email won't show until you do."),
          el("a", { class: "btn sm", href: "/gmail/connect" }, "Reconnect"))
      : null;
    const drift = d.reconcile.status === "drift"
      ? el("div", { class: "notice caution" }, icon("alert"), el("div", null, el("b", null, "A payment may be missing. "), d.reconcile.message)) : null;
    const checks = (d.checks || []).slice(0, 2).map(checkCard);
    const asks = ((d.friends || {}).suggestions || []).slice(0, 1).map((x) => el("div", { class: "notice info", style: { alignItems: "flex-start" } }, icon("users"),
      el("div", { style: { flex: 1 } }, el("b", null, `Was the ${inr0(x.amount)} ${onDay(x.tx_date)} from ${x.person.split(" ")[0]}?`),
        el("div", { class: "row", style: { gap: "8px", marginTop: "10px" } },
          el("button", { class: "btn sm", onclick: async () => { try { await api(`/api/friends/${x.id}/settle`, { method: "POST", body: { transaction_id: x.suggested_tx_id } }); window.Kitna.ok("Ticked off."); window.Kitna.refresh(); } catch (e) { window.Kitna.err(e); } } }, "Yes"),
          el("button", { class: "btn sm ghost", onclick: async () => { try { await api(`/api/friends/${x.id}/not-them`, { method: "POST" }); window.Kitna.refresh(); } catch (e) { window.Kitna.err(e); } } }, "No")))));

    // ── 3. Recent payments
    const recent = section("Recent payments", el("a", { class: "link", href: "/app/transactions" }, "See all"),
      el("div", { class: "card list-card" }, d.recent.length
        ? el("div", { class: "tx-list" }, d.recent.slice(0, 5).map((t) => txRow(t)))
        : el("div", { class: "empty" }, el("b", null, "No payments yet"), "Tap Scan & Pay, or Add payment.")));

    // ── Coming up (only if something is)
    const upcoming = [
      ...sf.plans.filter((p) => p.kind !== "income").map((p) => ({ date: p.date, name: p.title, amount: p.amount })),
      ...sf.bills.map((b) => ({ date: b.next_date, name: b.name, amount: b.amount })),
    ].sort((a, b) => a.date.localeCompare(b.date)).slice(0, 3);
    const coming = !setup && upcoming.length ? section("Coming up", el("a", { class: "link", href: "/app/plans" }, "See all"),
      el("div", { class: "card list-card" }, el("div", { class: "tx-list" }, upcoming.map((u) => el("div", { class: "tx" },
        el("div", { class: "cat-ic" }, icon("calendar")),
        el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, u.name), el("div", { class: "tx-sub" }, dateFmt(u.date))),
        el("div", { class: "tx-amt" }, inr0(u.amount))))))) : null;

    // Only what matters: today's number, the four actions, anything that needs you, recent payments
    return [el("div", { class: "greet" }, greeting(user.name)), today, actions, reconnect, drift, ...checks, ...asks, nextStep(d.setup), recent];
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
