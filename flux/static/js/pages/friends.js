(function () {
  const onDay = (iso) => { const t = window.Kitna.dateFmt(iso); return t === "Today" ? "today" : t === "Yesterday" ? "yesterday" : "on " + t; };
  const { el, icon, api, inr0, inr, dateFmt, avatar, pageHead, onRefresh, ok, err, confirmBox, friendModal, splitModal } = window.Kitna;

  async function render(main) {
    const content = el("div", { class: "stack narrow", style: { gap: "18px" } });
    main.replaceChildren(pageHead("Friends", "Money you lent or borrowed. Ticked off by itself when the UPI payment arrives."), content);
    const load = () => window.Kitna.live("/api/friends", (d) => content.replaceChildren(...build(d).filter(Boolean)));
    onRefresh(load);
    await load();
  }

  async function remind(r) {
    try {
      const m = await api(`/api/friends/${r.id}/message`);
      if (navigator.share) {
        try { await navigator.share({ text: m.text }); return; } catch (e) { if (e && e.name === "AbortError") return; }
      }
      window.open("https://wa.me/?text=" + encodeURIComponent(m.text), "_blank", "noopener");
    } catch (e) { err(e); }
  }

  async function settle(r, txId) {
    try {
      await api(`/api/friends/${r.id}/settle`, { method: "POST", body: txId ? { transaction_id: txId } : {} });
      ok(r.direction === "they_owe" ? `${r.person.split(" ")[0]} is ticked off.` : `Marked as paid to ${r.person.split(" ")[0]}.`);
      window.Kitna.refresh();
    } catch (e) { err(e); }
  }

  async function notThem(r) {
    try { await api(`/api/friends/${r.id}/not-them`, { method: "POST" }); window.Kitna.refresh(); } catch (e) { err(e); }
  }

  async function remove(r) {
    if (!(await confirmBox("Remove this?", `${r.person} · ${inr(r.amount)}${r.note ? " · " + r.note : ""}`, true))) return;
    try { await api(`/api/friends/${r.id}`, { method: "DELETE" }); ok("Removed."); window.Kitna.refresh(); } catch (e) { err(e); }
  }

  async function pickPayment() {
    let page;
    try { page = await api("/api/transactions?page=1&size=30"); } catch (e) { err(e); return; }
    const items = (page.items || page.transactions || []).filter((t) => t.kind === "expense").slice(0, 20);
    if (!items.length) { err(new Error("No payments yet to split. Add the expense first.")); return; }
    let chosen = null;
    const list = el("div", { class: "tx-list", style: { maxHeight: "55vh", overflow: "auto" } }, items.map((t) =>
      el("div", { class: "tx tx-edit", role: "button", tabindex: "0", style: { cursor: "pointer" },
        onclick: () => { chosen = t; document.querySelector(".modal-bg .modal-foot .btn.primary").click(); } },
        avatar(t.note || t.category), el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, t.note || t.category),
          el("div", { class: "tx-sub" }, dateFmt(t.date) + " · " + t.category)),
        el("div", { class: "tx-amt" }, "-" + inr(t.amount)))));
    const v = await window.Kitna.modal("Which payment?", list, [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Next", submit: true, cls: "primary", value: () => chosen },
    ]);
    if (v) splitModal(v);
  }

  function row(r) {
    const they = r.direction === "they_owe";
    return el("div", { class: "tx-item owed-row" },
      el("div", { class: "tx" },
        avatar(r.person),
        el("div", { class: "tx-main" },
          el("div", { class: "tx-title wrap" }, r.person),
          el("div", { class: "tx-sub" }, [r.note, dateFmt(r.date)].filter(Boolean).join(" · "))),
        el("div", { class: "tx-amt" + (they ? " in" : "") }, (they ? "+" : "-") + inr0(r.amount))),
      r.settled ? null : el("div", { class: "item-actions" },
        they ? el("button", { class: "btn sm", onclick: () => remind(r) }, icon("share"), "Remind") : null,
        el("button", { class: "btn sm ghost", onclick: () => settle(r) }, they ? "They paid" : "I paid"),
        el("button", { class: "btn sm ghost", "aria-label": "Remove " + r.person, onclick: () => remove(r) }, icon("trash"), "Remove")));
  }

  function build(d) {
    const t = d.totals;
    const summary = el("div", { class: "grid g-2" },
      el("div", { class: "card" }, el("div", { class: "small muted" }, "Friends owe you"),
        el("div", { class: "big num green", style: { fontSize: "30px", marginTop: "4px" } }, inr0(t.they_owe)),
        el("div", { class: "tiny faint", style: { marginTop: "4px" } }, t.they_owe ? "Not counted in today's number until it arrives." : "Split a payment to start.")),
      el("div", { class: "card" }, el("div", { class: "small muted" }, "You owe friends"),
        el("div", { class: "big num", style: { fontSize: "30px", marginTop: "4px" } }, inr0(t.i_owe)),
        el("div", { class: "tiny faint", style: { marginTop: "4px" } }, t.i_owe ? "Already kept aside in today's number." : "Nothing to pay back.")));

    const actions = el("div", { class: "chip-row" },
      el("button", { class: "btn primary", onclick: pickPayment }, icon("split"), "Split a payment"),
      el("button", { class: "btn", onclick: () => friendModal("they_owe") }, icon("plus"), "Someone owes me"),
      el("button", { class: "btn ghost", onclick: () => friendModal("i_owe") }, "I owe someone"));

    const asks = d.suggestions.map((s) => el("div", { class: "notice info", style: { alignItems: "flex-start" } }, icon("info"),
      el("div", { style: { flex: 1 } },
        el("b", null, `Was the ${inr0(s.amount)} ${onDay(s.tx_date)} from ${s.person.split(" ")[0]}?`),
        el("div", { class: "small", style: { marginTop: "4px" } }, `Your bank didn't say who sent it${s.tx_note ? ` (“${s.tx_note}”)` : ""}.`),
        el("div", { class: "chip-row", style: { marginTop: "10px" } },
          el("button", { class: "btn sm", onclick: () => settle(s, s.suggested_tx_id) }, "Yes, tick it off"),
          el("button", { class: "btn sm ghost", onclick: () => notThem(s) }, "No")))));

    const open = el("section", null, el("div", { class: "section-title" }, el("span", null, "Still open")),
      el("div", { class: "card", style: { padding: "4px 20px" } }, d.open.length
        ? el("div", { class: "tx-list" }, d.open.map(row))
        : el("div", { class: "empty" }, el("b", null, "All square"), "Paid for dinner or a cab? Split it here, or from the payment in Activity.")));

    const upi = d.upi_id ? null : el("div", { class: "card row", style: { gap: "12px", alignItems: "center", flexWrap: "wrap" } },
      el("div", { style: { flex: 1, minWidth: "200px" } }, el("h3", null, "Add your UPI ID"),
        el("div", { class: "small muted" }, "Reminders you send will include it, so friends can pay in one go.")),
      el("a", { class: "btn sm", href: "/app/settings#upi" }, "Add"));

    const done = d.settled.length ? el("details", { class: "card" },
      el("summary", { style: { cursor: "pointer", fontWeight: 650 } }, `Paid back (${d.settled.length})`),
      el("div", { class: "tx-list", style: { marginTop: "8px", opacity: 0.75 } }, d.settled.map(row))) : null;

    return [summary, actions, ...asks, open, upi, done];
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
