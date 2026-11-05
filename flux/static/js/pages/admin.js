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

  async function render(main) {
    const box = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Kitna numbers", "Totals about everyone using Kitna. Only you can see this page. No one's money is shown.",
      el("button", { class: "btn", onclick: async () => {
        try { const r = await api("/api/admin/rollup", { method: "POST" }); ok(`Daily totals updated (${r.rolled_up.length} day${r.rolled_up.length === 1 ? "" : "s"}).`); load(); } catch (e) { err(e); }
      } }, "Update daily totals")), box);

    async function load() {
      const [d, fb] = await Promise.all([api("/api/admin/overview"), api("/api/admin/feedback").catch(() => [])]);
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
      box.replaceChildren(fbCard,
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
