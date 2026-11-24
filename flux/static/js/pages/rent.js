/* Kitna Rent (PG / hostel / flat owners): who paid, who's late, remind in one tap.
   Tenants pay the owner's own UPI ID; Kitna matches the owner's bank alerts to tenants (see flux/rent.py). */
(function () {
  const { el, icon, api, inr0, dateFmt, avatar, pageHead, onRefresh, ok, err, confirmBox, modal } = window.Kitna;
  const monthName = (ym) => new Date(ym + "-01T00:00:00").toLocaleDateString("en-IN", { month: "long" });
  const shortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const thisMonth = () => new Date().toISOString().slice(0, 7);

  async function render(main) {
    const content = el("div", { class: "stack narrow rent", style: { gap: "16px" } }, window.Kitna.skeleton(4));
    main.replaceChildren(content);
    const load = () => window.Kitna.live("/api/rent", (d) => content.replaceChildren(...(d.property ? build(d) : setup())));
    onRefresh(load);
    await load();
    if (new URLSearchParams(location.search).get("upgrade")) upgrade("menu");
  }

  // ─── First time: what this is, and three fields ──────────────
  function setup(existing) {
    const p = existing || {};
    const name = el("input", { class: "input", maxlength: "60", placeholder: "Sharma PG, Sector 14", value: p.name || "", required: true, "aria-label": "PG or flat name" });
    const upi = el("input", { class: "input", maxlength: "100", placeholder: "yourname@okaxis", value: p.upi_id || window.Kitna.user.upi_id || "", autocapitalize: "off", "aria-label": "Your UPI ID" });
    const day = el("input", { class: "input", type: "number", min: "1", max: "28", value: p.due_day || 5, "aria-label": "Rent due day" });
    const form = el("form", { class: "card stack", style: { gap: "12px" }, onsubmit: async (e) => {
      e.preventDefault();
      try {
        await api("/api/rent/property", { method: "PUT", body: { name: name.value, upi_id: upi.value, due_day: day.value } });
        window.Kitna.cacheClear();
        if (!existing) { window.Kitna.user.has_rent = true; location.reload(); return; }
        ok("Saved."); window.Kitna.refresh();
      } catch (ex) { err(ex); }
    } },
      el("label", { class: "field" }, el("span", null, "PG, hostel or flat name"), name),
      el("label", { class: "field" }, el("span", null, "Your UPI ID (tenants pay this)"), upi),
      el("label", { class: "field" }, el("span", null, "Rent is due on day"), day),
      el("button", { class: "btn primary lg block", type: "submit" }, existing ? "Save" : "Start collecting rent"));
    if (existing) return form;
    return [
      el("header", { class: "large-title" }, el("h1", null, "Collect rent")),
      el("div", { class: "card rent-pitch" },
        el("h2", null, "Know who paid, without checking your bank."),
        el("ul", { class: "how-list" },
          el("li", null, icon("check"), el("span", null, "Tenants pay your UPI ID like they do today. No gateway, no fee.")),
          el("li", null, icon("check"), el("span", null, "Kitna reads your bank alerts and ticks off whose rent arrived, even from a parent's account.")),
          el("li", null, icon("check"), el("span", null, "Who's late, by how many days. Remind them on WhatsApp in one tap.")),
          el("li", null, icon("check"), el("span", null, "Every tenant gets a link with their dues, your UPI QR and receipts.")))),
      form,
      el("p", { class: "tiny faint", style: { textAlign: "center" } }, "Free for up to 5 tenants. Pro is ₹299 a month for up to 100."),
    ];
  }

  // ─── Main screen ─────────────────────────────────────────────
  function build(d) {
    const p = d.property;
    const pct = d.expected ? Math.min(100, Math.round((d.collected / d.expected) * 100)) : 0;
    const head = el("header", { class: "large-title row", style: { alignItems: "flex-end", justifyContent: "space-between" } },
      el("div", null, el("div", { class: "lt-date" }, p.name), el("h1", null, "Rent")),
      el("button", { class: "icon-btn", type: "button", title: "Settings", "aria-label": "Rent settings", onclick: () => settings(p) }, icon("gear")));

    const summary = el("section", { class: "today rent-sum" },
      el("div", { class: "today-label" }, `${monthName(d.month)} collected`),
      el("div", { class: "today-num num" }, el("span", { class: "cur" }, "₹"), inr0(d.collected).replace("₹", "")),
      el("div", { class: "today-sub" }, `of ${inr0(d.expected)}` + (d.pending > 0 ? ` · ${inr0(d.pending)} still to collect` : " · all collected")),
      el("div", { class: "bar", style: { margin: "12px 0 10px" } }, el("div", { class: "fill", style: { width: pct + "%" } })),
      el("div", { class: "rent-pills" },
        d.counts.late ? pill("late", d.counts.late, "late") : null, d.counts.due ? pill("due", d.counts.due, "due") : null,
        d.counts.paid ? pill("paid", d.counts.paid, "paid") : null));

    const plan = d.plan;
    const banner = plan.limited && plan.tenants >= plan.free_tenants - 1
      ? el("button", { class: "notice info plan-banner", type: "button", onclick: () => upgrade(plan.at_limit ? "limit" : "banner") }, icon("spark"),
          el("div", { style: { flex: 1, textAlign: "left" } }, el("b", null, plan.at_limit ? "You've used all 5 free tenants" : "1 free tenant left"),
            el("div", { class: "small" }, "Kitna Rent Pro: up to 100 tenants for ₹299 a month.")), icon("chev"))
      : null;

    const auto = autoNotice();
    const unmatched = d.unmatched.length ? section(d.unmatched.length === 1 ? "Whose rent is this?" : `Whose rent is this? (${d.unmatched.length})`, null,
      el("div", { class: "card sort-card" }, d.unmatched.map(unmatchedRow))) : null;

    const groups = [["late", "Late"], ["due", "Due"], ["paid", "Paid"]].map(([k, label]) => {
      const list = d.tenants.filter((t) => t.status === "active" && t.money === k);
      return list.length ? section(`${label} · ${list.length}`, null, el("div", { class: "card list-card" }, el("div", { class: "tx-list" }, list.map(tenantRow)))) : null;
    });
    const left = d.tenants.filter((t) => t.status === "left");
    const leftBox = left.length ? section("Moved out, still owe", null, el("div", { class: "card list-card" }, el("div", { class: "tx-list" }, left.map(tenantRow)))) : null;
    const empty = d.tenants.length ? null : el("div", { class: "card empty" }, el("b", null, "Add your tenants"),
      "Name, room and rent. Add them one by one, or paste your whole list at once.");

    const actions = el("div", { class: "grid g-2 keep", style: { gap: "10px" } },
      el("button", { class: "btn primary lg", onclick: () => tenantForm(null, d) }, icon("plus"), "Add tenant"),
      el("button", { class: "btn lg", onclick: () => bulkAdd(d) }, icon("list"), "Paste a list"));

    return [head, summary, auto, banner, unmatched, ...groups, leftBox, empty, actions].filter(Boolean);
  }

  const section = (title, link, ...kids) => el("section", null, el("div", { class: "section-title" }, el("span", null, title), link || null), ...kids);
  const pill = (cls, n, label) => el("span", { class: "rent-pill " + cls }, el("b", null, String(n)), " " + label);

  function autoNotice() {
    const s = window.Kitna.config.features || {};
    const holder = el("div");
    api("/api/gmail").then((g) => {
      if (g.connected) return;
      return api("/api/ingest/token").catch(() => null).then((t) => {
        if (t && t.active) return;
        holder.replaceChildren(el("a", { class: "notice caution", href: "/app/settings#auto" }, icon("bolt"),
          el("div", { style: { flex: 1 } }, el("b", null, "Connect your bank alerts"),
            el("div", { class: "small" }, s.gmail ? "Connect Gmail (iPhone) or the Android app so rent is ticked off by itself." : "So rent is ticked off by itself.")), icon("chev")));
      });
    }).catch(() => {});
    return holder;
  }

  function unmatchedRow(u) {
    const row = el("div", { class: "sort-row" },
      el("div", { class: "sort-top" },
        el("div", { style: { minWidth: 0, flex: 1 } },
          el("div", { class: "tx-title" }, u.note || "Money in"),
          el("div", { class: "tx-sub" }, dateFmt(u.date), " · received")),
        el("div", { class: "tx-amt num in" }, "+" + inr0(u.amount))),
      el("div", { class: "sort-chips" },
        u.choices.map((c) => el("button", { class: "sort-chip" + (u.likely.includes(c.id) ? " on" : ""), type: "button", onclick: () => assign(u, c, row) },
          c.name.split(" ")[0] + (c.room ? " · " + c.room : ""))),
        el("button", { class: "sort-chip", type: "button", onclick: () => notRent(u, row) }, "Not rent")));
    return row;
  }

  async function assign(u, c, row) {
    row.classList.add("sorting");
    try {
      await api("/api/rent/assign", { method: "POST", body: { transaction_id: u.transaction_id, tenant_id: c.id } });
      ok(`${inr0(u.amount)} counted as ${c.name.split(" ")[0]}'s rent. Kitna will recognise this payer next time.`);
      window.Kitna.refresh();
    } catch (e) { row.classList.remove("sorting"); err(e); }
  }

  async function notRent(u, row) {
    row.classList.add("sorting");
    try { await api("/api/rent/assign", { method: "POST", body: { transaction_id: u.transaction_id, not_rent: true } }); window.Kitna.refresh(); } catch (e) { row.classList.remove("sorting"); err(e); }
  }

  function statusLine(t) {
    if (t.money === "paid") return t.advance > 0 ? `Paid · ${inr0(t.advance)} extra` : "Paid";
    if (t.money === "due") return `Due ${shortDate(t.due_on)}`;
    return `${t.late_days} day${t.late_days === 1 ? "" : "s"} late`;
  }

  function tenantRow(t) {
    return el("div", { class: "tx tx-edit", role: "button", tabindex: "0", onclick: () => tenantSheet(t.id),
      onkeydown: (e) => { if (e.key === "Enter") tenantSheet(t.id); } },
      avatar(t.name),
      el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, t.name),
        el("div", { class: "tx-sub" + (t.money === "late" ? " red" : "") }, [t.room && "Room " + t.room, statusLine(t)].filter(Boolean).join(" · "))),
      el("div", { class: "tx-amt num" + (t.money === "late" ? " red" : "") }, t.balance > 0 ? inr0(t.balance) : el("span", { class: "ok-tick" }, icon("check"))));
  }

  // ─── One tenant ──────────────────────────────────────────────
  async function tenantSheet(id) {
    let t;
    try { t = await api(`/api/rent/tenants/${id}`); } catch (e) { err(e); return; }
    const first = t.name.split(" ")[0];
    const remind = async () => {
      api(`/api/rent/reminded/${id}`, { method: "POST" }).catch(() => {});
      const url = t.wa_phone ? `https://wa.me/${t.wa_phone}?text=${encodeURIComponent(t.reminder)}` : `https://wa.me/?text=${encodeURIComponent(t.reminder)}`;
      window.open(url, "_blank", "noopener");
    };
    const copyLink = async () => {
      try { await navigator.clipboard.writeText(t.link); ok(`${first}'s link copied. Send it on WhatsApp.`); }
      catch (e) { window.prompt("Copy this link", t.link); }
    };
    const body = el("div", { class: "stack", style: { gap: "14px" } },
      el("div", { class: "tenant-head" },
        el("div", { class: "tiny faint" }, [t.room && "Room " + t.room, inr0(t.rent) + " a month"].filter(Boolean).join(" · ")),
        el("div", { class: "tenant-bal num" + (t.money === "late" ? " red" : "") }, t.balance > 0 ? inr0(t.balance) : "All paid"),
        el("div", { class: "small muted" }, t.balance > 0 ? statusLine(t) : t.advance > 0 ? `${inr0(t.advance)} paid in advance` : "Nothing due")),
      el("div", { class: "grid g-2 keep", style: { gap: "8px" } },
        el("button", { class: "btn primary", type: "button", disabled: t.balance <= 0 ? true : null, onclick: remind }, icon("share"), "Remind"),
        el("button", { class: "btn", type: "button", onclick: () => { close(); cashForm(t); } }, icon("check"), "Got cash")),
      el("button", { class: "btn ghost block", type: "button", onclick: copyLink }, icon("share"), `Copy ${first}'s link (dues, QR, receipts)`),
      t.months.length ? el("div", null, el("div", { class: "section-title" }, el("span", null, "Months")),
        el("div", { class: "month-rows" }, t.months.map((m) => el("div", { class: "month-row" },
          el("span", null, monthName(m.month)),
          el("span", { class: "rent-pill " + (m.status === "paid" ? "paid" : m.status === "part" ? "due" : "late") },
            m.status === "paid" ? "Paid" : m.status === "part" ? `${inr0(m.paid)} of ${inr0(m.rent)}` : "Not paid"))))) : null,
      t.payments.length ? el("div", null, el("div", { class: "section-title" }, el("span", null, "Payments")),
        el("div", { class: "tx-list" }, t.payments.map((x) => el("div", { class: "tx" },
          el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, inr0(x.amount)),
            el("div", { class: "tx-sub" }, dateFmt(x.date) + " · " + ({ upi: "UPI", cash: "Cash", bank: "Bank" }[x.method]) + (x.how === "auto" ? " · matched by Kitna" : ""))),
          el("button", { class: "icon-btn", type: "button", "aria-label": "Remove payment", title: "Remove", onclick: async () => {
            if (!(await confirmBox("Remove this payment?", `${inr0(x.amount)} on ${dateFmt(x.date)}. ${first} will owe it again.`, true))) return;
            try { await api(`/api/rent/payments/${x.id}`, { method: "DELETE" }); ok("Removed."); window.Kitna.refresh(); } catch (e) { err(e); }
          } }, icon("trash")))))) : null,
      el("div", { class: "row", style: { gap: "8px", flexWrap: "wrap" } },
        el("button", { class: "btn sm ghost", type: "button", onclick: () => { close(); tenantForm(t); } }, "Edit"),
        t.status === "active"
          ? el("button", { class: "btn sm ghost", type: "button", onclick: async () => {
              if (!(await confirmBox(`${first} moved out?`, `Rent stops after ${monthName(thisMonth())}. Anything still owed stays on the list.`))) return;
              try { await api(`/api/rent/tenants/${id}`, { method: "PATCH", body: { left: true } }); ok("Done."); window.Kitna.refresh(); } catch (e) { err(e); }
            } }, "Moved out")
          : el("button", { class: "btn sm ghost", type: "button", onclick: async () => {
              try { await api(`/api/rent/tenants/${id}`, { method: "PATCH", body: { left: false } }); window.Kitna.refresh(); } catch (e) { err(e); if (e.status === 402) upgrade("limit"); }
            } }, "Moved back in"),
        el("button", { class: "btn sm ghost danger-text", type: "button", style: { marginLeft: "auto" }, onclick: async () => {
          if (!(await confirmBox(`Delete ${t.name}?`, "Their payments and history are deleted too.", true))) return;
          try { await api(`/api/rent/tenants/${id}`, { method: "DELETE" }); ok("Deleted."); window.Kitna.refresh(); } catch (e) { err(e); }
        } }, "Delete")));
    const close = () => { const x = document.querySelector(".modal-bg"); if (x) x.querySelector(".modal-x").click(); };
    await modal(t.name, body);
  }

  async function cashForm(t) {
    const amount = el("input", { class: "input num", type: "number", inputmode: "decimal", min: "1", step: "0.01", value: t.balance > 0 ? t.balance : t.rent, required: true, "aria-label": "Amount" });
    const date = el("input", { class: "input", type: "date", value: window.Kitna.todayISO(), "aria-label": "Date" });
    let method = "cash";
    const seg = el("div", { class: "seg" }, [["cash", "Cash"], ["bank", "Bank / UPI"]].map(([k, label]) =>
      el("button", { type: "button", class: k === method ? "on" : "", onclick: (e) => { method = k === "bank" ? "bank" : "cash"; [...seg.children].forEach((b) => b.classList.remove("on")); e.currentTarget.classList.add("on"); } }, label)));
    const v = await modal(`${t.name.split(" ")[0]} paid`, el("div", { class: "stack", style: { gap: "12px" } },
      el("label", { class: "field" }, el("span", null, "Amount (₹)"), amount),
      el("label", { class: "field" }, el("span", null, "Date"), date), seg,
      el("p", { class: "tiny faint" }, "Only for money Kitna can't see, like cash. UPI to your account is matched by itself.")), [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ amount: amount.value, date: date.value, method }) },
    ]);
    if (!v) return;
    try { await api(`/api/rent/tenants/${t.id}/payments`, { method: "POST", body: v }); ok("Saved."); window.Kitna.refresh(); } catch (e) { err(e); }
  }

  async function tenantForm(t, d) {
    const f = (k, label, attrs) => { const i = el("input", Object.assign({ class: "input", value: t ? (t[k] ?? "") : "" }, attrs)); return [i, el("label", { class: "field" }, el("span", null, label), i)]; };
    const [name, nameF] = f("name", "Name", { maxlength: "60", required: true, autofocus: true });
    const [room, roomF] = f("room", "Room or bed (optional)", { maxlength: "20" });
    const [rentIn, rentF] = f("rent", "Monthly rent (₹)", { type: "number", min: "1", inputmode: "decimal", required: true });
    const [phone, phoneF] = f("phone", "WhatsApp number (optional)", { type: "tel", maxlength: "15", placeholder: "98765 43210" });
    const [payers, payersF] = f("payer_names", "Who else pays for them? (optional)", { maxlength: "120", placeholder: "e.g. father's name as on his bank account" });
    const [start, startF] = f("start_month", "Rent counts from", { type: "month", value: t ? t.start_month : thisMonth() });
    const [old, oldF] = f("opening_due", "Old dues before Kitna (₹, optional)", { type: "number", min: "0", inputmode: "decimal", value: t ? (t.opening_due || "") : "" });
    const v = await modal(t ? `Edit ${t.name}` : "Add tenant", el("div", { class: "stack", style: { gap: "10px" } },
      nameF, roomF, rentF, phoneF, payersF,
      el("details", { class: "auto-more" }, el("summary", null, "Start month and old dues"), el("div", { class: "stack", style: { gap: "10px", marginTop: "10px" } }, startF, oldF))), [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: t ? "Save" : "Add", submit: true, cls: "primary", value: () => ({ name: name.value, room: room.value, rent: rentIn.value, phone: phone.value,
        payer_names: payers.value, start_month: start.value || thisMonth(), opening_due: old.value || 0 }) },
    ]);
    if (!v) return;
    try {
      if (t) await api(`/api/rent/tenants/${t.id}`, { method: "PATCH", body: v });
      else await api("/api/rent/tenants", { method: "POST", body: v });
      ok(t ? "Saved." : `${v.name.split(" ")[0]} added.`);
      window.Kitna.refresh();
    } catch (e) { if (e.status === 402) upgrade("limit"); else err(e); }
  }

  async function bulkAdd() {
    const box = el("textarea", { class: "input", rows: "8", placeholder: "Rahul Verma, 101, 8500, 9876543210\nPriya Nair, 102, 7000\nAman Gupta, 103, 8000", "aria-label": "Tenant list" });
    const v = await modal("Paste your tenant list", el("div", { class: "stack", style: { gap: "10px" } },
      el("p", { class: "small muted" }, "One tenant per line: name, room, rent, phone. Copy it from your notebook, Excel or WhatsApp."), box), [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Add all", submit: true, cls: "primary", value: () => box.value },
    ]);
    if (!v) return;
    const tenants = [];
    for (const line of v.split(/\n+/).map((l) => l.trim()).filter(Boolean)) {
      const parts = line.split(/\s*[,\t|]\s*/);
      const rentPart = parts.findIndex((x, i) => i > 0 && /^₹?\s*[\d,]+(\.\d+)?$/.test(x) && Number(x.replace(/[₹,\s]/g, "")) >= 100);
      if (rentPart < 0) { err(new Error(`Couldn't find the rent in: "${line}"`)); return; }
      const rest = parts.filter((_, i) => i !== rentPart && i !== 0);
      const phone = rest.find((x) => /^\+?[\d\s-]{10,15}$/.test(x)) || "";
      const room = rest.find((x) => x !== phone) || "";
      tenants.push({ name: parts[0], rent: parts[rentPart].replace(/[₹,\s]/g, ""), room, phone, start_month: thisMonth() });
    }
    if (!tenants.length) return;
    try { const r = await api("/api/rent/tenants", { method: "POST", body: { tenants } }); ok(`${r.ids.length} tenants added.`); window.Kitna.refresh(); }
    catch (e) { if (e.status === 402) upgrade("limit"); else err(e); }
  }

  async function settings(p) {
    const form = setup(p);
    form.classList.remove("card");
    const foot = form.querySelector("button[type=submit]");
    foot.textContent = "Save";
    modal("Rent settings", form);
  }

  // ─── Kitna Rent Pro (Razorpay) ───────────────────────────────
  async function upgrade(from) {
    let b;
    try { b = await api("/api/billing"); } catch (e) { err(e); return; }
    const body = el("div", { class: "stack", style: { gap: "14px" } },
      el("ul", { class: "how-list" },
        el("li", null, icon("check"), el("span", null, "Up to 100 tenants (free covers 5)")),
        el("li", null, icon("check"), el("span", null, "Rent matched from your bank alerts, reminders, tenant links")),
        el("li", null, icon("check"), el("span", null, "Your tenants' payments never pass through Kitna: no fees on rent"))),
      b.pro ? el("div", { class: "notice info" }, icon("check"), el("div", null, el("b", null, "You're on Pro"), ` until ${dateFmt(b.until)}. Buying more adds to it.`)) : null);
    if (!b.enabled) {
      body.append(el("div", { class: "notice info" }, icon("info"), el("div", null, el("b", null, "Pro opens soon. "),
        "Until then, add as many tenants as you need by writing to us from You → Tell us something.")));
      await modal("Kitna Rent Pro", body);
      return;
    }
    const plans = el("div", { class: "grid g-2 keep", style: { gap: "10px" } }, b.plans.map((pl) =>
      el("button", { class: "plan-card" + (pl.months === 12 ? " best" : ""), type: "button", onclick: () => buy(pl.id, from) },
        el("div", { class: "tiny faint" }, pl.months === 12 ? "12 months · 2 months free" : "1 month"),
        el("div", { class: "plan-price num" }, inr0(pl.price)),
        el("div", { class: "tiny faint" }, pl.months === 12 ? "₹250 a month" : "No auto-renewal: it just ends"))));
    body.append(plans, el("p", { class: "tiny faint", style: { textAlign: "center" } },
      "Paid securely on Razorpay: UPI, cards or net banking. ", el("a", { href: "/refunds", class: "link" }, "Refunds")));
    await modal("Kitna Rent Pro", body);
  }

  function loadCheckout() {
    if (window.Razorpay) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://checkout.razorpay.com/v1/checkout.js";
      s.onload = resolve; s.onerror = () => reject(new Error("Couldn't open the payment screen. Check your connection."));
      document.head.appendChild(s);
    });
  }

  async function buy(plan, from) {
    try {
      const [o] = await Promise.all([api("/api/billing/order", { method: "POST", body: { plan, from } }), loadCheckout()]);
      const x = document.querySelector(".modal-bg .modal-x");
      if (x) x.click();
      const rzp = new window.Razorpay({
        key: o.key, order_id: o.order_id, amount: o.amount, currency: o.currency, name: o.name, description: o.description,
        prefill: { email: o.email, name: o.user_name }, theme: { color: "#4F46E5" },
        handler: async (resp) => {
          try {
            const v = await api("/api/billing/verify", { method: "POST", body: resp });
            ok(`You're on Kitna Rent Pro until ${dateFmt(v.until)}. Thank you!`);
            window.Kitna.cacheClear(); window.Kitna.refresh();
          } catch (e) { err(e); }
        },
      });
      rzp.on("payment.failed", (r) => err(new Error((r && r.error && r.error.description) || "The payment didn't go through. No money was taken.")));
      rzp.open();
    } catch (e) { err(e); }
  }

  window.Kitna.rentUpgrade = upgrade;
  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
