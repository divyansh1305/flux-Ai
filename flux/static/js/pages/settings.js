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
        example.textContent = `Example: a ₹47 expense rounds up to ₹${up}, so ₹${up - 47} is set aside for your goal.`;
      } else if (mode.value === "percent") {
        example.textContent = `Example: a ₹400 expense sets aside ₹${(400 * v) / 100} for your goal.`;
      } else example.textContent = "Nothing is set aside automatically.";
    };
    const example = el("p", { class: "tiny faint" });
    mode.onchange = fillValues;
    value.onchange = describe;
    const goalSel = el("select", { class: "input" }, el("option", { value: "" }, goals.length ? "Choose a goal" : "Create a goal first"),
      goals.map((g) => el("option", { value: g.id, selected: u.autosave_goal_id === g.id ? true : null }, g.title)));
    fillValues();
    const autosave = el("div", { class: "card" }, el("h2", null, "Set aside as you spend"),
      el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "After each expense, Flux sets a little aside for your goal, only if you have it. The money stays in your bank account: Flux just stops counting it as spendable. To really save it, move it to a savings account or RD."),
      el("div", { class: "form" },
        el("label", { class: "field" }, "Mode", mode),
        el("label", { class: "field" }, "Amount", value), example,
        el("label", { class: "field" }, "For which goal", goalSel),
        el("div", null, el("button", { class: "btn primary", onclick: () => {
          const body = { autosave_mode: mode.value, autosave_goal_id: goalSel.value ? Number(goalSel.value) : null };
          if (mode.value !== "off") body.autosave_value = Number(value.value);
          save(body, "Saved.");
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
    const data = el("div", { class: "card", id: "data" }, el("h2", null, "Your data"),
      el("p", { class: "small muted", style: { margin: "6px 0 14px" } }, "You own your data. See exactly what Flux has, download it, or delete your account permanently."),
      el("div", { class: "row wrap" },
        el("a", { class: "btn", href: "/app/privacy-center" }, icon("eye"), "What Flux knows"),
        el("button", { class: "btn", onclick: () => download("/api/account/export", "flux-my-data.json").catch(err) }, icon("download"), "Download my data"),
        el("button", { class: "btn", onclick: logout }, icon("out"), "Sign out"),
        el("button", { class: "btn danger", onclick: async () => {
          const input = el("input", { class: "input", placeholder: "Type DELETE" });
          const v = await modal("Delete account?", el("div", { class: "form" },
            el("p", { class: "muted small" }, "This permanently deletes your account, payments, plans, budgets and goals, and removes Flux's access to your Gmail. It cannot be undone."), input),
            [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Delete forever", submit: true, cls: "danger", value: () => input.value }]);
          if (v === null) return;
          try { await api("/api/account", { method: "DELETE", body: { confirm: v } }); window.Flux.cacheClear(); location.href = "/"; } catch (e) { err(e); }
        } }, icon("trash"), "Delete account")));

    // Automatic tracking — one personal link, a bank picker, copy buttons. Only real steps.
    const BANKS = {
      "HDFC Bank": ["Sent Rs", "credited"], "SBI": ["debited", "credited"], "ICICI Bank": ["debited", "credited"],
      "Axis Bank": ["debited", "credited"], "Kotak": ["Sent Rs", "Received Rs"], "Paytm Payments Bank": ["debited", "credited"],
      "Other bank": ["debited", "credited"],
    };
    const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const isAndroid = /Android/.test(navigator.userAgent);
    const copy = (text, label) => el("button", { class: "btn sm", type: "button", onclick: () =>
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => ok(label + " copied.")).catch(() => window.prompt("Copy this:", text)) }, "Copy");
    const autoBox = el("div", { class: "stack", style: { gap: "14px" } });
    let link = null;      // the personal link, only known right after it is created
    let platform = isAndroid ? "android" : "iphone";
    let bank = "HDFC Bank";

    function numbered(items) {
      return el("ol", { class: "stack", style: { gap: "10px", paddingLeft: "20px", margin: 0 } }, items.map((x) => el("li", { class: "small" }, x)));
    }

    async function gmailBlock() {
      if (!(window.Flux.config.features || {}).gmail) return null;
      const g = await api("/api/gmail");
      if (!g.connected) {
        return el("div", { class: "notice info", style: { flexDirection: "column", alignItems: "stretch", gap: "10px" } },
          el("div", null, el("b", null, "Easiest: connect Gmail. "), "Most banks email you for every payment. Flux reads only those alert emails (read-only: it can't send, delete or change anything) and adds the payments by itself. Works on iPhone and Android."),
          el("div", null, el("a", { class: "btn primary", href: "/gmail/connect" }, "Connect Gmail")),
          el("div", { class: "tiny faint" }, "Google will say \"Google hasn't verified this app\" because Flux is new. Tap Continue. You can disconnect any time."));
      }
      const when = g.last_sync_at ? window.Flux.dateFmt(g.last_sync_at.slice(0, 10)) + " " + g.last_sync_at.slice(11, 16) + " UTC" : "not yet";
      if (g.needs_reconnect) {
        return el("div", { class: "notice caution", style: { flexDirection: "column", alignItems: "stretch", gap: "10px" } },
          el("div", null, el("b", null, "Gmail needs to be reconnected. "), `Google stopped sharing ${g.email}'s bank emails with Flux, so new email payments aren't coming in.`),
          el("div", null, el("a", { class: "btn primary", href: "/gmail/connect" }, "Reconnect Gmail")));
      }
      return el("div", { class: "notice ok", style: { flexDirection: "column", alignItems: "stretch", gap: "8px" } },
        el("div", null, el("b", null, "Gmail connected"), ` (${g.email}). ${g.imported} payment${g.imported === 1 ? "" : "s"} added so far. Last checked: ${when}.`),
        g.error ? el("div", { class: "small", style: { color: "var(--red)" } }, g.error) : null,
        el("div", { class: "row wrap", style: { gap: "8px" } },
          el("button", { class: "btn sm", type: "button", onclick: async () => {
            try {
              let r, added = 0;
              for (let i = 0; i < 6; i++) { r = await api("/api/gmail/sync", { method: "POST", body: { force: true } }); added += r.logged || 0; if (!r.more || r.error) break; }
              ok(r.error ? r.error : added ? `Added ${added} new payment${added === 1 ? "" : "s"}.` : "No new payments."); drawAuto();
            } catch (e) { err(e); } } }, "Check now"),
          el("button", { class: "btn sm danger", type: "button", onclick: async () => {
            await api("/api/gmail", { method: "DELETE" }); ok("Gmail disconnected."); drawAuto(); } }, "Disconnect")));
    }

    async function drawAuto() {
      const [st, gm] = await Promise.all([api("/api/ingest/token"), gmailBlock()]);
      const kids = [];
      kids.push(el("p", { class: "small muted", style: { margin: 0 } },
        "Flux reads only your bank's payment messages, never your chats or OTPs, and never your bank password."));
      if (gm) {
        kids.push(gm);
        kids.push(el("div", { class: "small muted", style: { marginTop: "4px" } }, "Or set up your phone:"));
      }
      const seg = el("div", { class: "seg" }, [["iphone", "iPhone"], ["android", "Android"]].map(([k, label]) =>
        el("button", { type: "button", class: platform === k ? "on" : "", onclick: () => { platform = k; drawAuto(); } }, label)));
      kids.push(seg);

      if (platform === "iphone") {
        const words = BANKS[bank];
        const bankSel = el("select", { class: "input", style: { maxWidth: "260px" }, onchange: (e) => { bank = e.target.value; drawAuto(); } },
          Object.keys(BANKS).map((b) => el("option", { value: b, selected: b === bank ? true : null }, b)));
        let linkBlock;
        if (link) {
          linkBlock = el("div", { class: "notice ok", style: { flexDirection: "column", gap: "8px" } },
            el("div", null, el("b", null, "Your personal link"), " (keep it private, like a password):"),
            el("code", { style: { wordBreak: "break-all", color: "var(--text)", fontSize: "12px" } }, link),
            el("div", null, copy(link, "Link")));
        } else {
          linkBlock = el("div", { class: "row wrap", style: { gap: "10px" } },
            el("button", { class: "btn primary", type: "button", onclick: async () => {
              const r = await api("/api/ingest/token", { method: "POST" }); link = r.iphone_url; drawAuto(); } },
              st.active ? "Make a new link" : "Get my personal link"),
            st.active ? el("span", { class: "small muted" }, "Making a new link stops the old one. Update your automations after.") : null);
        }
        kids.push(el("div", { class: "stack", style: { gap: "10px" } },
          el("label", { class: "field" }, "Your bank", bankSel),
          linkBlock));
        kids.push(numbered([
          ["Open the ", el("b", null, "Shortcuts"), " app → ", el("b", null, "Automation"), " (bottom) → ", el("b", null, "+"), " → ", el("b", null, "Message"), "."],
          ["Tap ", el("b", null, "Message Contains"), " and type ", el("code", null, words[0]), " ", copy(words[0], "Word"), ". Leave Sender empty. Choose ", el("b", null, "Run Immediately"), " → ", el("b", null, "Next"), " → ", el("b", null, "New Blank Automation"), "."],
          ["Search ", el("b", null, "Get Contents of URL"), " and add it. Tap ", el("b", null, "URL"), " and paste your personal link."],
          ["Tap the small ", el("b", null, "›"), " on that block. Set ", el("b", null, "Method"), " to ", el("b", null, "POST"), ", ", el("b", null, "Request Body"), " to ", el("b", null, "File"), ", then tap ", el("b", null, "File"), " and pick ", el("b", null, "Shortcut Input"), ". Tap ", el("b", null, "Done"), "."],
          ["Do steps 1–4 once more with the word ", el("code", null, words[1]), " ", copy(words[1], "Word"), " so money you receive is added too."],
          ["Test it: send ₹1 by UPI. It shows up in Flux under Recent within a few seconds."],
        ]));
      } else {
        const apk = (window.Flux.config.features || {}).android_apk;
        if (!apk) {
          kids.push(el("div", { class: "notice info" }, icon("info"), el("div", null,
            el("b", null, "Android app: coming soon. "), "Until then, ",
            el("a", { class: "link", href: "/app/share" }, "paste bank SMS"), " or ",
            el("a", { class: "link", href: "/app/import" }, "upload your statement"), ".")));
        } else {
          const linkApp = el("button", { class: "btn primary", type: "button", onclick: async () => {
            try {
              const r = await api("/api/ingest/token", { method: "POST" });
              location.href = `fluxapp://connect?server=${encodeURIComponent(r.server)}&token=${encodeURIComponent(r.token)}`;
            } catch (e) { err(e); }
          } }, "Link the Flux app");
          kids.push(el("p", { class: "small", style: { margin: 0 } },
            "The Flux app logs every GPay, PhonePe, Paytm and bank payment by itself. It reads only payment notifications, never chats or OTPs, and has no SMS permission."));
          kids.push(numbered([
            ["Download the app ", el("a", { class: "btn sm", href: apk }, icon("download"), "Flux for Android"), ". Open the file and allow your browser to install it (Android asks once)."],
            ["Come back to this page on the same phone and tap ", linkApp, ". It opens the app and links your account."],
            ["In the app: tick the box, tap ", el("b", null, "Open Notification access settings"), ", choose Flux Companion and allow it. If Android says \"Restricted setting\", the app shows you the one extra step."],
            ["Test it: pay ₹1 by UPI. It appears in Flux under Recent within a minute."],
          ]));
          if (!isAndroid) kids.push(el("div", { class: "tiny faint" }, "Open this page on your Android phone to do these steps."));
        }
      }

      kids.push(el("div", { class: "small " + (st.uses ? "green" : "muted") },
        st.active ? (st.uses ? `Working: ${st.uses} message${st.uses === 1 ? "" : "s"} received, last at ${st.last_used_at} UTC.` : "Link ready. Waiting for your first payment message.") : "Not set up yet."));
      if (st.active) kids.push(el("div", null, el("button", { class: "btn sm danger", type: "button", onclick: async () => {
        await api("/api/ingest/token", { method: "DELETE" }); link = null; ok("Automatic tracking turned off."); drawAuto(); } }, "Turn off automatic tracking")));
      if (/localhost|127\.0\.0\.1/.test(location.hostname)) kids.push(el("div", { class: "notice info" }, "Your phone can't reach localhost. Set this up from the live site."));
      autoBox.replaceChildren(...kids);
    }
    const autoCard = el("div", { class: "card", id: "auto", style: { gridColumn: "1 / -1" } }, el("h2", null, "Automatic tracking"), el("div", { style: { marginTop: "12px" } }, autoBox));
    drawAuto().catch(err);
    const gq = new URLSearchParams(location.search).get("gmail");
    if (gq === "error") err(new Error("Gmail couldn't be connected. Please try again, and tick the Gmail permission box on Google's screen."));
    if (gq === "cancelled") ok("Gmail wasn't connected. You can try again any time.");
    if (location.hash === "#auto") setTimeout(() => autoCard.scrollIntoView({ behavior: "smooth" }), 300);

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
    const learnCard = el("div", { class: "card", style: { gridColumn: "1 / -1" } }, el("h2", null, "What Flux has learned"),
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
