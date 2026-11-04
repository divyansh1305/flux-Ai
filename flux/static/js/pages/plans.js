/* Plans: money you expect to spend or receive, plus the three answers that shape "safe to spend". */
(function () {
  const { el, icon, api, ok, err, inr0, pageHead, planModal, confirmBox, onRefresh, avatar, dateFmt } = window.Flux;

  function moneyCard(u, onSaved) {
    let pattern = u.income_pattern === "unset" ? "monthly" : u.income_pattern;
    const payDay = el("input", { class: "input num", type: "number", min: "1", max: "31", value: u.pay_day || 1, "aria-label": "Day of the month" });
    const expected = el("input", { class: "input num", type: "number", min: "0", placeholder: "Optional", value: u.expected_income || "" });
    const cushion = el("input", { class: "input num", type: "number", min: "0", value: u.cushion || 0 });
    const dayRow = el("label", { class: "field" }, "Which date?", payDay);
    const seg = el("div", { class: "seg" });
    const bM = el("button", { type: "button" }, "Same date every month");
    const bV = el("button", { type: "button" }, "It varies");
    const paint = () => { bM.className = pattern === "monthly" ? "on" : ""; bV.className = pattern === "varies" ? "on" : ""; dayRow.style.display = pattern === "monthly" ? "" : "none"; };
    bM.onclick = () => { pattern = "monthly"; paint(); };
    bV.onclick = () => { pattern = "varies"; paint(); };
    seg.append(bM, bV);
    paint();
    const cushionPick = el("div", { class: "chips" }, [0, 500, 1000, 2000].map((v) => el("button", { type: "button", class: "chip", onclick: () => { cushion.value = v; } }, v ? inr0(v) : "None")));
    return el("div", { class: "card", id: "money" },
      el("h2", null, "Your money setup"),
      el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "Three answers make today's number fit your life. Change them any time."),
      el("div", { class: "form" },
        el("div", { class: "field" }, el("span", null, "When does your money come in?"), seg,
          el("div", { class: "tiny faint" }, pattern === "varies" ? "" : "Salary, stipend or money from home.")),
        dayRow,
        el("label", { class: "field" }, "About how much? (₹)", expected),
        el("div", { class: "field" }, el("span", null, "Safety cushion (₹)"), cushion, cushionPick,
          el("div", { class: "tiny faint" }, "Money Flux never counts as spendable. For emergencies.")),
        el("div", null, el("button", { class: "btn primary", onclick: async () => {
          try {
            const body = { income_pattern: pattern, expected_income: Number(expected.value) || 0, cushion: Number(cushion.value) || 0 };
            if (pattern === "monthly") body.pay_day = Number(payDay.value);
            await api("/api/account", { method: "PATCH", body });
            ok("Saved. Today's number is updated.");
            onSaved();
          } catch (e) { err(e); }
        } }, "Save"))));
  }

  function planRow(p, past) {
    const editable = !p.done && !past;
    const title = el("div", { class: "tx-title", style: editable ? { cursor: "pointer" } : null, title: editable ? "Edit" : null,
      onclick: editable ? () => planModal(p) : null }, p.title);
    const sub = p.kind === "income" ? (p.sure ? "Coming in" : "Maybe (not counted)") : "Kept aside";
    return el("div", { class: "tx", style: past || p.done ? { opacity: 0.6 } : null }, avatar(p.title),
      el("div", { class: "tx-main" }, title, el("div", { class: "tx-sub" }, `${p.done ? "Done" : sub} · ${dateFmt(p.date)}`)),
      el("div", { class: "tx-amt" + (p.kind === "income" ? " green" : "") }, (p.kind === "income" ? "+" : "") + inr0(p.amount)),
      el("div", { class: "row", style: { gap: "2px" } },
        !p.done ? el("button", { class: "icon-btn", title: "Mark done", "aria-label": "Mark done", onclick: async () => {
          try { await api(`/api/plans/${p.id}`, { method: "PATCH", body: { done: true } }); ok("Marked done."); window.Flux.refresh(); } catch (e) { err(e); }
        } }, icon("check")) : null,
        el("button", { class: "icon-btn", title: "Delete", "aria-label": "Delete plan", onclick: async () => {
          if (!(await confirmBox("Delete plan?", `${p.title} · ${inr0(p.amount)}`, true))) return;
          try { await api(`/api/plans/${p.id}`, { method: "DELETE" }); window.Flux.refresh(); } catch (e) { err(e); }
        } }, icon("trash"))));
  }

  async function render(main) {
    const box = el("div", { class: "stack narrow" });
    main.replaceChildren(pageHead("Plans", "Tell Flux what's coming, so today's number is real. Tap a plan to edit it.",
      el("button", { class: "btn primary", onclick: () => planModal() }, icon("plus"), "Add a plan")), box);
    const load = async () => {
      const [plans, me] = await Promise.all([api("/api/plans"), api("/api/auth/me")]);
      const today = window.Flux.todayISO();
      const open = plans.filter((p) => !p.done && p.date >= today);
      const old = plans.filter((p) => p.done || p.date < today);
      const list = el("div", { class: "card", style: { padding: "4px 20px" } }, open.length
        ? el("div", { class: "tx-list" }, open.map((p) => planRow(p, false)))
        : el("div", { class: "empty" }, el("b", null, "No plans yet"),
            "Add things like \"Dinner Friday ₹2,000\" or \"Client pays ₹15,000 on the 20th\". Plans aren't payments: nothing leaves your bank."));
      box.replaceChildren(...[
        el("section", null, el("div", { class: "section-title" }, el("span", null, "Coming up")), list),
        old.length ? el("section", null, el("div", { class: "section-title" }, el("span", null, "Past and done")),
          el("div", { class: "card", style: { padding: "4px 20px" } }, el("div", { class: "tx-list" }, old.map((p) => planRow(p, true))))) : null,
        moneyCard(me.user, load)].filter(Boolean));
      if (location.hash === "#money") setTimeout(() => document.getElementById("money").scrollIntoView({ behavior: "smooth" }), 50);
    };
    onRefresh(load);
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
