/* Kitna helper: in-app support chat. Answers only about Kitna, in 11 languages, by typing or by voice.
   Opens from the ? in the top bar or You → Help. The server grounds every answer on the Kitna guide. */
(function () {
  "use strict";
  const K = window.Kitna;
  if (!K) return;
  const { el, icon, api } = K;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;

  // UI words for the languages people pick most; the AI answers in any of the 11.
  const LANGS = [
    ["en", "English", "en-IN"], ["hi", "हिन्दी", "hi-IN"], ["hinglish", "Hinglish", "en-IN"], ["ta", "தமிழ்", "ta-IN"],
    ["te", "తెలుగు", "te-IN"], ["bn", "বাংলা", "bn-IN"], ["mr", "मराठी", "mr-IN"], ["gu", "ગુજરાતી", "gu-IN"],
    ["kn", "ಕನ್ನಡ", "kn-IN"], ["ml", "മലയാളം", "ml-IN"], ["pa", "ਪੰਜਾਬੀ", "pa-IN"],
  ];
  const HELLO = {
    en: "Hi! I'm the Kitna helper. Ask me anything about using Kitna.",
    hi: "नमस्ते! मैं Kitna helper हूँ। Kitna इस्तेमाल करने के बारे में कुछ भी पूछिए।",
    hinglish: "Hi! Main Kitna helper hoon. Kitna use karne ke baare mein kuch bhi poochho.",
    ta: "வணக்கம்! நான் Kitna helper. Kitna பயன்படுத்துவது பற்றி எதையும் கேளுங்கள்.",
    te: "నమస్తే! నేను Kitna helper. Kitna వాడటం గురించి ఏదైనా అడగండి.",
    bn: "নমস্কার! আমি Kitna helper। Kitna ব্যবহার নিয়ে যা খুশি জিজ্ঞেস করুন।",
    mr: "नमस्कार! मी Kitna helper आहे. Kitna वापरण्याबद्दल काहीही विचारा.",
    gu: "નમસ્તે! હું Kitna helper છું. Kitna વાપરવા વિશે કંઈ પણ પૂછો.",
    kn: "ನಮಸ್ಕಾರ! ನಾನು Kitna helper. Kitna ಬಳಸುವ ಬಗ್ಗೆ ಏನು ಬೇಕಾದರೂ ಕೇಳಿ.",
    ml: "നമസ്കാരം! ഞാൻ Kitna helper ആണ്. Kitna ഉപയോഗിക്കുന്നതിനെക്കുറിച്ച് എന്തും ചോദിക്കൂ.",
    pa: "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ Kitna helper ਹਾਂ। Kitna ਵਰਤਣ ਬਾਰੇ ਕੁਝ ਵੀ ਪੁੱਛੋ।",
  };
  const STARTERS = {
    en: ["How is today's number worked out?", "How do I track payments automatically?", "Scan isn't opening", "How do I split a bill?"],
    hi: ["आज का नंबर कैसे बनता है?", "पेमेंट अपने-आप कैसे जुड़ें?", "स्कैन नहीं खुल रहा", "बिल कैसे बाँटें?"],
    hinglish: ["Aaj ka number kaise banta hai?", "Payments automatic kaise track karu?", "Scan nahi khul raha", "Bill split kaise karu?"],
  };

  const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  function defaultLang() {
    const saved = store("kitna_help_lang");
    if (saved && LANGS.some(([c]) => c === saved)) return saved;
    const u = K.user;
    if (u && u.lang === "hinglish") return "hinglish";
    const nav = (navigator.language || "en").slice(0, 2);
    return LANGS.some(([c]) => c === nav) ? nav : "en";
  }

  let open = false;
  function openHelp() {
    if (open) return;
    open = true;
    let lang = defaultLang();
    let speakOn = store("kitna_help_speak") === "1";
    const history = [];
    let rec = null, listening = false, busy = false;

    const msgs = el("div", { class: "help-msgs", "aria-live": "polite" });
    const input = el("input", { class: "input help-input", placeholder: "Ask about Kitna…", autocomplete: "off", "aria-label": "Your question", enterkeyhint: "send" });
    const sendBtn = el("button", { class: "btn primary help-send", type: "submit", "aria-label": "Send" }, icon("send"));
    const micBtn = SR ? el("button", { class: "btn help-mic", type: "button", "aria-label": "Speak your question", onclick: () => toggleMic() }, icon("mic")) : null;
    const langSel = el("select", { class: "help-lang", "aria-label": "Language", onchange: (e) => { lang = e.target.value; store("kitna_help_lang", lang); hello(); } },
      LANGS.map(([c, name]) => el("option", { value: c, selected: c === lang ? true : null }, name)));
    const speakBtn = el("button", { class: "help-speak" + (speakOn ? " on" : ""), type: "button", "aria-pressed": String(speakOn),
      title: "Read answers aloud", "aria-label": "Read answers aloud", onclick: () => {
        speakOn = !speakOn; store("kitna_help_speak", speakOn ? "1" : "0");
        speakBtn.classList.toggle("on", speakOn); speakBtn.setAttribute("aria-pressed", String(speakOn));
        if (!speakOn && synth) synth.cancel();
      } }, el("span", { "aria-hidden": "true" }, "🔊"));
    const close = () => { open = false; if (synth) synth.cancel(); if (rec) try { rec.abort(); } catch (e) { /* ignore */ } bg.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    const form = el("form", { class: "help-form", onsubmit: (e) => { e.preventDefault(); ask(input.value); } }, micBtn, input, sendBtn);
    const sheet = el("div", { class: "modal sheet help-sheet", role: "dialog", "aria-modal": "true", "aria-label": "Kitna helper" },
      el("div", { class: "help-head" },
        el("div", { class: "help-title" }, el("b", null, "Kitna helper"), el("span", null, "Answers about using Kitna")),
        langSel, synth ? speakBtn : null,
        el("button", { type: "button", class: "modal-x", "aria-label": "Close", onclick: close }, icon("x"))),
      msgs, form,
      el("p", { class: "tiny faint help-foot" }, "Never share OTPs, PINs or passwords here. For money questions, use Ask Kitna."));
    const bg = el("div", { class: "modal-bg sheet-bg", onclick: (e) => { if (e.target === bg) close(); } }, sheet);
    document.body.appendChild(bg);
    document.addEventListener("keydown", onKey);

    function bubble(role, text, links) {
      const b = el("div", { class: "help-msg " + role }, el("div", { class: "help-bubble" }, text));
      if (links && links.length) b.appendChild(el("div", { class: "help-links" }, links.map((l) =>
        el("a", { class: "btn sm", href: l.href, onclick: () => close() }, l.label))));
      msgs.appendChild(b);
      msgs.scrollTop = msgs.scrollHeight;
      return b;
    }
    function hello() {
      msgs.replaceChildren();
      history.length = 0;
      bubble("bot", HELLO[lang] || HELLO.en);
      const chips = el("div", { class: "help-starters" }, (STARTERS[lang] || STARTERS.en).map((s) =>
        el("button", { class: "chip", type: "button", onclick: () => ask(s) }, s)));
      msgs.appendChild(chips);
      input.placeholder = lang === "en" ? "Ask about Kitna…" : "…";
    }
    function speak(text) {
      if (!speakOn || !synth || !text) return;
      synth.cancel();
      const code = (LANGS.find(([c]) => c === lang) || LANGS[0])[2];
      const u = new SpeechSynthesisUtterance(text);
      u.lang = code;
      const v = synth.getVoices().find((x) => x.lang === code) || synth.getVoices().find((x) => x.lang && x.lang.startsWith(code.slice(0, 2)));
      if (v) u.voice = v;
      synth.speak(u);
    }
    async function ask(text) {
      text = String(text || "").trim();
      if (!text || busy) return;
      busy = true; sendBtn.disabled = true;
      const st = msgs.querySelector(".help-starters"); if (st) st.remove();
      input.value = "";
      bubble("me", text);
      history.push({ role: "user", text });
      const typing = bubble("bot typing", "…");
      try {
        const r = await api("/api/help/chat", { method: "POST", body: { messages: history.slice(-10), lang, screen: location.pathname.split("/")[2] || "home" } });
        typing.remove();
        bubble("bot", r.reply, r.links);
        history.push({ role: "assistant", text: r.reply });
        speak(r.reply);
      } catch (e) {
        typing.remove();
        bubble("bot", (e && e.message) || "Something went wrong. Try again in a moment.");
      } finally { busy = false; sendBtn.disabled = false; input.focus(); }
    }
    function toggleMic() {
      if (listening && rec) { rec.stop(); return; }
      if (synth) synth.cancel();
      rec = new SR();
      rec.lang = (LANGS.find(([c]) => c === lang) || LANGS[0])[2];
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.onstart = () => { listening = true; micBtn.classList.add("on"); input.placeholder = "Listening…"; };
      rec.onresult = (e) => {
        const t = Array.from(e.results).map((x) => x[0].transcript).join(" ");
        input.value = t;
        if (e.results[e.results.length - 1].isFinal) ask(t);
      };
      rec.onerror = (e) => { if (e.error === "not-allowed") bubble("bot", "The microphone is blocked. Allow it in your browser settings, or type instead."); };
      rec.onend = () => { listening = false; micBtn.classList.remove("on"); input.placeholder = "Ask about Kitna…"; };
      try { rec.start(); } catch (e) { /* already started */ }
    }
    hello();
    setTimeout(() => input.focus(), 50);
  }

  K.helpChat = openHelp;
})();
