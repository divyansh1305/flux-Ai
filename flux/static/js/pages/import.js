(function () {
  const { el, icon, api, ok, err, inr, pageHead, CAT_EMOJI } = window.Kitna;

  async function render(main) {
    const area = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Add bank statement", "Upload the PDF your bank emails you, or a CSV. Kitna sorts every transaction for you."), area);
    showUpload();

    function showUpload() {
      const input = el("input", { type: "file", accept: ".pdf,.csv,.txt,application/pdf,text/csv", class: "sr-only", id: "file" });
      const drop = el("label", { for: "file", class: "card", style: { display: "block", border: "2px dashed var(--line-2)", background: "transparent", textAlign: "center", padding: "48px 20px", cursor: "pointer" } },
        el("div", { class: "feature", style: { display: "flex", justifyContent: "center" } }, el("div", { class: "ico" }, icon("file"))),
        el("h2", { style: { margin: "10px 0 6px" } }, "Drop your statement here"),
        el("p", { class: "muted small" }, "PDF or CSV · password-protected PDFs work too · max 5 MB"), input);
      ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.style.borderColor = "var(--brand)"; }));
      ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => (drop.style.borderColor = "var(--line-2)")));
      drop.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
      input.onchange = () => input.files[0] && upload(input.files[0]);
      area.replaceChildren(drop,
        el("a", { href: "/app/share", class: "card tap row", style: { gap: "14px" } }, el("div", { class: "feature" }, el("div", { class: "ico", style: { margin: 0 } }, icon("chat"))),
          el("div", { style: { flex: 1 } }, el("h3", null, "Got bank SMS instead?"), el("div", { class: "small muted" }, "Paste or share your debit/credit alerts and Kitna adds them.")),
          el("span", { class: "link" }, "Track from SMS →")),
        el("div", { class: "grid g-2" },
        el("div", { class: "card" }, el("h3", null, "Where to find your statement"),
          el("ul", { class: "small muted", style: { paddingLeft: "18px", margin: "10px 0 0", lineHeight: 1.8 } },
            el("li", null, "Easiest: the monthly e-statement PDF in your email (search “statement” in Gmail)"),
            el("li", null, "Or net banking → Accounts → Statement → choose dates → Download PDF or CSV"),
            el("li", null, "Works with HDFC, SBI, ICICI, Axis, Kotak and most others"),
            el("li", null, "Excel file? Open it and “Save as” CSV first"))),
        el("div", { class: "card" }, el("h3", null, "Your privacy"),
          el("p", { class: "small muted", style: { marginTop: "10px" } }, "The file is read once and not stored. Only the transactions you confirm are saved to your account. Categories are worked out on our server; nothing is sent to third parties."),
          el("a", { class: "btn sm", href: "/static/sample_statement.csv", download: "sample_statement.csv", style: { marginTop: "12px" } }, icon("download"), "Try with sample data"))));
    }

    let format = "csv";
    async function upload(file, password) {
      area.replaceChildren(el("div", { class: "card" }, el("div", { class: "skeleton", style: { height: "20px", width: "40%" } }), el("div", { class: "skeleton", style: { height: "200px", marginTop: "14px" } })));
      const fd = new FormData();
      fd.append("file", file);
      if (password) fd.append("password", password);
      try {
        const r = await api("/api/import/preview", { method: "POST", body: fd });
        if (r.needs_password) { askPassword(file, r); return; }
        format = r.format || "csv";
        showPreview(r);
      } catch (e) { err(e); showUpload(); }
    }

    function askPassword(file, r) {
      const pw = el("input", { class: "input", type: "password", autocomplete: "off", required: true, placeholder: "Statement password", "aria-label": "PDF password" });
      const form = el("form", { class: "card form", onsubmit: (e) => { e.preventDefault(); if (pw.value) upload(file, pw.value); } },
        el("h2", null, r.wrong ? "That password didn't work" : "This PDF has a password"),
        el("p", { class: "small muted" }, r.message),
        el("p", { class: "tiny faint" }, "Common formats: first 4 letters of your name + date of birth (DDMM), your customer ID, or date of birth (DDMMYYYY). The password is used once to open the file and is never saved."),
        pw, el("div", { class: "row", style: { gap: "8px" } }, el("button", { class: "btn primary", type: "submit" }, "Open statement"),
          el("button", { class: "btn ghost", type: "button", onclick: showUpload }, "Choose another file")));
      area.replaceChildren(form);
      setTimeout(() => pw.focus(), 30);
    }

    function showPreview(r) {
      const rows = r.rows.map((x) => ({ ...x, include: !x.duplicate }));
      const tbody = el("tbody");
      const countEl = el("span");
      const updateCount = () => {
        const n = rows.filter((x) => x.include).length;
        countEl.textContent = `Import ${n} transaction${n === 1 ? "" : "s"}`;
      };
      rows.forEach((row) => {
        const cb = el("input", { type: "checkbox", checked: row.include ? true : null, "aria-label": "Include" });
        cb.onchange = () => { row.include = cb.checked; updateCount(); };
        const cats = row.kind === "income" ? r.categories.income : r.categories.expense;
        const sel = el("select", { class: "input", style: { padding: "6px 30px 6px 8px", fontSize: "13px" } }, cats.map((c) => el("option", { value: c, selected: c === row.category ? true : null }, c)));
        sel.onchange = () => (row.category = sel.value);
        tbody.appendChild(el("tr", { style: { opacity: row.duplicate ? 0.5 : 1 } },
          el("td", null, cb),
          el("td", { class: "small" }, row.date),
          el("td", null, el("div", { class: "small", style: { fontWeight: 600 } }, row.note), el("div", { class: "tiny faint raw-text" }, row.raw), row.duplicate ? el("span", { class: "badge" }, "already imported") : null),
          el("td", null, sel, row.auto ? null : el("div", { class: "tiny amber" }, "check this")),
          el("td", { class: "right num " + (row.kind === "income" ? "green" : "") }, (row.kind === "income" ? "+" : "-") + inr(row.amount))));
      });
      updateCount();
      const go = el("button", { class: "btn primary", onclick: async () => {
        const chosen = rows.filter((x) => x.include);
        if (!chosen.length) return err("Select at least one transaction.");
        go.disabled = true;
        try {
          const res = await api("/api/import/commit", { method: "POST", body: { rows: chosen, format } });
          ok(`Imported ${res.imported} transactions.` + (res.duplicates_skipped ? ` Skipped ${res.duplicates_skipped} duplicates.` : ""));
          location.href = "/app";
        } catch (e) { err(e); go.disabled = false; }
      } }, countEl);
      const s = r.stats;
      area.replaceChildren(
        el("div", { class: "grid g-4" },
          el("div", { class: "card stat" }, el("div", { class: "label" }, "Transactions found"), el("div", { class: "value" }, String(s.total))),
          el("div", { class: "card stat" }, el("div", { class: "label" }, "Auto-categorised"), el("div", { class: "value green" }, s.auto_percent + "%")),
          el("div", { class: "card stat" }, el("div", { class: "label" }, "Already imported"), el("div", { class: "value" }, String(s.duplicates))),
          el("div", { class: "card stat" }, el("div", { class: "label" }, "Rows skipped"), el("div", { class: "value faint" }, String(r.skipped)))),
        el("div", { class: "card" },
          el("div", { class: "card-head" }, el("h2", null, "Review before importing"), el("div", { class: "actions" }, el("button", { class: "btn ghost", onclick: showUpload }, "Choose another file"), go)),
          el("p", { class: "small muted", style: { marginBottom: "12px" } }, "Rows marked “check this” didn't match a known merchant. Fix any category, untick anything you don't want, then import."),
          el("div", { class: "table-wrap" }, el("table", { class: "table" },
            el("thead", null, el("tr", null, el("th"), el("th", null, "Date"), el("th", null, "Description"), el("th", null, "Category"), el("th", { class: "right" }, "Amount"))), tbody))));
    }
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
