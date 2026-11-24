/* A tenant's own rent page (/r/<token>): no sign-in. Their dues, the owner's UPI ID and QR, and receipts.
   Money goes straight to the owner's UPI ID; Kitna never handles it. */
(function () {
  const { el, icon, api, inr0, dateFmt, ok, err } = window.Kitna;
  const monthName = (ym) => new Date(ym + "-01T00:00:00").toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const token = location.pathname.split("/").filter(Boolean).pop();

  async function start() {
    const main = el("main", { class: "main tenant-page" }, el("div", { class: "narrow stack" }, window.Kitna.skeleton(3)));
    document.body.append(main);
    let v;
    try { v = await api(`/api/r/${token}`); } catch (e) {
      main.replaceChildren(el("div", { class: "narrow card empty", style: { marginTop: "40px" } }, el("b", null, "Link not found"), e.message));
      return;
    }
    document.title = `${v.property} · Rent`;
    const first = v.tenant.split(" ")[0];
    const due = v.balance > 0;
    const status = el("section", { class: "today" + (v.money === "late" ? " careful" : "") },
      el("div", { class: "today-label" }, due ? "Rent to pay" : "Your rent"),
      el("div", { class: "today-num num" }, due ? inr0(v.balance) : "All paid"),
      el("div", { class: "today-sub" }, due
        ? (v.money === "late" ? `${v.late_days} day${v.late_days === 1 ? "" : "s"} late (was due ${dateFmt(v.due_on)})` : `Due by ${dateFmt(v.due_on)}`)
        : v.advance > 0 ? `${inr0(v.advance)} paid in advance. Thank you!` : `Next rent ${inr0(v.rent)} is due on the ${v.due_day}${ord(v.due_day)}.`));

    const copy = async () => {
      try { await navigator.clipboard.writeText(v.upi_id); ok("UPI ID copied. Paste it in GPay, PhonePe or Paytm."); }
      catch (e) { window.prompt("Copy this UPI ID", v.upi_id); }
    };
    const pay = v.upi_id && due ? el("section", { class: "card stack", style: { gap: "12px" } },
      el("h2", null, "How to pay"),
      el("div", { class: "upi-box" },
        el("div", { style: { minWidth: 0 } }, el("div", { class: "tiny faint" }, `Pay ${v.property} at`), el("div", { class: "upi-id" }, v.upi_id)),
        el("button", { class: "btn sm", type: "button", onclick: copy }, "Copy")),
      el("ol", { class: "pay-how small" },
        el("li", null, "Open GPay, PhonePe or Paytm → Pay to UPI ID"),
        el("li", null, "Paste the ID, enter ", el("b", null, inr0(v.balance)), " and pay with your PIN")),
      el("details", { class: "auto-more" }, el("summary", null, "Or scan a QR (from another phone or a screenshot)"),
        el("div", { class: "qr-wrap" }, el("img", { src: `/api/r/${token}/qr.svg`, alt: `UPI QR to pay ${inr0(v.balance)} to ${v.property}`, width: "220", height: "220" })),
        el("p", { class: "tiny faint", style: { textAlign: "center" } }, "Screenshot this, then in your UPI app tap Scan → Gallery.")),
      el("p", { class: "tiny faint" }, `Your payment goes straight to ${v.property}'s bank account. It shows here once their bank confirms it.`)) : null;

    const months = v.months.length ? el("section", null, el("div", { class: "section-title" }, el("span", null, "Months")),
      el("div", { class: "card list-card" }, el("div", { class: "month-rows" }, v.months.map((m) => el("div", { class: "month-row" },
        el("span", null, monthName(m.month)),
        el("span", { class: "rent-pill " + (m.status === "paid" ? "paid" : m.status === "part" ? "due" : "late") },
          m.status === "paid" ? "Paid" : m.status === "part" ? `${inr0(m.paid)} of ${inr0(m.rent)}` : "Not paid")))))) : null;

    const receipts = v.payments.length ? el("section", null, el("div", { class: "section-title" }, el("span", null, "Receipts"),
      el("button", { class: "link", type: "button", onclick: () => window.print() }, "Print / PDF")),
      el("div", { class: "card list-card" }, el("div", { class: "tx-list" }, v.payments.map((p) => el("div", { class: "tx" },
        el("div", { class: "cat-ic" }, icon("check")),
        el("div", { class: "tx-main" }, el("div", { class: "tx-title" }, `Rent received · ${inr0(p.amount)}`),
          el("div", { class: "tx-sub" }, `${dateFmt(p.date)} · ${{ upi: "UPI", cash: "Cash", bank: "Bank" }[p.method]} · ${v.property}`)),
        el("div", { class: "tx-amt num" }, inr0(p.amount))))))) : null;

    main.replaceChildren(el("div", { class: "narrow stack", style: { gap: "16px" } },
      el("header", { class: "large-title" }, el("div", { class: "lt-date" }, v.property + (v.room ? ` · Room ${v.room}` : "")), el("h1", null, `Hi, ${first}`)),
      status, pay, months, receipts,
      el("p", { class: "tiny faint", style: { textAlign: "center", marginTop: "8px" } },
        "Rent kept by ", el("a", { href: "/?ref=tenant", class: "link" }, "Kitna"), ". Track your own spending free.")));
  }

  const ord = (n) => (n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th");
  document.addEventListener("DOMContentLoaded", start);
})();
