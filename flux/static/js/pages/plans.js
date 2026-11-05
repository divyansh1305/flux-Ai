/* Plans: money you expect to spend or receive, plus the three answers that shape "safe to spend". */
(function () {
  const { el, icon, api, ok, err, inr0, pageHead, planModal, confirmBox, onRefresh, avatar, dateFmt } = window.Kitna;

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
      el("div", { style: { height: "14px" } }),
      el("div", { class: "form" },
        el("div", { class: "field" }, el("span", null, "When does your money come in?"), seg,
          el("div", { class: "tiny faint" }, pattern === "varies" ? "" : "Salary, stipend or money from home.")),
        dayRow,
        el("label", { class: "field" }, "About how much? (₹)", expected),
        el("div", { class: "field" }, el("span", null, "Safety cushion (₹)"), cushion, cushionPick,
          el("div", { class: "tiny faint" }, "Money Kitna never counts as spendable. For emergencies.")),
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
    const sub = p.kind === "income" ? (p.sure ? "Coming in" : "Maybe, not counted") : "Kept aside";
    const doneBtn = el("button", { class: "done-btn", title: "Mark done", "aria-label": "Mark " + p.title + " done", onclick: async (e) => {
      e.stopPropagation();
      row.style.opacity = "0.5";  // instant feedback; the list refreshes once the server confirms
      try { await api(`/api/plans/${p.id}`, { method: "PATCH", body: { done: true } }); ok("Marked done."); window.Kitna.refresh(); } catch (ex) { row.style.opacity = ""; err(ex); }
    } }, icon("check"));
    const delBtn = el("button", { class: "icon-btn", title: "Delete", "aria-label": "Delete " + p.title, onclick: async () => {
      if (!(await confirmBox("Delete plan?", `${p.title} · ${inr0(p.amount)}`, true))) return;
      row.remove();
      try { await api(`/api/plans/${p.id}`, { method: "DELETE" }); window.Kitna.refresh(); } catch (e) { err(e); window.Kitna.refresh(); }
    } }, icon("trash"));
    const row = el("div", { class: "tx", style: past || p.done ? { opacity: 0.6 } : null },
      avatar(p.title),
      el("div", editable ? { class: "tx-main tx-edit", role: "button", tabindex: "0", title: "Edit", onclick: () => planModal(p),
        onkeydown: (e) => { if (e.key === "Enter") planModal(p); } } : { class: "tx-main" },
        el("div", { class: "tx-title" }, p.title), el("div", { class: "tx-sub" }, `${p.done ? "Done" : sub} · ${dateFmt(p.date)}`)),
      el("div", { class: "tx-amt" + (p.kind === "income" ? " green" : "") }, (p.kind === "income" ? "+" : "") + inr0(p.amount)),
      editable ? doneBtn : delBtn);
    return row;
  }

  let early = api("/api/plans", { allow401: true }).catch(() => null);

  async function render(main) {
    const box = el("div", { class: "stack narrow" }, window.Kitna.skeleton(2));
    main.replaceChildren(pageHead("Plans", "What's coming, so today's number is real. Tap a plan to edit it.",
      el("button", { class: "btn primary", onclick: () => planModal() }, icon("plus"), "Add")), box);
    let me = { user: window.Kitna.user };
    let lastPlans = null;
    const load = async () => {
      const pre = early;
      early = null;
      const meNow = api("/api/auth/me").then((m) => { me = m; }).catch(() => {});
      await window.Kitna.live("/api/plans", (plans) => { lastPlans = plans; draw(plans); }, pre);
      await meNow;
      if (lastPlans) draw(lastPlans);  // money setup shows what was just saved
    };
    const draw = (plans) => {
      const today = window.Kitna.todayISO();
      const open = plans.filter((p) => !p.done && p.date >= today);
      const old = plans.filter((p) => p.done || p.date < today);
      const list = el("div", { class: "card", style: { padding: "4px 20px" } }, open.length
        ? el("div", { class: "tx-list" }, open.map((p) => planRow(p, false)))
        : el("div", { class: "empty" }, el("b", null, "No plans yet"),
            "Dinner on Friday? Rent on the 5th? Add it, and Kitna keeps the money aside."));
      box.replaceChildren(...[
        el("section", null, el("div", { class: "section-title" }, el("span", null, "Coming up")), list),
        old.length ? el("section", null, el("div", { class: "section-title" }, el("span", null, "Past and done")),
          el("div", { class: "card", style: { padding: "4px 20px" } }, el("div", { class: "tx-list" }, old.map((p) => planRow(p, true))))) : null,
        moneyCard(me.user, load)].filter(Boolean));
      if (location.hash === "#money") setTimeout(() => { const m = document.getElementById("money"); if (m) m.scrollIntoView({ behavior: "smooth" }); }, 50);
    };
    onRefresh(load);
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
