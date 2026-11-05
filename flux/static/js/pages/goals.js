(function () {
  const { el, icon, api, ok, err, modal, confirmBox, inr, inr0, pageHead, onRefresh } = window.Kitna;

  async function goalModal() {
    const title = el("input", { class: "input", maxlength: "60", required: true, placeholder: "e.g. New laptop" });
    const target = el("input", { class: "input big num", type: "number", min: "1", step: "1", required: true, placeholder: "60000" });
    const deadline = el("input", { class: "input", type: "date" });
    const v = await modal("New goal", el("div", { class: "form" },
      el("label", { class: "field" }, "What are you saving for?", title),
      el("label", { class: "field" }, "Target (₹)", target),
      el("label", { class: "field" }, "Target date (optional)", deadline)),
      [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Create goal", submit: true, cls: "primary", value: () => ({ title: title.value, target: target.value, deadline: deadline.value || null }) }]);
    if (!v) return;
    try { const g = await api("/api/goals", { method: "POST", body: v }); ok(`Goal created: ${g.title}.`); window.Kitna.refresh(); } catch (e) { err(e); }
  }

  async function moveModal(g, withdraw) {
    const amount = el("input", { class: "input big num", type: "number", min: "1", step: "0.01", required: true, placeholder: "500" });
    const v = await modal(withdraw ? `Withdraw from ${g.title}` : `Add to ${g.title}`, el("div", { class: "form" },
      el("label", { class: "field" }, "Amount (₹)", amount),
      el("p", { class: "tiny faint" }, withdraw ? `This goal holds ${inr(g.saved)}. Withdrawn money goes back to your balance.` : "Money moves from your balance into this goal.")),
      [{ label: "Cancel", value: null, cls: "ghost" }, { label: withdraw ? "Withdraw" : "Add money", submit: true, cls: "primary", value: () => amount.value }]);
    if (!v) return;
    try {
      const r = await api(`/api/goals/${g.id}/contribute`, { method: "POST", body: { amount: v, withdraw } });
      ok(`${r.goal.title}: now ${r.goal.percent}% complete.`);
      window.Kitna.refresh();
    } catch (e) { err(e); }
  }

  function eta(g) {
    if (g.complete) return "Goal reached";
    if (!g.deadline) return `${inr0(g.remaining)} to go`;
    const days = Math.ceil((new Date(g.deadline + "T00:00:00") - new Date()) / 86400000);
    if (days <= 0) return `Target date passed · ${inr0(g.remaining)} to go`;
    const perMonth = g.remaining / Math.max(days / 30, 1 / 30);
    return `${inr0(g.remaining)} to go · ${inr0(Math.min(perMonth, g.remaining))}/month for ${days} days`;
  }

  async function render(main, user) {
    const box = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Goals", "Track what you're saving for. Money you set aside stays in your bank; Kitna just stops counting it as spendable.",
      el("button", { class: "btn primary", onclick: goalModal }, icon("plus"), "New goal")), box);

    async function load() { await window.Kitna.live("/api/goals", (goals) => paint(goals, window.Kitna.user)); }
    function paint(goals, u) {
      const autoGoal = goals.find((g) => g.id === u.autosave_goal_id);
      const modeText = u.autosave_mode === "off" ? "Automatic set-aside is off."
        : u.autosave_mode === "roundup" ? `Every expense rounds up to the next ₹${u.autosave_value}` : `${u.autosave_value}% of every expense`;
      const auto = el("div", { class: "notice info" }, icon("repeat"),
        el("div", null, u.autosave_mode === "off" ? modeText : `${modeText}, and Kitna sets the difference aside for `, u.autosave_mode !== "off" ? el("b", null, autoGoal ? autoGoal.title : "no goal yet") : null,
          ". ", el("a", { class: "brand", href: "/app/settings" }, "Change")));
      const cards = goals.map((g) => el("div", { class: "card" },
        el("div", { class: "row between" }, el("h3", null, g.title), g.id === u.autosave_goal_id ? el("span", { class: "badge autosave" }, "set-aside") : null),
        el("div", { class: "row between", style: { margin: "16px 0 8px", alignItems: "flex-end" } },
          el("div", null, el("div", { class: "stat" }, el("div", { class: "value", style: { fontSize: "24px" } }, inr0(g.saved))), el("div", { class: "tiny faint" }, "of " + inr0(g.target))),
          el("div", { style: { fontSize: "22px", fontWeight: 800 }, class: g.complete ? "green" : "" }, g.percent + "%")),
        el("div", { class: "bar ok" }, el("i", { style: { width: g.percent + "%" } })),
        el("div", { class: "tiny muted", style: { marginTop: "8px" } }, eta(g)),
        el("div", { class: "row wrap", style: { marginTop: "14px" } },
          el("button", { class: "btn sm primary", onclick: () => moveModal(g, false) }, "Add money"),
          g.saved > 0 ? el("button", { class: "btn sm", onclick: () => moveModal(g, true) }, "Withdraw") : null,
          g.id !== u.autosave_goal_id ? el("button", { class: "btn sm ghost", onclick: async () => {
            try { await api("/api/account", { method: "PATCH", body: { autosave_goal_id: g.id } }); ok(`Set-asides now go to ${g.title}.`); window.Kitna.user = { ...window.Kitna.user, autosave_goal_id: g.id }; load(); } catch (e) { err(e); }
          } }, "Set aside here") : null,
          el("button", { class: "btn sm ghost", onclick: async () => {
            if (!(await confirmBox("Delete goal?", `${g.title} holds ${inr(g.saved)}. Deleting it returns that money to your balance.`, true))) return;
            try { await api(`/api/goals/${g.id}`, { method: "DELETE" }); ok("Goal deleted."); window.Kitna.refresh(); } catch (e) { err(e); }
          } }, "Delete"))));
      box.replaceChildren(auto, goals.length ? el("div", { class: "grid g-3" }, cards)
        : el("div", { class: "card empty" }, el("b", null, "No goals yet"), 'Create one, or say "create a goal laptop for 60000".'));
    }
    onRefresh(load);
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
