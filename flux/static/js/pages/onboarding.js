/* Setup in three screens: (1) 18+ and a promise, (2) when money comes in, (3) connect payments.
   It ends with real payments arriving (Gmail pulls the last 30 days) instead of an empty app. */
(function () {
  const { el, api, err } = window.Flux;

  async function render(main, user) {
    let step = 0;
    const data = { pattern: "monthly", payDay: 1, balance: "" };
    const wrap = el("div", { style: { maxWidth: "520px", margin: "6vh auto 0", padding: "0 16px" } });
    main.style.marginLeft = "0";
    main.appendChild(wrap);
    const isAndroid = /Android/.test(navigator.userAgent);
    const gmailOn = (window.Flux.config.features || {}).gmail;
    const apk = (window.Flux.config.features || {}).android_apk;

    const dots = () => el("div", { class: "steps" }, [0, 1, 2].map((i) => el("i", { class: i <= step ? "on" : "" })));
    const back = () => step > 0 ? el("button", { class: "btn ghost", type: "button", onclick: () => { step--; draw(); } }, "Back") : el("span");

    async function finish(next) {
      try {
        await api("/api/account", { method: "PATCH", body: { onboarded: true } });
        window.Flux.cacheClear();
        location.href = next;
      } catch (e) { err(e); }
    }

    function draw() {
      const card = el("div", { class: "card", style: { padding: "28px" } }, dots());
      if (step === 0) {
        const adult = el("input", { type: "checkbox", id: "adult" });
        const go = el("button", { class: "btn primary", type: "button", disabled: true, onclick: async () => {
          try { await api("/api/account", { method: "PATCH", body: { adult_confirmed: true } }); step = 1; draw(); } catch (e) { err(e); }
        } }, "Continue");
        adult.onchange = () => { go.disabled = !adult.checked; };
        card.append(
          el("h1", { style: { margin: "10px 0 6px" } }, `Hi ${user.name.split(" ")[0]}, welcome to Flux`),
          el("p", { class: "muted" }, "Flux tells you how much you can safely spend today, and logs your payments by itself."),
          el("ul", { class: "small", style: { margin: "16px 0", paddingLeft: "18px", lineHeight: 1.8 } },
            ["Never sells your data or shows ads", "Never offers loans", "Can't move your money or see your bank password"].map((t) => el("li", null, t))),
          el("label", { class: "row", style: { gap: "10px", alignItems: "center", margin: "8px 0 4px" } }, adult, el("span", null, "I'm 18 or older")),
          el("p", { class: "tiny faint" }, "Flux is only for adults, as India's data protection law requires for apps like this."),
          el("div", { class: "row between", style: { marginTop: "20px" } }, el("span"), go));
      } else if (step === 1) {
        const seg = el("div", { class: "seg" });
        const day = el("input", { class: "input num", type: "number", min: "1", max: "31", value: data.payDay, style: { maxWidth: "120px" }, "aria-label": "Date of the month" });
        const dayRow = el("label", { class: "field" }, "On which date?", day);
        const bal = el("input", { class: "input num", type: "number", inputmode: "decimal", placeholder: "Optional", value: data.balance, "aria-label": "Money in your bank now" });
        const opts = [["monthly", "Same date every month"], ["varies", "It varies"]];
        const paint = () => {
          seg.replaceChildren(...opts.map(([k, l]) => el("button", { type: "button", class: data.pattern === k ? "on" : "", onclick: () => { data.pattern = k; paint(); } }, l)));
          dayRow.style.display = data.pattern === "monthly" ? "" : "none";
        };
        paint();
        card.append(
          el("h1", { style: { margin: "10px 0 6px" } }, "When does your money come in?"),
          el("p", { class: "muted" }, "Salary, stipend or money from home. Flux makes today's number last until then."),
          el("div", { class: "form", style: { marginTop: "16px" } }, seg, dayRow,
            el("label", { class: "field" }, "About how much is in your bank right now? (₹)", bal),
            el("p", { class: "tiny faint" }, "So the number is useful today. Flux matches it with your bank later.")),
          el("div", { class: "row between", style: { marginTop: "20px" } }, back(),
            el("div", { class: "row" },
              el("button", { class: "btn ghost", type: "button", onclick: () => { step = 2; draw(); } }, "Skip"),
              el("button", { class: "btn primary", type: "button", onclick: async () => {
                data.payDay = Number(day.value) || 1; data.balance = bal.value;
                const body = { income_pattern: data.pattern };
                if (data.pattern === "monthly") body.pay_day = Math.min(31, Math.max(1, data.payDay));
                if (data.balance !== "") body.current_balance = data.balance;
                try { await api("/api/account", { method: "PATCH", body }); step = 2; draw(); } catch (e) { err(e); }
              } }, "Continue"))));
      } else {
        const options = [];
        if (gmailOn) {
          options.push(el("div", { class: "card", style: { padding: "16px", borderColor: isAndroid ? null : "var(--brand)" } },
            el("b", null, isAndroid ? "Connect Gmail" : "Connect Gmail (recommended)"),
            el("p", { class: "small muted", style: { margin: "6px 0 12px" } }, "Your bank emails you after every payment. Flux reads only those bank emails, never personal mail, and can't send or delete anything. It also brings in the last 30 days at once."),
            el("button", { class: "btn primary", type: "button", onclick: () => finish("/gmail/connect") }, "Connect Gmail"),
            el("p", { class: "tiny faint", style: { marginTop: "8px" } }, "Google may say \"Google hasn't verified this app\" because Flux is new. Tap Advanced → Continue.")));
        }
        if (isAndroid && apk) {
          options.unshift(el("div", { class: "card", style: { padding: "16px", borderColor: "var(--brand)" } },
            el("b", null, "Get the Flux app (recommended on Android)"),
            el("p", { class: "small muted", style: { margin: "6px 0 12px" } }, "Logs every GPay, PhonePe, Paytm and bank payment by itself. Reads only payment notifications, never chats or OTPs."),
            el("button", { class: "btn primary", type: "button", onclick: () => finish("/app/settings#auto") }, "Set it up")));
        }
        card.append(
          el("h1", { style: { margin: "10px 0 6px" } }, "See your payments automatically"),
          el("p", { class: "muted" }, options.length > 1 ? "Pick one. You can add the other later in Settings." : "You can change this later in Settings."),
          el("div", { class: "stack", style: { gap: "12px", marginTop: "16px" } }, ...options,
            el("button", { class: "btn ghost", type: "button", onclick: () => finish("/app") }, "I'll add payments myself for now")),
          el("div", { class: "row between", style: { marginTop: "16px" } }, back(), el("span")));
      }
      wrap.replaceChildren(card);
    }
    if (user.adult_confirmed) step = 1;
    draw();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
