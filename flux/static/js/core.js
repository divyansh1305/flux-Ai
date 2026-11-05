/* Kitna core: safe DOM helpers, API client, app shell, toasts, modals.
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
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
    split: '<path d="M12 3v7M12 10l-6 6v5M12 10l6 6v5"/>',
    share: '<path d="M12 3v12M7 8l5-5 5 5"/><path d="M5 13v7h14v-7"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    chev: '<path d="M9 6l6 6-6 6"/>',
    sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  };
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = ICONS[name] || ""; // constant strings only
    return svg;
  }

  // The Kitna wordmark (the logo). Constant markup only; it takes the text colour, the coin stays marigold.
  const WORDMARK = '<g fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"><path d="M10 20V100M10 74L46 50M26 63L48 100"/><path d="M70 50V100"/><path d="M102 28V86Q102 100 116 100M92 54H118"/><path d="M142 100V50M142 72A20 20 0 0 1 182 72V100"/><circle cx="229" cy="75" r="25"/><path d="M254 50V100"/></g><circle cx="70" cy="28" r="9" fill="#f2a93b"/>';
  function wordmark() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "2 12 260 96");
    svg.setAttribute("class", "logo-wm");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Kitna");
    svg.innerHTML = WORDMARK; // constant string only
    return svg;
  }

  // ─── Formatting ───────────────────────────────────────────
  const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
  const inr = (v) => (v < 0 ? "−₹" : "₹") + inrFmt.format(Math.abs(Number(v) || 0));
  const inr0 = (v) => (v < 0 ? "−₹" : "₹") + new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.abs(Number(v) || 0));
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
  const CAT_COLORS = ["#17171a", "#4b4a4e", "#737176", "#9a989c", "#bcbabd", "#d6d4d6", "#e6e4e5", "#efeeee"];  // one ink, in steps

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
    const data = opts.raw && res.ok ? await res.blob() : type.includes("application/json") ? await res.json() : await res.blob();
    if (!res.ok) throw new Error((data && data.error) || "Something went wrong.");
    if (init.method !== "GET" && path.startsWith("/api/account")) cacheDrop("/api/auth/me");  // settings changed
    return data;
  }

  // ─── Instant screens: show the last numbers this phone saw, then swap in fresh ones ──
  // Kept in this browser only, cleared on sign-out and on the sign-in page.
  const CK = "fluxc:";
  function cacheGet(path) { try { const v = localStorage.getItem(CK + path); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
  function cacheSet(path, data) { try { localStorage.setItem(CK + path, JSON.stringify(data)); } catch (e) { /* full or blocked */ } }
  function cacheDrop(path) { try { localStorage.removeItem(CK + path); } catch (e) { /* ignore */ } }
  function cacheClear() { try { Object.keys(localStorage).filter((k) => k.startsWith(CK)).forEach((k) => localStorage.removeItem(k)); } catch (e) { /* ignore */ } }
  /* live(path, onData[, early]): calls onData(cached) at once if this phone has it, then onData(fresh) when the
     server answers (only if something changed). `early` = a request already started for the same path. */
  async function live(path, onData, early) {
    const cached = cacheGet(path);
    if (cached) { try { onData(cached, true); } catch (e) { cacheDrop(path); } }
    let fresh = early ? await early : null;
    if (!fresh || fresh.error) fresh = await api(path);
    cacheSet(path, fresh);
    if (!cached || JSON.stringify(cached) !== JSON.stringify(fresh)) onData(fresh, false);
    return fresh;
  }
  // Fill the saved copies for other screens while the phone is idle, so their first open is instant too.
  function prefetch(paths) {
    const run = () => paths.reduce((p, path) => p.then(() => api(path).then((d) => cacheSet(path, d)).catch(() => {})), Promise.resolve());
    if ("requestIdleCallback" in window) requestIdleCallback(run, { timeout: 3000 }); else setTimeout(run, 800);
  }
  async function download(path, filename) {
    const blob = await api(path, { raw: true });  // a file even when the server sends JSON (the data export)
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
  const err = (e) => {
    toast(e && e.message ? e.message : String(e), "err", USER ? { label: "Tell us", run: () => feedbackModal("broken") } : undefined);
    track("error_shown");
  };

  // Usage counting: which screen was opened, and that an error was shown. Never amounts, merchants or text.
  const SCREENS = { "/app": "home", "/app/transactions": "activity", "/app/plans": "plans", "/app/coach": "ask",
    "/app/goals": "goals", "/app/budgets": "budgets", "/app/settings": "settings", "/app/import": "import",
    "/app/share": "share", "/app/privacy-center": "privacy-center", "/onboarding": "onboarding", "/app/admin": "admin",
    "/app/friends": "friends", "/app/pay": "pay" };
  function track(name, value) {
    if (!USER) return;
    const prop = value || SCREENS[location.pathname.replace(/\/$/, "") || "/app"] || "other";
    api("/api/events", { method: "POST", body: { name, prop } }).catch(() => {});
  }

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
    const pre = cacheGet("/api/meta");  // filled by prefetch from Home
    if (pre && pre.expense_categories) return (META = pre);
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
      if (r.paid_back) msg += r.paid_back.direction === "they_owe" ? ` ${r.paid_back.person.split(" ")[0]} is ticked off your Friends list.` : ` Your debt to ${r.paid_back.person.split(" ")[0]} is settled.`;
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
        ? "Sure money counts in today's number. If you're not sure, Kitna shows it separately and never counts on it."
        : "Kitna keeps this aside until the day, so today's number is real. It's not a payment: nothing leaves your bank.";
    };
    bS.onclick = () => { kind = "spend"; paint(); };
    bI.onclick = () => { kind = "income"; paint(); };
    seg.append(bS, bI);
    paint();
    const body = el("div", { class: "form" }, seg, el("label", { class: "field" }, "What for", title),
      el("div", { class: "grid g-2" }, el("label", { class: "field" }, "Amount (₹)", amount), el("label", { class: "field" }, "When", day)),
      sureRow, hint);
    const v = await modal(existing ? "Edit plan" : "Add a plan", body, [
      existing ? { label: "Delete", value: "delete", cls: "ghost danger-text" } : { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ kind, title: title.value, amount: amount.value, date: day.value, sure: kind === "income" ? sure.checked : true }) },
    ]);
    if (!v) return null;
    if (v === "delete") {
      if (!(await confirmBox("Delete plan?", `${existing.title} · ${inr0(existing.amount)}`, true))) return null;
      try { await api(`/api/plans/${existing.id}`, { method: "DELETE" }); ok("Plan deleted."); refresh(); } catch (e) { err(e); }
      return null;
    }
    try {
      const r = existing ? await api(`/api/plans/${existing.id}`, { method: "PATCH", body: v }) : await api("/api/plans", { method: "POST", body: v });
      ok(existing ? "Plan updated." : "Plan added. Today's number now keeps it aside.");
      refresh();
      return r;
    } catch (e) { err(e); return null; }
  }

  // ─── Shell ────────────────────────────────────────────────
  // Four things people do every day are tabs; everything else lives in one "More" menu.
  const NAV = [
    ["/app", "home", "Home"],
    ["/app/transactions", "list", "Activity"],
    ["/app/pay", "qr", "Pay"],
    ["/app/friends", "users", "Friends"],
    ["/app/plans", "calendar", "Plans"],
  ];
  const MOBILE_NAV = [["/app", "home", "Home"], ["/app/transactions", "list", "Activity"], ["/app/pay", "qr", "Pay"],
    ["/app/friends", "users", "Friends"], ["#more", "menu", "More"]];
  const MENU = [
    ["/app/plans", "calendar", "Plans", "Money kept aside for what's coming"],
    ["/app/budgets", "pie", "Budgets", "Monthly limits"],
    ["/app/goals", "target", "Goals", "Saving for something"],
    ["/app/coach", "chat", "Ask Kitna", "Questions about your money"],
    ["/app/import", "upload", "Import a statement", "Bank PDF or CSV"],
    ["/app/settings", "gear", "Settings", "Account, reminders, language"],
  ];
  function moreMenu() {
    const items = MENU.concat((CONFIG.features || {}).admin ? [["/app/admin", "trend", "Kitna numbers", "Only you can see this"]] : []);
    const close = () => { bg.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    const initials = USER.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    const sheet = el("div", { class: "modal sheet", role: "dialog", "aria-modal": "true", "aria-label": "More" },
      el("div", { class: "sheet-me" }, el("span", { class: "avatar" }, initials),
        el("div", { style: { minWidth: 0 } }, el("b", null, USER.name), el("div", { class: "tiny faint", style: { overflow: "hidden", textOverflow: "ellipsis" } }, USER.email || ""))),
      el("div", { class: "menu-list" }, items.map(([href, ic, label, sub]) =>
        el("a", { href, class: "menu-item" }, el("span", { class: "menu-ic" }, icon(ic)),
          el("span", { class: "menu-text" }, el("b", null, label), el("span", null, sub)), icon("chev")))),
      el("button", { class: "menu-item plain", type: "button", onclick: () => { close(); feedbackModal(); } },
        el("span", { class: "menu-ic" }, icon("chat")), el("span", { class: "menu-text" }, el("b", null, "Tell us something"), el("span", null, "A bug, an idea, anything"))),
      el("button", { class: "btn ghost block", type: "button", onclick: close }, "Close"));
    const bg = el("div", { class: "modal-bg sheet-bg", onclick: (e) => { if (e.target === bg) close(); } }, sheet);
    document.body.appendChild(bg);
    document.addEventListener("keydown", onKey);
  }
  const featureOn = () => true;
  let USER = null;
  let CONFIG = {};

  function refresh() { document.dispatchEvent(new CustomEvent("flux:refresh")); }
  function onRefresh(fn) { document.addEventListener("flux:refresh", fn); }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST", allow401: true }); } catch (e) { /* ignore */ }
    cacheClear();
    location.href = "/login";
  }

  // Ask "who am I?" as soon as this file loads, not after the page is parsed: one less wait on slow networks.
  const mePromise = location.pathname.startsWith("/app") || location.pathname === "/onboarding"
    ? api("/api/auth/me", { allow401: true }).catch((e) => ({ error: e })) : null;

  async function boot(renderPage) {
    const cachedMe = cacheGet("/api/auth/me");
    let me;
    if (cachedMe && cachedMe.user) {
      me = cachedMe;  // draw now; check with the server in the background
      (mePromise || api("/api/auth/me", { allow401: true })).then((fresh) => {
        if (!fresh || fresh.error) return;
        if (!fresh.user) { cacheClear(); location.href = "/login"; return; }
        cacheSet("/api/auth/me", fresh);
        if (fresh.user.id !== cachedMe.user.id || fresh.user.onboarded !== cachedMe.user.onboarded || fresh.user.lang !== cachedMe.user.lang) { location.reload(); return; }
        USER = fresh.user; CONFIG = fresh;
      });
    } else {
      me = (mePromise && await mePromise) || await api("/api/auth/me", { allow401: true });
      if (me.error) throw me.error;
      if (!me.user) { cacheClear(); location.href = "/login"; return; }
      cacheSet("/api/auth/me", me);
    }
    if ("serviceWorker" in navigator && (location.protocol === "https:" || ["localhost", "127.0.0.1"].includes(location.hostname))) {
      try { navigator.serviceWorker.register("/sw.js").catch(() => {}); } catch (e) { /* not supported */ }
    }
    USER = me.user;
    CONFIG = me;
    if (!USER.onboarded && location.pathname !== "/onboarding") { location.href = "/onboarding"; return; }
    if (window.FluxI18n) window.FluxI18n.start(USER.lang);
    const qs = new URLSearchParams(location.search);
    if (qs.get("from") === "push") {  // opened from a reminder: count it (which kind only), then tidy the address
      track("push_opened", qs.get("k") || "");
      qs.delete("from"); qs.delete("k");
      history.replaceState(null, "", location.pathname + (qs.toString() ? "?" + qs : "") + location.hash);
    }
    const path = location.pathname.replace(/\/$/, "") || "/app";
    const main = el("main", { class: "main", id: "main" });
    if (location.pathname !== "/onboarding") {
      const initials = USER.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
      const dot = el("span", { class: "bell-dot", hidden: true });
      const bell = el("a", { href: "#", class: "icon-link bell", title: "Reminders", "aria-label": "Reminders", onclick: (e) => { e.preventDefault(); inboxModal(dot); } }, icon("bell"), dot);
      const showDot = (r) => { dot.hidden = !(r && r.unread); };
      showDot(cacheGet("/api/reminders"));
      setTimeout(() => api("/api/reminders").then((r) => { cacheSet("/api/reminders", r); showDot(r); }).catch(() => {}), 1500);
      const inMenu = MENU.some(([h]) => h === path) || path === "/app/admin";
      const nav = el("nav", { class: "nav", "aria-label": "Main" }, NAV.map(([href, ic, label]) =>
        el("a", { href, class: path === href ? "active" : null, "aria-current": path === href ? "page" : null }, icon(ic), el("span", null, label))));
      const top = el("header", { class: "topbar" }, el("div", { class: "topbar-in" },
        el("a", { href: "/app", class: "logo", "aria-label": "Kitna home" }, wordmark()),
        nav,
        el("div", { class: "top-actions" },
          bell,
          el("button", { type: "button", class: "avatar", title: USER.name, "aria-label": "More", onclick: moreMenu }, initials))));
      const tab = (href, ic, label, extra) => el("a", Object.assign({ href, class: (href === "/app/pay" ? "pay " : "") + (path === href || (href === "#more" && inMenu) ? "active" : ""),
        "aria-current": path === href ? "page" : null }, extra || {}),
        el("span", { class: "ni" }, href === "/app/pay" ? el("span", { class: "pay-dot" }, icon(ic)) : icon(ic)), el("span", { class: "nl" }, label));
      const bottom = el("nav", { class: "bottom-nav", "aria-label": "Main" }, MOBILE_NAV.map(([href, ic, label]) =>
        href === "#more" ? tab(href, ic, label, { href: "#", onclick: (e) => { e.preventDefault(); moreMenu(); }, "aria-haspopup": "dialog" }) : tab(href, ic, label)));
      document.body.append(top, main, bottom);
    } else {
      document.body.append(main);
    }
    try {
      await renderPage(main, USER);
    } catch (e) { err(e); }
    track("screen_opened");
    if (window.FluxVoice && location.pathname !== "/onboarding") window.FluxVoice.init(USER, { fab: false });
  }

  // Grey placeholder rows while the first data loads (never a blank screen).
  function skeleton(rows = 4) {
    return el("div", { class: "card list-card", "aria-busy": "true", "aria-label": "Loading" },
      ...Array.from({ length: rows }, () => el("div", { class: "tx" }, el("div", { class: "skeleton", style: { width: "40px", height: "40px", borderRadius: "50%" } }),
        el("div", { class: "tx-main" }, el("div", { class: "skeleton", style: { width: "55%", height: "14px" } }), el("div", { class: "skeleton", style: { width: "35%", height: "11px", marginTop: "8px" } })),
        el("div", { class: "skeleton", style: { width: "56px", height: "14px" } }))));
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
    const sign = isIn ? "+" : isSave ? (t.amount < 0 ? "+" : "") : "−";  // a real minus sign, like a bank statement
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
      onDelete && !editable && t.source !== "autosave" ? el("button", { class: "icon-btn", title: "Delete", "aria-label": "Delete transaction", onclick: () => onDelete(t) }, icon("trash")) : null);
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
    const hint = t.auto_category && t.auto_category !== t.category ? el("p", { class: "tiny faint" }, `Kitna first filed this under ${t.auto_category}.`) : null;
    const body = el("div", { class: "form" },
      el("p", { class: "muted small", style: { margin: 0 } }, `${inr(Math.abs(t.amount))} · ${dateFmt(t.date)}`),
      el("label", { class: "field" }, "Category", cat),
      el("label", { class: "field" }, "Note / merchant", note),
      el("label", { class: "row", style: { gap: "8px", alignItems: "center" } }, remember, rememberText), hint);
    const v = await modal("Edit payment", body, [
      { label: "Delete", value: "delete", cls: "ghost danger-text" },
      t.kind === "expense" ? { label: "Split", value: "split" } : null,
      { label: "Save", submit: true, cls: "primary", value: () => ({ category: cat.value, note: note.value, remember: remember.checked }) },
    ].filter(Boolean));
    if (v === "split") { splitModal(t); return; }
    if (v === "delete") { deleteTx(t); return; }
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

  // ─── Split a payment with friends ─────────────────────────
  async function splitModal(t) {
    const total = Math.abs(Number(t.amount));
    const names = el("input", { class: "input", maxlength: "200", placeholder: "Rahul, Priya, Aman", required: true, "aria-label": "Friends' names" });
    const me = el("input", { type: "checkbox", checked: true });
    const list = el("div", { class: "stack", style: { gap: "8px" } });
    const mine = el("p", { class: "small muted", style: { margin: 0 } });
    let rows = [];
    const people = () => names.value.split(/[,\n]+/).map((x) => x.trim()).filter(Boolean).slice(0, 20);
    const recount = () => {
      const used = rows.reduce((a, r) => a + (Number(r.input.value) || 0), 0);
      const left = Math.round((total - used) * 100) / 100;
      mine.textContent = left < 0 ? "Friends' shares are more than you paid." : `Your share: ${inr(left)} (only this counts as your spending).`;
      mine.style.color = left < 0 ? "var(--red)" : "";
    };
    const rebuild = () => {
      const ps = people();
      const share = ps.length ? Math.floor((total / (ps.length + (me.checked ? 1 : 0))) * 100) / 100 : 0;
      rows = ps.map((name) => ({ name, input: el("input", { class: "input num", type: "number", inputmode: "decimal", min: "1", step: "0.01", value: share, "aria-label": "Share for " + name }) }));
      rows.forEach((r) => r.input.addEventListener("input", recount));
      list.replaceChildren(...rows.map((r) => el("div", { class: "row between", style: { gap: "10px" } }, el("span", null, r.name), el("div", { style: { width: "130px" } }, r.input))));
      recount();
    };
    names.addEventListener("input", rebuild);
    me.addEventListener("change", rebuild);
    rebuild();
    const body = el("div", { class: "form" },
      el("p", { class: "muted small", style: { margin: 0 } }, `${t.note || t.category} · ${inr(total)} · ${dateFmt(t.date)}`),
      el("label", { class: "field" }, "Who was it with?", names),
      el("label", { class: "row", style: { gap: "8px", alignItems: "center" } }, me, el("span", null, "I'm paying a share too")),
      list, mine,
      el("p", { class: "tiny faint" }, "When they pay you back on UPI, Kitna ticks them off by itself."));
    const v = await modal("Split with friends", body, [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Split", submit: true, cls: "primary", value: () => rows.map((r) => ({ name: r.name, amount: r.input.value })) },
    ]);
    if (!v || !v.length) return null;
    try {
      const r = await api("/api/friends/split", { method: "POST", body: { transaction_id: t.id, people: v } });
      ok(`Done. Friends owe you ${inr(r.totals.they_owe)} in total.`, { label: "See", run: () => (location.href = "/app/friends") });
      cacheDrop("/api/friends");
      refresh();
      return r;
    } catch (e) { err(e); return null; }
  }

  async function friendModal(direction = "they_owe") {
    let dir = direction;
    const person = el("input", { class: "input", maxlength: "40", placeholder: "Rahul", required: true });
    const amount = el("input", { class: "input big num", type: "number", inputmode: "decimal", min: "1", step: "0.01", placeholder: "500", required: true, "aria-label": "Amount in rupees" });
    const note = el("input", { class: "input", maxlength: "80", placeholder: "Movie tickets" });
    const day = el("input", { class: "input", type: "date", value: todayISO(), max: todayISO() });
    const seg = el("div", { class: "seg" });
    const a = el("button", { type: "button" }, "They owe me");
    const b = el("button", { type: "button" }, "I owe them");
    const paint = () => { a.className = dir === "they_owe" ? "on inc" : ""; b.className = dir === "i_owe" ? "on exp" : ""; };
    a.onclick = () => { dir = "they_owe"; paint(); };
    b.onclick = () => { dir = "i_owe"; paint(); };
    seg.append(a, b); paint();
    const v = await modal("Add money with a friend", el("div", { class: "form" }, seg,
      el("div", { class: "grid g-2" }, el("label", { class: "field" }, "Friend's name", person), el("label", { class: "field" }, "Amount (₹)", amount)),
      el("div", { class: "grid g-2" }, el("label", { class: "field" }, "What for (optional)", note), el("label", { class: "field" }, "Date", day)),
      el("p", { class: "tiny faint" }, "Money you owe is kept aside in today's number. Money friends owe you is only counted once it arrives.")), [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Save", submit: true, cls: "primary", value: () => ({ direction: dir, person: person.value, amount: amount.value, note: note.value, date: day.value }) },
    ]);
    if (!v) return null;
    try { const r = await api("/api/friends", { method: "POST", body: v }); ok("Saved."); cacheDrop("/api/friends"); refresh(); return r; } catch (e) { err(e); return null; }
  }

  // ─── Feedback: straight to the people who build Kitna ─────
  async function feedbackModal(kind = "") {
    const KINDS = [["broken", "Something's broken"], ["confusing", "Confusing"], ["idea", "An idea"], ["love", "I love it"]];
    let pick = kind;
    const chips = el("div", { class: "chips" });
    const paint = () => chips.replaceChildren(...KINDS.map(([k, label]) =>
      el("button", { type: "button", class: "chip" + (pick === k ? " on" : ""), "aria-pressed": pick === k ? "true" : "false", onclick: () => { pick = k; paint(); } }, label)));
    paint();
    const msg = el("textarea", { class: "input", rows: "4", maxlength: "1500", required: true, placeholder: "What happened, or what would make Kitna better?", "aria-label": "Your feedback" });
    const v = await modal("Tell us", el("div", { class: "form" }, chips, msg,
      el("p", { class: "tiny faint" }, "Goes straight to the people who build Kitna. Please don't include card numbers, PINs or passwords.")), [
      { label: "Cancel", value: null, cls: "ghost" },
      { label: "Send", submit: true, cls: "primary", value: () => ({ kind: pick, message: msg.value }) },
    ]);
    if (!v) return;
    if (!v.kind) { err(new Error("Choose what kind of feedback this is.")); return feedbackModal(); }
    const screen = SCREENS[location.pathname.replace(/\/$/, "") || "/app"] || "other";
    try { await api("/api/feedback", { method: "POST", body: { ...v, screen } }); ok("Thank you. We read every message."); } catch (e) { err(e); }
  }

  // ─── Reminders on this phone (Web Push) ───────────────────
  const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const pushApi = {
    supported: () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window,
    // iPhone only allows notifications for web apps added to the Home Screen (iOS 16.4+).
    needsHomeScreen: () => isIOS() && !standalone(),
    async current() {
      if (!pushApi.supported()) return null;
      try { const reg = await navigator.serviceWorker.ready; return await reg.pushManager.getSubscription(); } catch (e) { return null; }
    },
    async enable() {
      if (pushApi.needsHomeScreen()) throw new Error("On iPhone, first add Kitna to your Home Screen (Share → Add to Home Screen), open it from there, then turn reminders on.");
      if (!pushApi.supported()) throw new Error("This browser can't show notifications. Try Chrome on Android, or Kitna from the iPhone Home Screen.");
      const perm = await Notification.requestPermission();
      if (perm !== "granted") throw new Error("Notifications are blocked for Kitna. Allow them in your phone's settings for this site, then try again.");
      try { await navigator.serviceWorker.register("/sw.js"); } catch (e) { /* already registered */ }
      const reg = await navigator.serviceWorker.ready;
      const info = await api("/api/reminders");
      const raw = atob(info.public_key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (info.public_key.length % 4)) % 4));
      const key = Uint8Array.from(raw, (c) => c.charCodeAt(0));
      let sub = await reg.pushManager.getSubscription();
      if (sub) {  // a subscription made with an old server key can't be used: replace it
        const old = sub.options && sub.options.applicationServerKey ? new Uint8Array(sub.options.applicationServerKey) : null;
        if (old && old.join() !== key.join()) { await sub.unsubscribe(); sub = null; }
      }
      sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
      const r = await api("/api/reminders/subscribe", { method: "POST", body: sub.toJSON() });
      cacheDrop("/api/reminders");
      return r;
    },
    async disable() {
      const sub = await pushApi.current();
      await api("/api/reminders/unsubscribe", { method: "POST", body: { endpoint: sub ? sub.endpoint : "" } });
      if (sub) { try { await sub.unsubscribe(); } catch (e) { /* ignore */ } }
      cacheDrop("/api/reminders");
    },
  };

  async function inboxModal(dot) {
    let r;
    try { r = await api("/api/reminders"); } catch (e) { err(e); return; }
    // Stored in UTC ("2026-11-05 19:30:00"): show it as the local day, so a reminder from 1 am isn't "Yesterday".
    const when = (ts) => { const d = new Date(String(ts).replace(" ", "T") + "Z"); return isNaN(d) ? "" : dateFmt(new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)); };
    const body = el("div", { class: "stack", style: { gap: "4px", maxHeight: "60vh", overflow: "auto" } },
      r.inbox.length ? r.inbox.map((n) => el("a", { href: n.url, class: "tx", style: { textDecoration: "none", color: "inherit" } },
        avatar(n.title, n.kind === "friends" ? "users" : n.kind === "bills" ? "calendar" : n.kind === "weekly" ? "trend" : n.kind === "morning" ? "bell" : "alert"),
        el("div", { class: "tx-main" }, el("div", { class: "tx-title wrap", style: { fontWeight: n.read ? 500 : 700 } }, n.title),
          el("div", { class: "tx-sub", style: { whiteSpace: "normal" } }, n.body)),
        el("div", { class: "tiny faint" }, when(n.created_at))))
        : el("div", { class: "empty" }, el("b", null, "Nothing yet"), "Reminders about bills, late refunds and friends show up here."),
      r.phones ? null : el("a", { href: "/app/settings#reminders", class: "link small", style: { marginTop: "10px" } }, "Get these on your phone →"));
    if (r.unread) api("/api/reminders/read", { method: "POST" }).then(() => { if (dot) dot.hidden = true; cacheDrop("/api/reminders"); }).catch(() => {});
    await modal("Reminders", body);
  }

  window.Kitna = {
    el, icon, api, download, toast, ok, err, modal, confirmBox, inr, inr0, dateFmt, todayISO, CAT_EMOJI, CAT_COLORS, avatar,
    boot, pageHead, skeleton, txRow, deleteTx, editTx, addTransactionModal, planModal, splitModal, friendModal, feedbackModal, push: pushApi, live, prefetch, cacheClear, refresh, onRefresh, logout, meta,
    get user() { return USER; }, set user(u) { USER = u; }, get config() { return CONFIG; },
  };
})();
