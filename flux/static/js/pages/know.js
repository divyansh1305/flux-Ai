/* "What Kitna knows": every data source and record type, in plain words, with export and delete one tap away. */
(function () {
  const { el, icon, api, err, pageHead, download } = window.Kitna;

  const row = (k, v, sub) => el("div", { class: "kv" }, el("div", { class: "k" }, k, sub ? el("small", null, sub) : null), el("div", { class: "v" }, v));

  async function render(main) {
    const k = await api("/api/account/knows");
    const g = k.sources.gmail, p = k.sources.phone;
    const c = k.counts;
    main.replaceChildren(pageHead("What Kitna knows", "Everything Kitna has about you, and how to take it back."),
      el("div", { class: "stack narrow" },
        el("div", { class: "card", style: { padding: "6px 20px" } },
          row("Gmail", g.connected ? (g.needs_reconnect ? "Needs reconnect" : "Connected") : "Not connected",
            g.connected ? `${g.email}. Kitna reads only bank alert emails. It can't send, delete or change anything, and never keeps the email itself.` : null),
          row("Phone (Android app or iPhone link)", p.connected ? "Connected" : "Not connected",
            p.connected ? "Sends bank and UPI payment alerts to Kitna. OTPs, chats and other notifications are never sent." : null),
          el("div", { class: "row", style: { gap: "8px", padding: "12px 0" } }, el("a", { class: "btn sm", href: "/app/settings#auto" }, "Manage connections"))),
        el("div", { class: "card", style: { padding: "6px 20px" } },
          el("h2", { style: { margin: "14px 0 4px" } }, "What's stored"),
          row("Payments", String(c.transactions), "Amount, merchant name, date, category, and the bank reference number"),
          row("Plans", String(c.plans)),
          row("Goals and budgets", `${c.goals} · ${c.budgets}`),
          row("Your category choices", String(c.merchant_rules), "e.g. \"Always file Rapido as Travel\""),
          row("Bank balances seen in alerts", String(c.bank_balances), "Used to check Kitna matches your bank"),
          row("Friends", String(c.friends || 0), "Names and amounts you added on the Friends screen"),
          row("Reminders", `${c.reminders || 0} · on ${c.phones_with_reminders || 0} phone${c.phones_with_reminders === 1 ? "" : "s"}`, "What Kitna told you, and the phones you turned notifications on for"),
          row("Feedback you sent", String(c.feedback || 0), "Your own words, so we can fix what you told us about"),
          row("Usage counts", String(c.usage_events), "Which screens you opened, never amounts or merchants. Only totals across everyone are looked at"),
          row("Masked message samples", k.contribute_samples ? String(c.masked_samples) : "Off", "Only if you turned on \"Help Kitna read more banks\". Numbers and names are hidden first")),
        el("div", { class: "card" },
          el("h2", null, "What Kitna never does"),
          el("ul", { class: "small", style: { margin: "10px 0 0", paddingLeft: "18px", lineHeight: 1.7 } },
            ["Never sells or shares your data", "Never shows ads or offers loans", "Never stores OTPs, passwords or full email text",
             "Never moves money: Kitna can't pay anyone or touch your bank account",
             "When you ask Kitna a question, only the numbers needed to answer it are sent to Google's Gemini to write the reply"].map((t) => el("li", null, t)))),
        el("div", { class: "card" },
          el("h2", null, "Take it with you, or delete it"),
          el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "Download everything as a file, or delete your account. Deleting also removes Kitna's access to your Gmail."),
          el("div", { class: "row wrap", style: { gap: "8px" } },
            el("button", { class: "btn", onclick: () => download("/api/account/export", "kitna-my-data.json").catch(err) }, icon("download"), "Download my data"),
            el("a", { class: "btn ghost", href: "/app/settings#data" }, icon("trash"), "Delete account")),
          el("p", { class: "tiny faint", style: { marginTop: "14px" } }, "Kitna is for people aged 18 and over. Questions or a request about your data: reply to any email you got from Kitna. ",
            el("a", { class: "brand", href: "/privacy" }, "Privacy page")))));
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
