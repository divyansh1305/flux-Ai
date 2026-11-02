(function () {
  const { el, icon, api, ok, err, modal, confirmBox, inr0, pageHead, onRefresh, meta, CAT_EMOJI } = window.Flux;

  async function budgetModal(existing) {
    const m = await meta();
    const cat = el("select", { class: "input", disabled: existing ? true : null },
      m.expense_categories.map((c) => el("option", { value: c, selected: existing && existing.category === c ? true : null }, (CAT_EMOJI[c] || "") + " " + c)));
    const limit = el("input", { class: "input big num", type: "number", min: "1", step: "1", required: true, value: existing ? existing.limit : "", placeholder: "4000" });
    const v = await modal(existing ? "Edit budget" : "New monthly budget",
      el("div", { class: "form" }, el("label", { class: "field" }, "Category", cat), el("label", { class: "field" }, "Monthly limit (₹)", limit),
        el("p", { class: "tiny faint" }, "Flux warns you before an expense would break this, and when you're spending faster than the month allows.")),
      [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Save", submit: true, cls: "primary", value: () => ({ category: cat.value, limit: limit.value }) }]);
    if (!v) return;
    try {
      await api("/api/budgets/" + encodeURIComponent(v.category), { method: "PUT", body: { limit: v.limit } });
      ok(`Budget saved: ${v.category}.`);
      window.Flux.refresh();
    } catch (e) { err(e); }
  }

  async function render(main) {
    const box = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Budgets", "Monthly limits per category. Resets on the 1st.",
      el("button", { class: "btn primary", onclick: () => budgetModal() }, icon("plus"), "New budget")), box);

    async function load() {
      const [budgets, ins] = await Promise.all([api("/api/budgets"), api("/api/insights")]);
      const unbudgeted = ins.this_month.by_category.filter((c) => !budgets.some((b) => b.category === c.category));
      const total = budgets.reduce((a, b) => a + b.limit, 0);
      const spent = budgets.reduce((a, b) => a + b.spent, 0);
      const today = new Date();
      const daysLeft = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate() - today.getDate();
      const cards = budgets.map((b) => el("div", { class: "card" },
        el("div", { class: "row between" }, el("h3", null, (CAT_EMOJI[b.category] || "") + " " + b.category),
          el("span", { class: "pill " + b.state }, b.state === "ok" ? "On track" : b.state === "ahead" ? "Spending fast" : "Over budget")),
        el("div", { class: "row between", style: { margin: "14px 0 8px" } },
          el("div", null, el("div", { class: "stat" }, el("div", { class: "value", style: { fontSize: "22px" } }, inr0(b.spent))), el("div", { class: "tiny faint" }, "of " + inr0(b.limit))),
          el("div", { style: { textAlign: "right" } }, el("div", { class: b.left < 0 ? "red" : "green", style: { fontWeight: 700 } }, b.left < 0 ? inr0(-b.left) + " over" : inr0(b.left) + " left"),
            el("div", { class: "tiny faint" }, b.left > 0 && daysLeft > 0 ? `~${inr0(b.left / daysLeft)}/day for ${daysLeft} days` : ""))),
        el("div", { class: "bar " + b.state }, el("i", { style: { width: Math.min(100, b.percent) + "%" } })),
        el("div", { class: "row", style: { marginTop: "14px", justifyContent: "flex-end" } },
          el("button", { class: "btn sm ghost", onclick: () => budgetModal(b) }, "Edit"),
          el("button", { class: "btn sm ghost", onclick: async () => {
            if (!(await confirmBox("Remove budget?", `Stop tracking a budget for ${b.category}?`, true))) return;
            try { await api("/api/budgets/" + encodeURIComponent(b.category), { method: "DELETE" }); window.Flux.refresh(); } catch (e) { err(e); }
          } }, "Remove"))));

      const summary = budgets.length ? el("div", { class: "card" }, el("div", { class: "row between wrap" },
        el("div", null, el("div", { class: "muted small" }, "Total budgeted this month"), el("div", { class: "stat" }, el("div", { class: "value" }, `${inr0(spent)} / ${inr0(total)}`))),
        el("div", { class: "muted small" }, `${daysLeft} days left in the month`)),
        el("div", { class: "bar " + (spent > total ? "over" : "ok"), style: { marginTop: "12px" } }, el("i", { style: { width: Math.min(100, (spent / (total || 1)) * 100) + "%" } }))) : null;

      const suggest = unbudgeted.length ? el("div", { class: "card" }, el("h2", null, "Spending without a budget"),
        el("p", { class: "small muted", style: { margin: "6px 0 12px" } }, "Tap to set a budget for these categories."),
        el("div", { class: "chips" }, unbudgeted.map((c) => el("button", { class: "chip", onclick: () => budgetModal({ category: c.category, limit: Math.ceil(c.amount / 500) * 500 }).then(() => {}) }, `${c.category} · ${inr0(c.amount)}`)))) : null;

      box.replaceChildren(...[summary,
        budgets.length ? el("div", { class: "grid g-3" }, cards) : el("div", { class: "card empty" }, el("b", null, "No budgets yet"),
          'Budgets are the easiest way to stop overspending. Say "set food budget to 4000" or tap New budget.'),
        suggest].filter(Boolean));
    }
    onRefresh(load);
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
