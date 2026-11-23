/* Kitna numbers: totals about the whole app, for the people in ADMIN_EMAILS only. No one's money is shown. */
(function () {
  const { el, api, ok, err, pageHead, inr0 } = window.Kitna;

  const stat = (label, value, sub) => el("div", { class: "card", style: { padding: "16px" } },
    el("div", { class: "tiny faint" }, label), el("div", { style: { fontSize: "26px", fontWeight: 750, marginTop: "4px" } }, value),
    sub ? el("div", { class: "tiny muted", style: { marginTop: "2px" } }, sub) : null);
  const pct = (v) => (v === null || v === undefined ? "—" : v + "%");
  const bar = (p) => el("div", { class: "bar ok", style: { marginTop: "6px" } }, el("i", { style: { width: Math.max(0, Math.min(100, p || 0)) + "%" } }));
  const table = (head, rows) => el("table", { class: "table", style: { width: "100%", fontSize: "14px" } },
    el("thead", null, el("tr", null, head.map((h, i) => el("th", { style: { textAlign: i ? "right" : "left", padding: "6px 4px" } }, h)))),
    el("tbody", null, rows.length ? rows.map((r) => el("tr", null, r.map((c, i) => el("td", { style: { textAlign: i ? "right" : "left", padding: "6px 4px", borderTop: "1px solid var(--line)" } }, String(c)))))
      : el("tr", null, el("td", { colspan: head.length, class: "muted", style: { padding: "8px 4px" } }, "Nothing yet"))));
  const section = (title, sub, ...kids) => el("section", { class: "card" }, el("h2", null, title),
    sub ? el("p", { class: "tiny faint", style: { margin: "4px 0 12px" } }, sub) : null, ...kids);

  const yes = (b) => (b ? "✓" : "–");
  const day = (t) => (t ? t.slice(0, 10) : "never");

  // People: who uses Kitna and whether it works for them. No amounts or payment details, by design.
  function usersCard() {
    const list = el("div");
    const q = el("input", { class: "input", placeholder: "Search name or email", style: { maxWidth: "320px" } });
    let page = 1, timer = null;
    async function draw() {
      const r = await api(`/api/admin/users?page=${page}&q=${encodeURIComponent(q.value)}`);
      const rows = r.users.map((u) => el("tr", { class: "tap", style: { cursor: "pointer" }, onclick: () => userSheet(u.id) },
        el("td", { style: { padding: "8px 4px" } }, el("b", null, u.name), el("div", { class: "tiny faint" }, u.email)),
        ...[day(u.joined), yes(u.setup_done), [u.gmail ? "Gmail" : "", u.phone ? "Phone" : ""].filter(Boolean).join(" + ") || "–",
          `${u.auto_payments}/${u.payments}`, day(u.last_active)].map((c) => el("td", { style: { textAlign: "right", padding: "8px 4px", borderTop: "1px solid var(--line)" } }, c))));
      list.replaceChildren(
        el("div", { class: "admin-scroll" }, el("table", { class: "table", style: { width: "100%", minWidth: "560px", fontSize: "14px" } },
          el("thead", null, el("tr", null, ["Person", "Joined", "Setup", "Connected", "Auto / all payments", "Last seen"].map((h, i) =>
            el("th", { style: { textAlign: i ? "right" : "left", padding: "6px 4px" } }, h)))),
          el("tbody", null, rows.length ? rows : el("tr", null, el("td", { colspan: 6, class: "muted", style: { padding: "8px 4px" } }, "No one found"))))),
        el("div", { class: "row between", style: { marginTop: "10px" } },
          el("span", { class: "tiny faint" }, `${r.total} people · page ${r.page}`),
          el("div", { class: "row", style: { gap: "6px" } },
            page > 1 ? el("button", { class: "btn sm", onclick: () => { page--; draw(); } }, "Previous") : null,
            r.page * 50 < r.total ? el("button", { class: "btn sm", onclick: () => { page++; draw(); } }, "Next") : null)));
    }
    q.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { page = 1; draw().catch(err); }, 250); };
    draw().catch(err);
    return section("People", "Everyone who signed up and whether Kitna works for them. Amounts and payment details are never shown here.",
      el("div", { class: "row between wrap", style: { gap: "10px", marginBottom: "8px" } }, q,
        el("a", { class: "btn sm", href: "/api/admin/users.csv" }, "Download CSV")), list);
  }

  async function userSheet(id) {
    let u;
    try { u = await api(`/api/admin/users/${id}`); } catch (e) { err(e); return; }
    const kv = (k, v) => el("div", { class: "how-row" }, el("span", null, k), el("b", null, String(v)));
    const g = u.gmail_detail, p = u.phone_detail;
    window.Kitna.modal(u.name, el("div", { class: "how" },
      kv("Email", u.email), kv("Joined", day(u.joined)), kv("Last seen", day(u.last_active)), kv("Language", u.lang),
      kv("Setup finished", yes(u.setup_done)), kv("Money comes in", u.money_setup.income + (u.money_setup.pay_day ? ` (day ${u.money_setup.pay_day})` : "")),
      kv("Gmail", g ? (g.needs_reconnect ? "needs reconnect" : `ok, last sync ${day(g.last_sync_at)}`) + (g.last_error ? " · error" : "") : "not connected"),
      kv("Phone app / Shortcut", p ? `${p.uses} messages, last ${day(p.last_used_at)}` : "not linked"),
      kv("Reminders on a phone", yes(u.reminders)),
      kv("Payments by source", Object.entries(u.payments_by_source).map(([k, n]) => `${k} ${n}`).join(" · ") || "none"),
      kv("Messages Kitna couldn't read (30 days)", u.unread_messages_30d),
      u.errors_7d.length ? kv("Errors seen (7 days)", u.errors_7d.map((x) => `${x.screen} ${x.n}`).join(" · ")) : null,
      u.helper_questions.length ? el("div", null, el("b", null, "Asked the helper"),
        el("ul", { class: "small muted", style: { paddingLeft: "18px" } }, u.helper_questions.map((h) => el("li", null, `${h.question} (${h.lang}${h.answered ? "" : ", not answered"})`)))) : null,
      u.feedback.length ? el("div", null, el("b", null, "Feedback"),
        el("ul", { class: "small muted", style: { paddingLeft: "18px" } }, u.feedback.map((f) => el("li", null, `${f.kind}: ${f.message}`)))) : null,
      el("div", null, el("b", null, "Recent activity"),
        el("div", { class: "tiny muted" }, u.recent_activity.map((a) => `${a.created_at.slice(5, 16)} ${a.name}${a.prop ? " " + a.prop : ""}`).join(" · ") || "none"))));
  }

  // What people ask the helper: the unanswered ones are the next thing to explain better (or build).
  function helpCard(h) {
    if (!h) return null;
    const langs = Object.entries(h.languages).map(([k, n]) => `${k} ${n}`).join(" · ") || "none yet";
    return section(`Helper questions (${h.total_30d} in 30 days, ${h.unanswered_30d} not answered)`, `Languages: ${langs}. Digits are hidden.`,
      h.recent.length ? el("div", { class: "tx-list" }, h.recent.slice(0, 40).map((x) => el("div", { class: "tx" },
        el("div", { class: "tx-main" }, el("div", { class: "tx-title wrap" }, x.question),
          el("div", { class: "tx-sub" }, `${x.email} · ${x.lang} · ${x.screen || "app"} · ${x.created_at.slice(0, 16)}`)),
        x.answered ? null : el("span", { class: "badge" }, "not answered")))) : el("p", { class: "small muted" }, "No questions yet."));
  }

  async function render(main) {
    const box = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Kitna admin", "People, questions, feedback and totals. Only admins can see this page. No one's money is shown.",
      el("button", { class: "btn", onclick: async () => {
        try { const r = await api("/api/admin/rollup", { method: "POST" }); ok(`Daily totals updated (${r.rolled_up.length} day${r.rolled_up.length === 1 ? "" : "s"}).`); load(); } catch (e) { err(e); }
      } }, "Update daily totals")), box);

    async function load() {
      const [d, fb, hq] = await Promise.all([api("/api/admin/overview"), api("/api/admin/feedback").catch(() => []),
        api("/api/admin/help").catch(() => null)]);
      const KIND = { broken: "Broken", confusing: "Confusing", idea: "Idea", love: "Love it" };
      const fbCard = section(`Feedback (${fb.filter((f) => f.status === "new").length} new)`, "What people told you from inside the app. Their own words.",
        fb.length ? el("div", { class: "tx-list" }, fb.slice(0, 50).map((f) => el("div", { class: "tx-item" },
          el("div", { class: "tx", style: { alignItems: "flex-start" } },
            el("div", { class: "tx-main" },
              el("div", { class: "tx-title wrap" }, `${KIND[f.kind]} · ${f.screen || "app"}`),
              el("div", { class: "small", style: { whiteSpace: "pre-wrap", marginTop: "4px" } }, f.message),
              el("div", { class: "tx-sub" }, `${f.email} · ${f.created_at.slice(0, 16)}`)),
            f.status === "new" ? el("button", { class: "btn sm ghost", onclick: async (e) => {
              try { await api(`/api/admin/feedback/${f.id}/read`, { method: "POST" }); e.target.remove(); } catch (x) { err(x); }
            } }, "Mark read") : el("span", { class: "tiny faint" }, "read"))))) : el("p", { class: "small muted" }, "No feedback yet."));
      const t = d.totals, r = d.retention;
      const maxDaily = Math.max(1, ...d.daily.map((x) => Math.max(x.signups, x.active_users)));
      box.replaceChildren(usersCard(), helpCard(hq), fbCard,
        el("div", { class: "grid g-3" },
          stat("People signed up", t.users, `${t.setup_done} finished setup`),
          stat("Active in the last 7 days", t.active_7d, `${t.active_30d} in the last 30 days`),
          stat("Connected payments", t.connected, `${t.with_auto_payment} got a payment automatically`),
          stat("Automatic payments (30 days)", t.payments_auto_30d),
          stat("Refunds Kitna watched that came back", t.refunds_back),
          stat("Money Kitna helped keep", inr0(t.kept_rupees), "From refunds that came back")),
        section("Setup: where people stop", "People who signed up in the last 30 days, and how far they got.",
          ...d.funnel.map((f) => el("div", { style: { margin: "10px 0" } },
            el("div", { class: "row between small" }, el("span", null, f.step), el("b", null, `${f.users} · ${pct(f.pct)}`)), bar(f.pct)))),
        section("Do people come back?", `Of the ${r.cohort} people who signed up 8–60 days ago.`,
          el("div", { class: "grid g-3" }, stat("Next day", pct(r.day1)), stat("In week 2", pct(r.day7)),
            stat("After a month", pct(r.day30), r.day30_cohort ? `of ${r.day30_cohort} old enough` : "Not enough data yet"))),
        section("Which connection works", "Last 30 days. \"Not understood\" = a bank message Kitna couldn't read: improve the reader for these first.",
          table(["Source", "Payments logged", "Not understood", "Read rate"],
            Object.entries(d.sources).map(([k, v]) => [{ sms: "Bank SMS (iPhone link)", notification: "Android app", email: "Gmail" }[k] || k, v.logged, v.unread, pct(v.read_rate)]))),
        section("Money checks", "Last 90 days. Many dismissals means a check is noise: change or drop it.",
          table(["Check", "Shown", "Dismissed"], d.checks.map((c) => [{ refund: "Failed payment watch", double: "Charged twice", price: "Price went up" }[c.type], c.found, c.dismissed]))),
        el("div", { class: "grid g-2" },
          section("Screens people open", "Last 30 days.", table(["Screen", "Opens", "People"], d.screens.map((s) => [s.name, s.count, s.users]))),
          section("What people ask Kitna", "Last 30 days, by type of question.", table(["Question type", "Times"], d.questions.map((q) => [q.name.replace(/_/g, " "), q.count])))),
        section("Errors people saw", "Last 7 days, by screen. Anything here is worth fixing.", table(["Screen", "Errors", "People"], d.errors.map((e) => [e.name, e.count, e.users]))),
        section("Last 30 days", "From the daily totals (run nightly by the scheduled task, or press \"Update daily totals\").",
          el("div", { class: "row", style: { alignItems: "flex-end", gap: "3px", height: "110px", marginTop: "8px" } },
            d.daily.map((x) => el("div", { title: `${x.day}: ${x.signups} sign-ups, ${x.active_users} active`, style: { flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: "2px", height: "100%" } },
              el("div", { style: { height: (x.active_users / maxDaily) * 100 + "%", background: "var(--brand)", borderRadius: "3px", minHeight: x.active_users ? "3px" : 0 } }),
              el("div", { style: { height: (x.signups / maxDaily) * 100 + "%", background: "var(--amber, #d0913a)", borderRadius: "3px", minHeight: x.signups ? "3px" : 0 } })))),
          el("div", { class: "tiny faint", style: { marginTop: "8px" } }, "Green: active people · Orange: sign-ups")),
        el("p", { class: "tiny faint" }, "Updated " + d.generated_at.replace("T", " ").replace("Z", " UTC")));
    }
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
