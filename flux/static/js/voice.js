/* Kitna Voice — a Siri-style assistant for the whole app.
   - Tap the mic, press Ctrl/⌘+K, or say "Hey Kitna" (optional wake word, Chrome/Edge).
   - Speech is recognised by the browser; the text goes to /api/voice/command,
     which understands English, Hindi and Hinglish and performs the action.
   - Replies are spoken aloud. Works by typing too when speech isn't available. */
(function () {
  "use strict";
  const { el, icon, api, ok, refresh } = window.Kitna;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const CONTINUE_KEY = "flux_voice_continue";
  const WAKE_KEY = "flux_wake_word";
  const WAKE_RE = /\b(hey|hi|ok|okay|hello)\s+(kitna|kitnaa|kithna|kitana|keetna)\b/i;

  const SUGGESTIONS = {
    "en-IN": ["What's my balance?", "Spent 250 on Swiggy", "How much did I spend this month?", "Can I afford 2000 shoes?", "Open goals", "Help"],
    "hi-IN": ["Kitne paise bache hain?", "Maine 200 chai pe kharch kiye", "Is mahine kitna kharch kiya?", "Papa se 2000 mile", "Goals kholo"],
  };

  let user = null;
  let lang = "en-IN";
  let overlay = null, orb, stateEl, heardEl, replyEl, actionsEl, typeInput;
  let rec = null, listening = false, pending = null;
  let wakeRec = null, wakeOn = false, wakePaused = false;
  let fab = null;

  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }

  // ─── Speaking ─────────────────────────────────────────────
  function pickVoice(l) {
    if (!synth) return null;
    const voices = synth.getVoices();
    return voices.find((v) => v.lang === l) || voices.find((v) => v.lang && v.lang.startsWith(l.split("-")[0])) ||
      voices.find((v) => v.lang === "en-IN") || voices.find((v) => v.lang && v.lang.startsWith("en")) || null;
  }
  function speak(text, then) {
    if (!synth || !text) { if (then) then(); return; }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/₹/g, "rupees ").replace(/(\d),(\d)/g, "$1$2"));
    const l = /[ऀ-ॿ]/.test(text) ? "hi-IN" : "en-IN";
    u.lang = l;
    const v = pickVoice(l);
    if (v) u.voice = v;
    u.rate = 1.04;
    u.onstart = () => setState("speaking");
    u.onend = u.onerror = () => { setState("idle"); if (then) then(); };
    synth.speak(u);
  }

  // ─── Overlay UI ───────────────────────────────────────────
  function setState(s) {
    if (!orb) return;
    orb.className = "v-mic " + (s === "listening" || s === "thinking" ? s : "");
    overlay.classList.toggle("listening-on", s === "listening");
    stateEl.firstChild.textContent = { listening: "Listening", thinking: "Thinking…", speaking: "Kitna", idle: SR ? "Tap the mic and speak" : "Type a command" }[s] || "";
  }

  function chips() {
    const box = el("div", { class: "v-suggest" });
    (SUGGESTIONS[lang] || SUGGESTIONS["en-IN"]).forEach((s) =>
      box.appendChild(el("button", { class: "chip", type: "button", onclick: () => send(s) }, s)));
    return box;
  }

  function open(startListening = true) {
    if (overlay) { if (startListening) listen(); return; }
    pauseWake();
    orb = el("button", { class: "v-mic", type: "button", "aria-label": "Talk to Kitna", onclick: () => (listening ? stopListening() : listen()) }, icon("mic"));
    stateEl = el("div", { class: "v-state row", style: { gap: "0" } }, el("span"), el("span", { class: "eq", "aria-hidden": "true" }, el("i"), el("i"), el("i"), el("i")));
    heardEl = el("div", { class: "v-heard", "aria-live": "polite" });
    replyEl = el("div", { class: "v-reply", "aria-live": "assertive" });
    actionsEl = el("div", { class: "row wrap" });
    typeInput = el("input", { class: "input", placeholder: SR ? "Or type: spent 200 on lunch" : "Type a command, e.g. spent 200 on lunch", maxlength: "300", "aria-label": "Type a command" });
    const typeForm = el("form", { class: "v-type", onsubmit: (e) => { e.preventDefault(); if (typeInput.value.trim()) send(typeInput.value.trim()); typeInput.value = ""; } },
      typeInput, el("button", { class: "btn primary", type: "submit", "aria-label": "Send" }, icon("send")));
    const langBtn = el("button", { class: "chip", type: "button", onclick: () => switchLang(langBtn) }, lang === "hi-IN" ? "हिंदी" : "English");
    const sheet = el("div", { class: "voice-sheet" },
      el("button", { class: "btn ghost sm v-close", type: "button", "aria-label": "Close", onclick: close }, icon("x")),
      el("div", { class: "v-top" }, orb, el("div", { style: { flex: 1, minWidth: 0 } }, stateEl, heardEl)),
      replyEl, actionsEl, chips(), typeForm,
      el("div", { class: "row tiny faint wrap" }, langBtn, SR ? "Esc to close · Ctrl/⌘+K to open" : "Voice input works in Chrome, Edge and Safari."));
    overlay = el("div", { class: "voice-overlay", role: "dialog", "aria-label": "Kitna voice assistant",
      onclick: (e) => { if (e.target === overlay) close(); } }, sheet);
    document.body.appendChild(overlay);
    setState("idle");
    if (startListening && SR) listen(); else typeInput.focus();
  }

  function close() {
    stopListening();
    if (synth) synth.cancel();
    if (overlay) overlay.remove();
    overlay = null;
    pending = null;
    resumeWake();
  }

  function switchLang(btn) {
    lang = lang === "en-IN" ? "hi-IN" : "en-IN";
    btn.textContent = lang === "hi-IN" ? "हिंदी" : "English";
    api("/api/account", { method: "PATCH", body: { voice_lang: lang } }).catch(() => {});
    const old = overlay.querySelector(".v-suggest");
    if (old) old.replaceWith(chips());
  }

  // ─── Listening ────────────────────────────────────────────
  function listen() {
    if (!SR) { typeInput && typeInput.focus(); return; }
    stopListening();
    if (synth) synth.cancel();
    rec = new SR();
    rec.lang = lang;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.continuous = false;
    let finalText = "";
    rec.onstart = () => { listening = true; setState("listening"); heardEl.textContent = ""; heardEl.className = "v-heard interim"; };
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
      }
      heardEl.textContent = (finalText + " " + interim).trim();
    };
    rec.onerror = (e) => {
      listening = false;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        replyEl.textContent = "Microphone access is blocked. Allow it in your browser's site settings, or type below.";
      } else if (e.error === "no-speech") {
        replyEl.textContent = "I didn't hear anything. Tap the orb and try again.";
      } else if (e.error !== "aborted") {
        replyEl.textContent = "Voice recognition hit a problem. You can type instead.";
      }
      setState("idle");
    };
    rec.onend = () => {
      listening = false;
      const text = finalText.trim();
      if (text) send(text); else if (orb && orb.className.includes("listening")) setState("idle");
    };
    try { rec.start(); } catch (e) { setState("idle"); }
  }
  function stopListening() {
    if (rec) { try { rec.onend = null; rec.abort(); } catch (e) { /* ignore */ } }
    rec = null; listening = false;
  }

  // ─── Sending commands ─────────────────────────────────────
  const YES = /^(yes|yeah|yep|sure|confirm|ok|okay|haan|ha|han|ji|haan ji|ji haan|theek hai|हाँ|हां|जी)\b/i;
  const NO = /^(no|nope|cancel|stop|nahi|nahin|mat|नहीं|ना)\b/i;

  async function send(text) {
    if (!overlay) open(false);
    heardEl.textContent = text;
    heardEl.className = "v-heard";
    replyEl.textContent = "";
    actionsEl.replaceChildren();

    if (pending) {
      const p = pending;
      if (YES.test(text.trim())) { pending = null; return run({ confirmed: true, command: p }); }
      if (NO.test(text.trim())) { pending = null; return respond({ reply: "Okay, cancelled." }); }
      pending = null;
    }
    return run({ text });
  }

  async function run(body) {
    setState("thinking");
    let r;
    try {
      r = await api("/api/voice/command", { method: "POST", body });
    } catch (e) {
      return respond({ reply: e.message, error: true });
    }
    respond(r);
  }

  function respond(r) {
    replyEl.textContent = r.reply || "";
    if (r.refresh) refresh();
    if (r.undo) {
      actionsEl.appendChild(el("button", { class: "btn sm", type: "button", onclick: async () => {
        try { await api("/api/voice/undo", { method: "POST", body: r.undo }); replyEl.textContent = "Undone."; refresh(); actionsEl.replaceChildren(); }
        catch (e) { replyEl.textContent = e.message; }
      } }, "Undo"));
    }
    if (r.needs_confirmation) {
      pending = r.command;
      actionsEl.append(
        el("button", { class: "btn primary sm", type: "button", onclick: () => send("yes") }, "Yes"),
        el("button", { class: "btn sm", type: "button", onclick: () => send("no") }, "No"));
      return speak(r.reply, () => { if (overlay && pending) listen(); });
    }
    if (r.logout) return speak(r.reply, () => window.Kitna.logout());
    if (r.navigate && r.navigate !== location.pathname && !["budget_status", "goal_status", "health_score"].includes(r.intent)) {
      try { sessionStorage.setItem(CONTINUE_KEY, JSON.stringify({ heard: r.heard || "", reply: r.reply })); } catch (e) { /* ignore */ }
      return speak(r.reply, () => { location.href = r.navigate; });
    }
    if (r.navigate && r.navigate !== location.pathname) {
      actionsEl.appendChild(el("a", { class: "btn sm", href: r.navigate }, "Open"));
    }
    speak(r.reply);
  }

  // ─── "Hey Kitna" wake word (optional) ──────────────────────
  function startWake() {
    if (!SR || wakeRec || !wakeOn) return;
    wakeRec = new SR();
    wakeRec.lang = lang;
    wakeRec.continuous = true;
    wakeRec.interimResults = true;
    wakeRec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        const m = t.match(WAKE_RE);
        if (m && e.results[i].isFinal) {
          const after = t.slice(m.index + m[0].length).trim();
          stopWake();
          open(!after);
          if (after) send(after);
          return;
        }
      }
    };
    wakeRec.onend = () => { wakeRec = null; if (wakeOn && !wakePaused && !overlay) setTimeout(startWake, 400); };
    wakeRec.onerror = (e) => { if (e.error === "not-allowed") { wakeOn = false; store(WAKE_KEY, "0"); updateFab(); } };
    try { wakeRec.start(); } catch (e) { wakeRec = null; }
    updateFab();
  }
  function stopWake() { if (wakeRec) { wakeRec.onend = null; try { wakeRec.abort(); } catch (e) { /* ignore */ } } wakeRec = null; updateFab(); }
  function pauseWake() { wakePaused = true; stopWake(); }
  function resumeWake() { wakePaused = false; if (wakeOn) setTimeout(startWake, 500); }
  function setWake(on) {
    wakeOn = !!on && !!SR;
    store(WAKE_KEY, wakeOn ? "1" : "0");
    if (wakeOn) startWake(); else stopWake();
    updateFab();
  }
  function updateFab() {
    if (!fab) return;
    fab.classList.toggle("wake", !!wakeRec);
    fab.title = wakeRec ? 'Listening for "Hey Kitna"… (tap to talk)' : "Talk to Kitna (Ctrl/⌘+K)";
  }

  // ─── Init ─────────────────────────────────────────────────
  function init(u) {
    user = u;
    lang = (u && u.voice_lang) || "en-IN";
    fab = el("button", { class: "mic-fab", type: "button", "aria-label": "Talk to Kitna", onclick: () => open(true) }, icon("mic"));
    const hint = el("div", { class: "mic-hint" }, SR ? "Ask Kitna anything" : "Type to Kitna");
    document.body.append(fab, hint);
    setTimeout(() => hint.remove(), 6000);
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); overlay ? close() : open(true); }
      else if (e.key === "Escape" && overlay) close();
    });
    if (synth) synth.getVoices(); // warm up voice list
    // Continue a conversation after a voice-triggered page change.
    let cont = null;
    try { cont = JSON.parse(sessionStorage.getItem(CONTINUE_KEY) || "null"); sessionStorage.removeItem(CONTINUE_KEY); } catch (e) { /* ignore */ }
    if (cont) {
      open(false);
      heardEl.textContent = cont.heard;
      replyEl.textContent = cont.reply;
      setTimeout(() => { if (overlay && !listening) close(); }, 2500);
    }
    if (store(WAKE_KEY) === "1") setWake(true);
  }

  window.FluxVoice = { init, open, close, send, setWake, get wakeOn() { return wakeOn; }, supported: !!SR, speak };
})();
