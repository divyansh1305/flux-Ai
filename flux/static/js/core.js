/* Flux core: safe DOM helpers, API client, app shell, toasts, modals.
   Rule: user data is ALWAYS inserted with textContent (via el()), never innerHTML. */
(function () {
  "use strict";

  // ─── Safe element builder ─────────────────────────────────
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (k === "html") throw new Error("el(): raw HTML is not allowed");
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  // Static, trusted SVG icons (no user data ever goes in here).
  const ICONS = {
    home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    pie: '<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    upload: '<path d="M12 16V4M6 10l6-6 6 6M4 20h16"/>',
    spark: '<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/>',
    out: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l-5-5 5-5M5 12h11"/>',
    download: '<path d="M12 4v12M6 10l6 6 6-6M4 20h16"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    send: '<path d="M4 12l16-8-6 16-2-7z"/>',
    qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/>',
    trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    msg: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="4"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    check: '<path d="M5 12l5 5 9-11"/>',
    bank: '<path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
    alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 12V10a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/><path d="M21 12v2a4 4 0 0 1-4 4H3"/>',
    chat: '<path d="M4 5h16v11H8l-4 4z"/>',
    zap: '<path d="M13 3L5 13h6l-1 8 8-10h-6z"/>',
    file: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
    wave: '<path d="M7 12V7a2 2 0 0 1 4 0v4M11 11V5a2 2 0 0 1 4 0v6M15 11V7a2 2 0 0 1 4 0v6a7 7 0 0 1-7 7h-1a7 7 0 0 1-6-3.5L3 13a2 2 0 0 1 3.4-2L7 12"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  };
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = ICONS[name] || ""; // constant strings only
    return svg;
  }

  // ─── Formatting ───────────────────────────────────────────
  const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
  const inr = (v) => (v < 0 ? "-₹" : "₹") + inrFmt.format(Math.abs(Number(v) || 0));
  const inr0 = (v) => (v < 0 ? "-₹" : "₹") + new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.abs(Number(v) || 0));
  const dateFmt = (iso) => {
    const d = new Date(iso + "T00:00:00");
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((today - d) / 86400000);
    if (diff === 0) return "Today";
    if (diff === 1) return "Yesterday";
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
  };
  const todayISO = () => {
    const d = new Date();
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  };
  const CAT_EMOJI = {}; // kept for compatibility; the UI uses initials + icons instead of emoji
  function tintFor(key) {
    let h = 0;
    for (const ch of String(key || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return "tint-" + (h % 6);
  }
  // GPay-style avatar: first letter of the merchant/person, same soft colour every time.
  function avatar(name, ic) {
    const m = String(name || "").match(/[A-Za-z0-9\u0900-\u097F]/);
    return el("div", { class: "tx-icon " + tintFor(name), "aria-hidden": "true" }, ic ? icon(ic) : (m ? m[0].toUpperCase() : "•"));
  }
  const CAT_COLORS = ["#2f7d67", "#d0913a", "#4f7cc4", "#b9638a", "#7a6ec9", "#8f9d45", "#a39d92", "#c8c2b6"];

  // ─── API client ───────────────────────────────────────────
  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)flux_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
    if (init.method !== "GET") init.headers["X-CSRF-Token"] = csrf();
    if (opts.body instanceof FormData) init.body = opts.body;
    else if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      throw new Error("You seem to be offline. Check your connection.");
    }
    if (res.status === 401 && !opts.allow401) {
      location.href = "/login";
      throw new Error("Please sign in.");
    }
    const type = res.headers.get("Content-Type") || "";
    const data = type.includes("application/json") ? await res.json() : await res.blob();
    if (!res.ok) throw new Error((data && data.error) || "Something went wrong.");
    return data;
  }
  async function download(path, filename) {
    const blob = await api(path);
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  // ─── Toasts & modals ──────────────────────────────────────
  function toast(message, kind = "", action) {
    let box = document.querySelector(".toasts");
    if (!box) { box = el("div", { class: "toasts", role: "status", "aria-live": "polite" }); document.body.appendChild(box); }
    const t = el("div", { class: "toast " + kind }, el("div", { class: "t-body" }, message));
    if (action) t.appendChild(el("button", { onclick: () => { action.run(); t.remove(); } }, action.label));
    box.appendChild(t);
    setTimeout(() => t.remove(), action ? 7000 : 4000);
  }
  const ok = (m, a) => toast(m, "ok", a);
  const err = (e) => toast(e && e.message ? e.message : String(e), "err");

  function modal(title, body, buttons) {
    return new Promise((resolve) => {
      const close = (v) => { bg.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
      const onKey = (e) => { if (e.key === "Escape") close(null); };
      const foot = el("div", { class: "modal-foot" });
      (buttons || [{ label: "Close", value: null }]).forEach((b) =>
        foot.appendChild(el("button", { class: "btn " + (b.cls || ""), type: b.submit ? "submit" : "button",
          onclick: b.submit ? null : () => close(b.value) }, b.label)));
      const form = el("form", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title,
        onsubmit: (e) => { e.preventDefault(); const b = (buttons || []).find((x) => x.submit); if (b) close(b.value()); } },
        el("h2", null, title), body, foot);
      const bg = el("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) close(null); } }, form);
      document.body.appendChild(bg);
      document.addEventListener("keydown", onKey);
      const first = form.querySelector("input, select, textarea, button");
      if (first) setTimeout(() => first.focus(), 30);
    });
  }
  const confirmBox = (title, text, danger) =>
    modal(title, el("p", { class: "muted" }, text), [
      { label: "Cancel", value: false, cls: "ghost" },
      { label: danger ? "Delete" : "Confirm", value: true, cls: danger ? "danger" : "primary" },
    ]);

  // ─── Shared "add transaction" modal (used by many pages) ──
  let META = null;
  const BUILD = ((document.currentScript && document.currentScript.src) || "").split("v=")[1] || "dev";
  async function meta() {
    if (META) return META;
    try { const c = JSON.parse(sessionStorage.getItem("flux_meta") || "null"); if (c && c.build === BUILD) return (META = c.data); } catch (e) { /* storage blocked */ }
    META = await api("/api/meta");
    try { sessionStorage.setItem("flux_meta", JSON.stringify({ build: BUILD, data: META })); } catch (e) { /* ignore */ }
    return META;
  }
  async function addTransactionModal(kind = "expense") {
    const m = await meta();
    let current = kind;
    const amount = el("input", { class: "input big num", type: "number", inputmode: "decimal", min: "0.01", step: "0.01", placeholder: "0", required: true, "aria-label": "Amount in rupees" });
    const cat = el("select", { class: "input", "aria-label": "Category" });
    const note = el("input", { class: "input", maxlength: "140", placeholder: "e.g. Lunch with friends" });
    const day = el("input", { class: "input", type: "date", value: todayISO(), max: todayISO() });
    const check = el("div");
    const fill = () => {
      cat.replaceChildren(...(current === "expense" ? m.expense_categories : m.income_categories).map((c) => el("option", { value: c }, c)));
    };
    const seg = el("div", { class: "seg" });
    const bE = el("button", { type: "button", class: "on exp" }, "Expense");
    const bI = el("button", { type: "button" }, "Income");
    bE.onclick = () => { current = "expense"; bE.className = "on exp"; bI.className = ""; fill(); runCheck(); };
    bI.onclick = () => { current = "income"; bI.className = "on inc"; bE.className = ""; fill(); check.replaceChildren(); };
    seg.append(bE, bI);
    if (kind === "income") bI.onclick();
    fill();
    let timer;
    const runCheck = () => {
      clearTimeout(timer);
      if (current !== "expense" || !(Number(amount.value) > 0)) { check.replaceChildren(); return; }
      timer = setTimeout(async () => {
        try {
          const r = await api("/api/transactions/check", { method: "POST", body: { amount: amount.value, category: cat.value } });
          const lines = r.warnings.length ? r.warnings : ["Looks fine. Balance after: " + inr(r.balance_after) + "."];
          if (r.goal_delay_days) lines.push(`Pushes your goals back ~${r.goal_delay_days} day(s).`);
          if (r.autosave_would_add > 0) lines.push(`${inr(r.autosave_would_add)} will be set aside for your goal (it stays in your bank).`);
          check.replaceChildren(el("div", { class: "notice " + r.level }, el("div", null, ...lines.map((l) => el("div", null, l)))));
        } catch (e) { /* ignore preview errors */ }
      }, 300);
    };
    amount.addEventListener("input", runCheck);
    cat.addEventListener("change", runCheck);

    const body = el("div", { class: "form" }, seg,
      el("label", { class: "field" }, "Amount (₹)", amount),
      el("label", { class: "field" }, "Category", cat), check,
      el("div", { class: "grid g-2" }, el("label", { class: "field" }, "Note (optional)", note), el("label", { class: "field" }, "Date", day)));
    const v = await modal("Add transaction", body, [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ kind: current, amount: amount.value, category: cat.value, note: note.value, date: day.value }) },
    ]);
    if (!v) return null;
    try {
      const r = await api("/api/transactions", { method: "POST", body: v });
      let msg = `Saved ${inr(r.transaction.amount)} ${r.transaction.kind}.`;
      if (r.autosaved) msg += ` ${inr(r.autosaved)} set aside for ${r.autosave_goal}.`;
      ok(msg, { label: "Undo", run: async () => { await api(`/api/transactions/${r.transaction.id}`, { method: "DELETE" }); refresh(); } });
      refresh();
      return r;
    } catch (e) { err(e); return null; }
  }

  // ─── Shared "plan" modal: money you expect to spend or receive ──
  async function planModal(existing) {
    const p = existing || { kind: "spend", title: "", amount: "", date: "", sure: true };
    let kind = p.kind;
    const title = el("input", { class: "input", maxlength: "60", placeholder: "Dinner on Friday", value: p.title, required: true });
    const amount = el("input", { class: "input big num", type: "number", inputmode: "decimal", min: "1", step: "1", placeholder: "2000", value: p.amount || "", required: true, "aria-label": "Amount in rupees" });
    const maxDay = new Date(); maxDay.setFullYear(maxDay.getFullYear() + 1);
    const day = el("input", { class: "input", type: "date", min: todayISO(), max: maxDay.toISOString().slice(0, 10), value: p.date || todayISO(), required: true });
    const sure = el("input", { type: "checkbox", checked: p.sure ? true : null });
    const sureRow = el("label", { class: "row", style: { gap: "8px", alignItems: "center" } }, sure, el("span", null, "I'm sure this money will come"));
    const hint = el("p", { class: "tiny faint" });
    const seg = el("div", { class: "seg" });
    const bS = el("button", { type: "button" }, "Money going out");
    const bI = el("button", { type: "button" }, "Money coming in");
    const paint = () => {
      bS.className = kind === "spend" ? "on exp" : ""; bI.className = kind === "income" ? "on inc" : "";
      sureRow.style.display = kind === "income" ? "" : "none";
      title.placeholder = kind === "income" ? "Client payment, pocket money" : "Dinner on Friday";
      hint.textContent = kind === "income"
        ? "Sure money counts in today's number. If you're not sure, Flux shows it separately and never counts on it."
        : "Flux keeps this aside until the day, so today's number is real. It's not a payment: nothing leaves your bank.";
    };
    bS.onclick = () => { kind = "spend"; paint(); };
    bI.onclick = () => { kind = "income"; paint(); };
    seg.append(bS, bI);
    paint();
    const body = el("div", { class: "form" }, seg, el("label", { class: "field" }, "What for", title),
      el("div", { class: "grid g-2" }, el("label", { class: "field" }, "Amount (₹)", amount), el("label", { class: "field" }, "When", day)),
      sureRow, hint);
    const v = await modal(existing ? "Edit plan" : "Add a plan", body, [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ kind, title: title.value, amount: amount.value, date: day.value, sure: kind === "income" ? sure.checked : true }) },
    ]);
    if (!v) return null;
    try {
      const r = existing ? await api(`/api/plans/${existing.id}`, { method: "PATCH", body: v }) : await api("/api/plans", { method: "POST", body: v });
      ok(existing ? "Plan updated." : "Plan added. Today's number now keeps it aside.");
      refresh();
      return r;
    } catch (e) { err(e); return null; }
  }

  // ─── Shell ────────────────────────────────────────────────
  const NAV = [
    ["/app", "home", "Home"],
    ["/app/transactions", "list", "Activity"],
    ["/app/budgets", "pie", "Budgets"],
    ["/app/goals", "target", "Goals"],
    ["/app/plans", "calendar", "Plans"],
    ["/app/coach", "spark", "Coach"],
  ];
  // Centre button: quick "Add" (always works).
  const MOBILE_NAV = [["/app", "home", "Home"], ["/app/transactions", "list", "Activity"], ["#add", "plus", "Add"],
    ["/app/plans", "calendar", "Plans"], ["/app/coach", "spark", "Ask"]];
  const featureOn = () => true;
  let USER = null;
  let CONFIG = {};

  function refresh() { document.dispatchEvent(new CustomEvent("flux:refresh")); }
  function onRefresh(fn) { document.addEventListener("flux:refresh", fn); }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST", allow401: true }); } catch (e) { /* ignore */ }
    location.href = "/login";
  }

  // Ask "who am I?" as soon as this file loads, not after the page is parsed: one less wait on slow networks.
  const mePromise = location.pathname.startsWith("/app") || location.pathname === "/onboarding"
    ? api("/api/auth/me", { allow401: true }).catch((e) => ({ error: e })) : null;

  async function boot(renderPage) {
    const me = (mePromise && await mePromise) || await api("/api/auth/me", { allow401: true });
    if (me.error) throw me.error;
    if (!me.user) { location.href = "/login"; return; }
    USER = me.user;
    CONFIG = me;
    if (!USER.onboarded && location.pathname !== "/onboarding") { location.href = "/onboarding"; return; }
    const path = location.pathname.replace(/\/$/, "") || "/app";
    const main = el("main", { class: "main", id: "main" });
    if (location.pathname !== "/onboarding") {
      const initials = USER.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
      const nav = el("nav", { class: "nav", "aria-label": "Main" }, NAV.filter(([href]) => featureOn(href)).map(([href, ic, label]) =>
        el("a", { href, class: path === href ? "active" : null, "aria-current": path === href ? "page" : null }, icon(ic), el("span", null, label))));
      const top = el("header", { class: "topbar" }, el("div", { class: "topbar-in" },
        el("a", { href: "/app", class: "logo" }, el("span", { class: "logo-mark" }, "F"), "Flux"),
        nav,
        el("div", { class: "top-actions" },
          el("a", { href: "/app/import", class: "icon-link" + (path === "/app/import" ? " active" : ""), title: "Import statement or SMS", "aria-label": "Import" }, icon("upload")),
          el("a", { href: "/app/settings", class: "icon-link" + (path === "/app/settings" ? " active" : ""), title: "Settings", "aria-label": "Settings" }, icon("gear")),
          el("a", { href: "/app/settings", class: "avatar", title: USER.name, "aria-label": "Account" }, initials))));
      const bottom = el("nav", { class: "bottom-nav", "aria-label": "Main" }, MOBILE_NAV.map(([href, ic, label]) =>
        href === "#add"
          ? el("a", { href: "#", class: "pay", onclick: (e) => { e.preventDefault(); addTransactionModal("expense"); } }, el("span", { class: "pay-dot" }, icon(ic)), label)
          : el("a", { href, class: path === href ? "active" : null }, icon(ic), label)));
      document.body.append(top, main, bottom);
    } else {
      document.body.append(main);
    }
    try {
      await renderPage(main, USER);
    } catch (e) { err(e); }
    if (window.FluxVoice && location.pathname !== "/onboarding") window.FluxVoice.init(USER);
  }

  function pageHead(title, subtitle, ...actions) {
    return el("div", { class: "page-head" },
      el("div", null, el("h1", null, title), subtitle ? el("p", { class: "muted" }, subtitle) : null),
      actions.length ? el("div", { class: "actions" }, ...actions) : null);
  }

  function txRow(t, onDelete) {
    const isIn = t.kind === "income";
    const isSave = t.kind === "saving";
    const title = t.note || t.category;
    const sign = isIn ? "+" : isSave ? (t.amount < 0 ? "+" : "→ ") : "-";
    const amtCls = isIn ? "green" : isSave ? "brand" : "";
    // Only show a tag when it means something to the user (not where the data came from).
    const badge = t.source === "autosave" ? el("span", { class: "badge autosave" }, "set aside") : null;
    const editable = t.kind === "income" || t.kind === "expense";
    return el("div", { class: "tx" },
      avatar(title, isSave ? "target" : null),
      el("div", editable ? { class: "tx-main tx-edit", role: "button", tabindex: "0", title: "Change category or note",
        onclick: () => editTx(t), onkeydown: (e) => { if (e.key === "Enter") editTx(t); } } : { class: "tx-main" },
        el("div", { class: "tx-title" }, title),
        el("div", { class: "tx-sub" }, dateFmt(t.date), " · ", t.category, " ", badge)),
      el("div", { class: "tx-amt " + amtCls }, sign + inr(Math.abs(t.amount))),
      onDelete && t.source !== "autosave" ? el("button", { class: "icon-btn", title: "Delete", "aria-label": "Delete transaction", onclick: () => onDelete(t) }, icon("trash")) : null);
  }

  async function editTx(t) {
    const m = await meta();
    const cats = t.kind === "income" ? m.income_categories : m.expense_categories;
    const cat = el("select", { class: "input" }, cats.map((c) => el("option", { value: c, selected: c === t.category }, c)));
    const note = el("input", { class: "input", value: t.note || "", maxlength: "140" });
    const remember = el("input", { type: "checkbox", checked: t.source !== "manual" });
    const who = () => (note.value || "").split("·")[0].trim() || "this merchant";
    const rememberText = el("span", null, `Always use this category for ${who()}`);
    note.addEventListener("input", () => { rememberText.textContent = `Always use this category for ${who()}`; });
    const hint = t.auto_category && t.auto_category !== t.category ? el("p", { class: "tiny faint" }, `Flux first filed this under ${t.auto_category}.`) : null;
    const body = el("div", { class: "form" },
      el("p", { class: "muted small", style: { margin: 0 } }, `${inr(Math.abs(t.amount))} · ${dateFmt(t.date)}`),
      el("label", { class: "field" }, "Category", cat),
      el("label", { class: "field" }, "Note / merchant", note),
      el("label", { class: "row", style: { gap: "8px", alignItems: "center" } }, remember, rememberText), hint);
    const v = await modal("Edit transaction", body, [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ category: cat.value, note: note.value, remember: remember.checked }) },
    ]);
    if (!v) return;
    try {
      const r = await api(`/api/transactions/${t.id}`, { method: "PATCH", body: v });
      ok(r.refiled ? `Saved. Also re-filed ${r.refiled} earlier payment${r.refiled > 1 ? "s" : ""} to ${v.category}.` : "Saved.");
      refresh();
    } catch (e) { err(e); }
  }

  async function deleteTx(t) {
    if (!(await confirmBox("Delete transaction?", `${t.note || t.category} · ${inr(t.amount)}. Anything set aside from it is removed too.`, true))) return;
    try { await api(`/api/transactions/${t.id}`, { method: "DELETE" }); ok("Deleted."); refresh(); } catch (e) { err(e); }
  }

  window.Flux = {
    el, icon, api, download, toast, ok, err, modal, confirmBox, inr, inr0, dateFmt, todayISO, CAT_EMOJI, CAT_COLORS, avatar,
    boot, pageHead, txRow, deleteTx, editTx, addTransactionModal, planModal, refresh, onRefresh, logout, meta,
    get user() { return USER; }, set user(u) { USER = u; }, get config() { return CONFIG; },
  };
})();
