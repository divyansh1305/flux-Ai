(function () {
  const { el, icon, api, err, inr } = window.Flux;

  async function render(main, user) {
    let step = 0;
    const data = { income: "", incomeCat: "Salary", goalTitle: "", goalTarget: "", mode: "roundup", value: 10 };
    const wrap = el("div", { style: { maxWidth: "520px", margin: "6vh auto 0" } });
    main.style.marginLeft = "0";
    main.appendChild(wrap);

    const steps = () => el("div", { class: "steps" }, [0, 1, 2, 3].map((i) => el("i", { class: i <= step ? "on" : "" })));
    const nav = (canSkip, next) => el("div", { class: "row between", style: { marginTop: "24px" } },
      step > 0 ? el("button", { class: "btn ghost", onclick: () => { step--; draw(); } }, "Back") : el("span"),
      el("div", { class: "row" }, canSkip ? el("button", { class: "btn ghost", onclick: () => { step++; draw(); } }, "Skip") : null,
        el("button", { class: "btn primary", onclick: next }, step === 3 ? "Go to dashboard" : "Continue")));

    function draw() {
      const card = el("div", { class: "card", style: { padding: "32px" } }, steps());
      if (step === 0) {
        const amt = el("input", { class: "input big num", type: "number", min: "1", placeholder: "25000", value: data.income });
        const cat = el("select", { class: "input" }, ["Salary", "Pocket Money", "Freelance", "Other Income"].map((c) => el("option", { value: c, selected: data.incomeCat === c ? true : null }, c)));
        card.append(el("div", { class: "feature" }, el("div", { class: "ico" }, icon("wave"))),
          el("h1", { style: { margin: "8px 0" } }, `Welcome to Flux, ${user.name.split(" ")[0]}!`),
          el("p", { class: "muted" }, "Let's set you up in under a minute. How much money comes in each month?"),
          el("div", { class: "form", style: { marginTop: "20px" } }, el("label", { class: "field" }, "Monthly income (₹)", amt), el("label", { class: "field" }, "Mostly from", cat)),
          nav(true, () => { data.income = amt.value; data.incomeCat = cat.value; step++; draw(); }));
      } else if (step === 1) {
        const title = el("input", { class: "input", maxlength: "60", placeholder: "New laptop, Goa trip, Emergency fund…", value: data.goalTitle });
        const target = el("input", { class: "input big num", type: "number", min: "1", placeholder: "50000", value: data.goalTarget });
        card.append(el("div", { class: "feature" }, el("div", { class: "ico" }, icon("target"))), el("h1", { style: { margin: "8px 0" } }, "What are you saving for?"),
          el("p", { class: "muted" }, "Goals give your savings a purpose. You can add more later."),
          el("div", { class: "chips", style: { marginTop: "16px" } }, ["Emergency fund", "New phone", "Trip", "Laptop"].map((g) => el("button", { class: "chip", onclick: () => { title.value = g; } }, g))),
          el("div", { class: "form", style: { marginTop: "16px" } }, el("label", { class: "field" }, "Goal", title), el("label", { class: "field" }, "Target (₹)", target)),
          nav(true, () => { data.goalTitle = title.value.trim(); data.goalTarget = target.value; step++; draw(); }));
      } else if (step === 2) {
        const opts = [["roundup", 10, "Round up to ₹10", "₹47 → save ₹3. Gentle, barely noticeable."],
          ["roundup", 100, "Round up to ₹100", "₹470 → save ₹30. Faster saving."],
          ["percent", 5, "Save 5% of every expense", "₹400 → save ₹20. The anti-cashback."],
          ["off", 10, "No auto-save", "I'll move money to goals myself."]];
        const list = el("div", { class: "stack", style: { gap: "10px", marginTop: "18px" } });
        const paint = () => list.replaceChildren(...opts.map(([m, v, t, d]) => el("button", {
          class: "card", style: { textAlign: "left", cursor: "pointer", borderColor: data.mode === m && (m === "off" || data.value === v) ? "var(--brand)" : null, padding: "14px 16px" },
          onclick: () => { data.mode = m; data.value = v; paint(); } }, el("b", null, t), el("div", { class: "small muted" }, d))));
        paint();
        card.append(el("div", { class: "feature" }, el("div", { class: "ico" }, icon("repeat"))), el("h1", { style: { margin: "8px 0" } }, "Save automatically as you spend"),
          el("p", { class: "muted" }, "Instead of cashback that makes you spend more, Flux moves a little of every expense into your goal, only when you have the balance."),
          list, nav(false, () => { step++; draw(); }));
      } else {
        const V = window.FluxVoice;
        card.append(el("div", { class: "feature" }, el("div", { class: "ico" }, icon("mic"))), el("h1", { style: { margin: "8px 0" } }, "Just talk to Flux"),
          el("p", { class: "muted" }, "Tap the mic button (or press Ctrl/⌘+K) on any page and say things like:"),
          el("div", { class: "stack", style: { gap: "8px", marginTop: "16px" } },
            ["“Spent 250 on Swiggy”", "“What's my balance?”", "“Can I afford 3000 shoes?”", "“Maine 200 chai pe kharch kiye”"].map((t) => el("div", { class: "bubble me", style: { marginLeft: 0 } }, t))),
          V && !V.supported ? el("div", { class: "notice caution", style: { marginTop: "14px" } }, "Voice input needs Chrome, Edge or Safari. You can always type commands instead.") : null,
          nav(false, finish));
      }
      wrap.replaceChildren(card);
    }

    async function finish() {
      try {
        if (Number(data.income) > 0) await api("/api/transactions", { method: "POST", body: { kind: "income", amount: data.income, category: data.incomeCat, note: "Monthly income" } });
        let goalId = null;
        if (data.goalTitle && Number(data.goalTarget) > 0) goalId = (await api("/api/goals", { method: "POST", body: { title: data.goalTitle, target: data.goalTarget } })).id;
        const body = { onboarded: true, autosave_mode: data.mode };
        if (data.mode !== "off") body.autosave_value = data.value;
        if (goalId) body.autosave_goal_id = goalId;
        await api("/api/account", { method: "PATCH", body });
        location.href = "/app";
      } catch (e) { err(e); }
    }
    draw();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
