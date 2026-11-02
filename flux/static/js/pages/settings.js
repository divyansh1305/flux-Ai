(function () {
  const { el, icon, api, download, ok, err, modal, pageHead, logout } = window.Flux;

  async function render(main) {
    const [me, goals] = await Promise.all([api("/api/auth/me"), api("/api/goals")]);
    let u = me.user;
    const save = async (body, msg) => {
      try { u = (await api("/api/account", { method: "PATCH", body })).user; ok(msg || "Saved."); } catch (e) { err(e); }
    };

    // Profile
    const name = el("input", { class: "input", value: u.name, maxlength: "60" });
    const profile = el("div", { class: "card" }, el("h2", null, "Profile"),
      el("div", { class: "form", style: { marginTop: "14px" } },
        el("label", { class: "field" }, "Name", name),
        el("label", { class: "field" }, "Email", el("input", { class: "input", value: u.email, disabled: true })),
        el("div", null, el("button", { class: "btn primary", onclick: () => save({ name: name.value }, "Name updated.") }, "Save"))));

    // Auto-save
    const mode = el("select", { class: "input" },
      [["roundup", "Round up each expense"], ["percent", "Save a % of each expense"], ["off", "Off"]].map(([v, l]) => el("option", { value: v, selected: u.autosave_mode === v ? true : null }, l)));
    const value = el("select", { class: "input" });
    const fillValues = () => {
      const opts = mode.value === "roundup" ? [[10, "to the next ₹10"], [50, "to the next ₹50"], [100, "to the next ₹100"]]
        : mode.value === "percent" ? [1, 2, 3, 5, 10, 15, 20].map((p) => [p, p + "%"]) : [];
      value.replaceChildren(...opts.map(([v, l]) => el("option", { value: v, selected: u.autosave_value === v ? true : null }, l)));
      value.disabled = mode.value === "off";
      describe();
    };
    const describe = () => {
      const v = Number(value.value) || 0;
      if (mode.value === "roundup") {
        const up = Math.ceil(47 / v) * v;
        example.textContent = `Example: a ₹47 expense rounds up to ₹${up}, so ₹${up - 47} goes to your goal.`;
      } else if (mode.value === "percent") {
        example.textContent = `Example: a ₹400 expense sends ₹${(400 * v) / 100} to your goal.`;
      } else example.textContent = "Nothing is saved automatically.";
    };
    const example = el("p", { class: "tiny faint" });
    mode.onchange = fillValues;
    value.onchange = describe;
    const goalSel = el("select", { class: "input" }, el("option", { value: "" }, goals.length ? "Choose a goal" : "Create a goal first"),
      goals.map((g) => el("option", { value: g.id, selected: u.autosave_goal_id === g.id ? true : null }, g.title)));
    fillValues();
    const autosave = el("div", { class: "card" }, el("h2", null, "Auto-save"),
      el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "Flux's anti-cashback: a little from every expense moves into your goal, but only if you have the balance."),
      el("div", { class: "form" },
        el("label", { class: "field" }, "Mode", mode),
        el("label", { class: "field" }, "Amount", value), example,
        el("label", { class: "field" }, "Send it to", goalSel),
        el("div", null, el("button", { class: "btn primary", onclick: () => {
          const body = { autosave_mode: mode.value, autosave_goal_id: goalSel.value ? Number(goalSel.value) : null };
          if (mode.value !== "off") body.autosave_value = Number(value.value);
          save(body, "Auto-save updated.");
        } }, "Save"))));

    // Voice
    const V = window.FluxVoice;
    const langSel = el("select", { class: "input" }, [["en-IN", "English (India)"], ["hi-IN", "हिंदी / Hinglish"]].map(([v, l]) => el("option", { value: v, selected: u.voice_lang === v ? true : null }, l)));
    langSel.onchange = () => save({ voice_lang: langSel.value }, "Voice language updated. Reload to apply.");
    const wake = el("input", { type: "checkbox", checked: V && V.wakeOn ? true : null, disabled: V && V.supported ? null : true });
    wake.onchange = () => { V.setWake(wake.checked); ok(wake.checked ? 'Say "Hey Flux" any time while Flux is open.' : "Wake word off."); };
    const voiceCard = el("div", { class: "card" }, el("h2", null, "Voice assistant"),
      el("div", { class: "form", style: { marginTop: "14px" } },
        el("label", { class: "field" }, "Language I'll speak", langSel),
        el("label", { class: "row small", style: { cursor: "pointer" } }, wake, el("span", null, el("b", null, '"Hey Flux" wake word'), el("br"),
          el("span", { class: "muted" }, "Listens for “Hey Flux” while this tab is open. Audio is processed by your browser's speech service; Flux only receives the text."))),
        !(V && V.supported) ? el("div", { class: "notice caution" }, "Your browser doesn't support voice input. Use Chrome, Edge or Safari. Typing commands still works.") : null,
        el("div", null, el("button", { class: "btn", onclick: () => V && V.open(true) }, icon("mic"), "Try it now"))));

    // Data & privacy
    const data = el("div", { class: "card" }, el("h2", null, "Your data"),
      el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "You own your data. Download everything, or delete your account permanently."),
      el("div", { class: "row wrap" },
        el("button", { class: "btn", onclick: () => download("/api/account/export", "flux-my-data.json").catch(err) }, icon("download"), "Download my data"),
        el("button", { class: "btn", onclick: logout }, icon("out"), "Sign out"),
        el("button", { class: "btn danger", onclick: async () => {
          const input = el("input", { class: "input", placeholder: "Type DELETE" });
          const v = await modal("Delete account?", el("div", { class: "form" },
            el("p", { class: "muted small" }, "This permanently deletes your account, transactions, budgets and goals. It cannot be undone."), input),
            [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Delete forever", submit: true, cls: "danger", value: () => input.value }]);
          if (v === null) return;
          try { await api("/api/account", { method: "DELETE", body: { confirm: v } }); location.href = "/"; } catch (e) { err(e); }
        } }, icon("trash"), "Delete account")));

    // Automatic tracking (iPhone Shortcuts / Android SMS forwarders)
    const autoBox = el("div", { class: "stack", style: { gap: "12px" } });
    const steps = (url, token) => el("ol", { class: "small", style: { paddingLeft: "20px", margin: 0, lineHeight: 1.85, color: "var(--muted)" } },
      el("li", null, "Open the ", el("b", null, "Shortcuts"), " app → ", el("b", null, "Automation"), " → ", el("b", null, "+"), " → ", el("b", null, "Message"), "."),
      el("li", null, "Message Contains: ", el("b", null, "debited"), ". Sender: any. Choose ", el("b", null, "Run Immediately"), "."),
      el("li", null, "Tap ", el("b", null, "New Blank Automation"), " → add action ", el("b", null, "Get Contents of URL"), "."),
      el("li", null, "URL: ", el("code", { class: "tiny", style: { wordBreak: "break-all", color: "var(--text)" } }, url)),
      el("li", null, "Method ", el("b", null, "POST"), ". Header ", el("b", null, "Authorization"), " = ",
        el("code", { class: "tiny", style: { wordBreak: "break-all", color: "var(--text)" } }, "Bearer " + (token || "<your token>"))),
      el("li", null, "Request Body ", el("b", null, "JSON"), ": key ", el("b", null, "text"), " → value ", el("b", null, "Shortcut Input › Content"), "."),
      el("li", null, "Optional: add ", el("b", null, "Show Notification"), " with ", el("b", null, "Contents of URL › message"), " to see what Flux logged."),
      el("li", null, "Repeat for messages containing ", el("b", null, "Sent Rs"), " (HDFC style) and ", el("b", null, "credited"), " (income)."));
    async function drawAuto(fresh) {
      const st = await api("/api/ingest/token");
      const url = location.origin + "/api/ingest/sms";
      const kids = [el("p", { class: "small muted" }, "Log bank SMS automatically, without opening Flux. On iPhone, a Shortcuts automation forwards each debit/credit SMS to your private Flux link. Flux ignores OTPs and offers, skips duplicates, and won't double-count payments you made through Scan & Pay.")];
      if (fresh) {
        const copyBtn = el("button", { class: "btn sm", onclick: () => navigator.clipboard && navigator.clipboard.writeText(fresh.token).then(() => ok("Token copied.")) }, "Copy token");
        kids.push(el("div", { class: "notice caution" }, el("div", null, el("b", null, "Your token (shown once): "),
          el("code", { style: { wordBreak: "break-all", color: "var(--text)" } }, fresh.token), el("div", { style: { marginTop: "8px" } }, copyBtn))));
      }
      if (st.active || fresh) {
        kids.push(el("div", { class: "tiny", style: { fontWeight: 700, letterSpacing: ".04em", color: "var(--muted)" } }, "ANDROID · FLUX COMPANION APP"));
        kids.push(el("p", { class: "small muted", style: { margin: 0 } }, "Install Flux Companion, tick consent, paste ", el("b", null, location.origin), " and your token, then turn on Notification access. Every GPay, PhonePe, Paytm and bank payment gets logged on its own."));
        kids.push(el("div", { class: "tiny", style: { fontWeight: 700, letterSpacing: ".04em", color: "var(--muted)", marginTop: "6px" } }, "IPHONE · SHORTCUTS AUTOMATION"));
        kids.push(steps(url, fresh && fresh.token));
        kids.push(el("div", { class: "tiny faint" }, st.uses ? `Used ${st.uses} time(s), last ${st.last_used_at} UTC.` : "Not used yet."));
        kids.push(el("div", { class: "row wrap" },
          el("button", { class: "btn sm", onclick: async () => drawAuto(await api("/api/ingest/token", { method: "POST" })) }, "New token"),
          el("button", { class: "btn sm danger", onclick: async () => { await api("/api/ingest/token", { method: "DELETE" }); ok("Automatic tracking turned off."); drawAuto(); } }, "Turn off")));
      } else {
        kids.push(el("div", null, el("button", { class: "btn primary", onclick: async () => drawAuto(await api("/api/ingest/token", { method: "POST" })) }, "Set up automatic tracking")));
      }
      if (/localhost|127\.0\.0\.1/.test(location.hostname)) kids.push(el("div", { class: "notice info" }, "Your phone can't reach localhost. Deploy Flux (e.g. on Render) and set this up from the live site."));
      autoBox.replaceChildren(...kids);
    }
    const autoCard = el("div", { class: "card", style: { gridColumn: "1 / -1" } }, el("h2", null, "⚡ Automatic tracking (Android app + iPhone)"), el("div", { style: { marginTop: "12px" } }, autoBox));
    drawAuto().catch(err);

    // Learned merchant rules + opt-in accuracy samples
    const rulesBox = el("div", { class: "stack", style: { gap: "8px" } });
    async function drawRules() {
      const rules = await api("/api/rules");
      rulesBox.replaceChildren(...(rules.length ? rules.map((r) => el("div", { class: "row", style: { justifyContent: "space-between" } },
        el("span", { class: "small" }, el("b", null, r.merchant_key), " → ", r.category),
        el("button", { class: "btn sm ghost", onclick: async () => { await api(`/api/rules/${r.id}`, { method: "DELETE" }); ok("Rule removed."); drawRules(); } }, "Remove")))
        : [el("p", { class: "small muted", style: { margin: 0 } }, "None yet. Tap a transaction, fix its category and tick “Always use this category”.")]));
    }
    const contrib = el("input", { type: "checkbox", checked: !!u.contribute_samples });
    contrib.onchange = async () => {
      try {
        await api("/api/account", { method: "PATCH", body: { contribute_samples: contrib.checked } });
        ok(contrib.checked ? "Thanks! Masked copies of new auto-logged messages will be kept for you to export." : "Turned off. Saved samples deleted.");
      } catch (e) { err(e); }
    };
    const learnCard = el("div", { class: "card", style: { gridColumn: "1 / -1" } }, el("h2", null, "🧠 What Flux has learned"),
      el("div", { style: { marginTop: "12px" } }, rulesBox),
      el("hr", { style: { border: 0, borderTop: "1px solid var(--line)", margin: "16px 0" } }),
      el("label", { class: "row", style: { gap: "10px", alignItems: "flex-start" } }, contrib,
        el("span", { class: "small" }, el("b", null, "Help improve accuracy (optional). "),
          el("span", { class: "muted" }, "Keep a masked copy of each auto-logged message: names, phone numbers, account numbers and references are removed. Nothing is sent anywhere. You can download the file and choose to share it."))),
      el("div", { style: { marginTop: "10px" } }, el("button", { class: "btn sm", onclick: () => download("/api/samples/export", "flux-parser-samples.jsonl").catch(err) }, "Download my masked samples")));
    drawRules().catch(err);

    main.replaceChildren(pageHead("Settings", null), el("div", { class: "grid g-2" }, autoCard, learnCard, profile, autosave, voiceCard, data));
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
