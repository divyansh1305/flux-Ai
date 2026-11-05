/* Auto-track from bank SMS: paste alerts, or on Android share an SMS straight to Kitna (PWA share target). */
(function () {
  const { el, icon, api, ok, err, inr, pageHead, CAT_EMOJI } = window.Kitna;
  const SAMPLE = "Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici (UPI Ref No 512345678901).\n\n" +
    "Sent Rs.180.00 From HDFC Bank A/C *1234 To UBER INDIA On 01/11/26 Ref 512345678902";

  async function render(main) {
    const params = new URLSearchParams(location.search);
    const shared = [params.get("title"), params.get("text"), params.get("url")].filter(Boolean).join("\n").trim();
    const area = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Track from SMS", "Paste your bank's debit/credit SMS. Kitna reads amount, merchant and date, and ignores OTPs and offers."), area);
    showInput(shared);
    if (shared) parse(shared);

    function showInput(text) {
      const ta = el("textarea", { class: "input", placeholder: "Paste one or more bank SMS here…", "aria-label": "Bank SMS" });
      ta.value = text || "";
      area.replaceChildren(el("div", { class: "grid g-main" },
        el("div", { class: "card form" }, ta,
          el("div", { class: "row wrap" },
            el("button", { class: "btn primary", onclick: () => parse(ta.value) }, "Find transactions"),
            el("button", { class: "btn ghost", onclick: () => { ta.value = SAMPLE; } }, "Try a sample"))),
        el("div", { class: "card" }, el("h3", null, "Fastest on Android"),
          el("ol", { class: "small muted", style: { paddingLeft: "18px", margin: "10px 0 0", lineHeight: 1.9 } },
            el("li", null, "Install Kitna: browser menu → “Add to Home screen”"),
            el("li", null, "Long-press a bank SMS → Share → Kitna"),
            el("li", null, "Confirm, done. No typing.")),
          el("p", { class: "tiny faint", style: { marginTop: "12px" } }, "Kitna only sees messages you choose to share. It never reads your inbox."),
          el("a", { class: "link", href: "/app/settings", style: { display: "inline-block", marginTop: "10px" } }, "iPhone: make it fully automatic →"))));
    }

    async function parse(text) {
      if (!text.trim()) return err("Paste at least one SMS.");
      try {
        const r = await api("/api/import/sms", { method: "POST", body: { text } });
        showRows(r, text);
      } catch (e) { err(e); }
    }

    function showRows(r, text) {
      const rows = r.rows.map((x) => ({ ...x, include: !x.duplicate }));
      const list = el("div", { class: "tx-list" });
      rows.forEach((row) => {
        const cb = el("input", { type: "checkbox", checked: row.include ? true : null, "aria-label": "Include" });
        cb.onchange = () => (row.include = cb.checked);
        const cats = row.kind === "income" ? r.categories.income : r.categories.expense;
        const sel = el("select", { class: "input", style: { width: "auto", padding: "6px 30px 6px 10px", fontSize: "13px" } },
          cats.map((c) => el("option", { value: c, selected: c === row.category ? true : null }, c)));
        sel.onchange = () => (row.category = sel.value);
        list.appendChild(el("div", { class: "tx", style: { opacity: row.duplicate ? 0.5 : 1 } }, cb,
          window.Kitna.avatar(row.note || row.category),
          el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, row.note), el("div", { class: "tx-sub" }, row.date, row.duplicate ? " · already added" : "")),
          sel, el("div", { class: "tx-amt " + (row.kind === "income" ? "green" : "") }, (row.kind === "income" ? "+" : "-") + inr(row.amount))));
      });
      area.replaceChildren(el("div", { class: "card" },
        el("div", { class: "card-head" }, el("h2", null, `Found ${rows.length} transaction${rows.length === 1 ? "" : "s"}`),
          el("span", { class: "tiny faint" }, r.ignored ? `${r.ignored} message(s) ignored` : "")),
        list,
        el("div", { class: "row", style: { marginTop: "16px" } },
          el("button", { class: "btn primary", onclick: async () => {
            const chosen = rows.filter((x) => x.include);
            if (!chosen.length) return err("Nothing selected.");
            try {
              const c = await api("/api/import/commit", { method: "POST", body: { rows: chosen, source: "sms" } });
              ok(`Added ${c.imported} transaction(s).`);
              location.href = "/app";
            } catch (e) { err(e); }
          } }, icon("check"), "Add to Kitna"),
          el("button", { class: "btn ghost", onclick: () => showInput(text) }, "Back"))));
    }
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
