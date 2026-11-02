/* Scan & Pay — pause before you pay.
   Scan a UPI QR → see budget impact → pay in your own UPI app → Flux logs it automatically. */
(function () {
  const { el, icon, api, ok, err, inr, pageHead, meta, CAT_EMOJI } = window.Flux;
  const ua = navigator.userAgent;
  const IS_ANDROID = /Android/i.test(ua);
  const IS_IOS = /iPhone|iPad|iPod/i.test(ua);
  const IS_MOBILE = IS_ANDROID || IS_IOS;

  let stream = null, scanTimer = null, detector = null;

  function stopCamera() {
    if (scanTimer) cancelAnimationFrame(scanTimer);
    scanTimer = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }

  async function decodeFrame(source, w, h) {
    if (detector) {
      try { const codes = await detector.detect(source); if (codes.length) return codes[0].rawValue; } catch (e) { /* fall back */ }
    }
    if (window.jsQR) {
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(source, 0, 0, w, h);
      const img = ctx.getImageData(0, 0, w, h);
      const code = window.jsQR(img.data, w, h, { inversionAttempts: "attemptBoth" });
      if (code) return code.data;
    }
    return null;
  }

  async function render(main) {
    const m = await meta();
    if ("BarcodeDetector" in window) {
      try { detector = new window.BarcodeDetector({ formats: ["qr_code"] }); } catch (e) { detector = null; }
    }
    const area = el("div", { class: "grid g-main" });
    main.replaceChildren(pageHead("Scan & Pay", "Flux checks your budget first, then your own UPI app does the payment. Flux never touches your money."), area);

    const params = new URLSearchParams(location.search);
    if (params.get("vpa")) {
      return showPayee({ vpa: params.get("vpa"), name: params.get("name") || "", amount: Number(params.get("amount")) || null,
        category: "Other", category_reason: null, known_payee: false, amount_locked: false });
    }
    if (params.get("amount")) startScreen(Number(params.get("amount")));
    else startScreen();

    function startScreen(prefillAmount) {
      stopCamera();
      const video = el("video", { playsinline: true, muted: true, autoplay: true });
      const msg = el("div", { class: "msg" }, "Starting camera…");
      const scanner = el("div", { class: "scanner" }, video, el("div", { class: "frame" }), msg);
      const fileIn = el("input", { type: "file", accept: "image/*", class: "sr-only", id: "qr-file" });
      fileIn.onchange = () => fileIn.files[0] && fromImage(fileIn.files[0]);
      const vpa = el("input", { class: "input", placeholder: "name@okaxis", autocomplete: "off", "aria-label": "UPI ID" });
      const manual = el("form", { class: "form", onsubmit: async (e) => { e.preventDefault(); handleCode(vpa.value.trim(), prefillAmount); } },
        el("label", { class: "field" }, "Or enter a UPI ID", vpa), el("button", { class: "btn", type: "submit" }, "Continue"));
      const payeesBox = el("div", { class: "chips" });
      api("/api/pay/payees").then((list) => {
        list.forEach((p) => payeesBox.appendChild(el("button", { class: "chip", type: "button", onclick: () => handleCode(p.vpa, prefillAmount) },
          (p.name || p.vpa))));
        if (list.length) payeesBox.before(el("div", { class: "small muted", style: { marginTop: "8px" } }, "Pay again"));
      }).catch(() => {});

      area.replaceChildren(
        el("div", { class: "card" }, scanner,
          el("div", { class: "row wrap", style: { marginTop: "14px" } },
            el("label", { for: "qr-file", class: "btn" }, icon("image"), "Scan from photo"), fileIn,
            prefillAmount ? el("span", { class: "badge voice" }, "Amount: " + inr(prefillAmount)) : null)),
        el("div", { class: "stack" },
          el("div", { class: "card" }, manual, payeesBox),
          el("div", { class: "card" }, el("h3", null, "How it works"),
            el("ol", { class: "small muted", style: { paddingLeft: "18px", margin: "10px 0 0", lineHeight: 1.9 } },
              el("li", null, "Scan any UPI QR: shop, friend, restaurant"),
              el("li", null, "See how it affects your budget and goals"),
              el("li", null, "Pay in GPay, PhonePe, Paytm or BHIM with your PIN"),
              el("li", null, "Come back: Flux logs it and auto-saves")))));
      startCamera(video, msg, prefillAmount);
    }

    async function startCamera(video, msg, prefillAmount) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        msg.textContent = "Camera not available here. Use “Scan from photo” or enter a UPI ID.";
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
        video.srcObject = stream;
        await video.play();
        msg.textContent = "Point at a UPI QR code";
        const tick = async () => {
          if (!stream) return;
          if (video.readyState >= 2) {
            const w = Math.min(640, video.videoWidth), h = Math.round(w * video.videoHeight / video.videoWidth);
            const code = await decodeFrame(video, w, h);
            if (code) { stopCamera(); return handleCode(code, prefillAmount); }
          }
          scanTimer = requestAnimationFrame(tick);
        };
        tick();
      } catch (e) {
        msg.textContent = e.name === "NotAllowedError" ? "Camera permission denied. Use a photo or UPI ID instead." : "Couldn't start the camera.";
      }
    }

    async function fromImage(file) {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = async () => {
        const scale = Math.min(1, 1200 / Math.max(img.width, img.height));
        const code = await decodeFrame(img, Math.round(img.width * scale), Math.round(img.height * scale));
        URL.revokeObjectURL(url);
        if (code) handleCode(code); else err("No QR code found in that photo. Try a clearer, closer shot.");
      };
      img.src = url;
    }

    async function handleCode(code, prefillAmount) {
      if (!code) return;
      try {
        const d = await api("/api/pay/parse", { method: "POST", body: { code } });
        if (d.amount == null && prefillAmount) d.amount = prefillAmount;
        stopCamera();
        showPayee(d);
      } catch (e) { err(e); }
    }

    function showPayee(d) {
      stopCamera();
      const initials = (d.name || d.vpa).split(/[\s@.]+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
      const amount = el("input", { class: "input big num", type: "number", inputmode: "decimal", min: "1", max: "100000", step: "0.01",
        value: d.amount || "", placeholder: "0", readonly: d.amount_locked ? true : null, "aria-label": "Amount" });
      const cat = el("select", { class: "input" }, m.expense_categories.map((c) => el("option", { value: c, selected: c === d.category ? true : null }, c)));
      const note = el("input", { class: "input", maxlength: "50", placeholder: "What's this for? (optional)", value: d.note || "" });
      const check = el("div");
      const payBtn = el("button", { class: "btn primary lg block", type: "submit" }, "Continue to pay");
      let t;
      const runCheck = () => {
        clearTimeout(t);
        if (!(Number(amount.value) > 0)) { check.replaceChildren(); return; }
        t = setTimeout(async () => {
          try {
            const r = await api("/api/transactions/check", { method: "POST", body: { amount: amount.value, category: cat.value } });
            const lines = r.warnings.length ? r.warnings.slice() : [`You'll have ${inr(r.balance_after)} left to spend.`];
            if (r.goal_delay_days) lines.push(`Pushes your goals back about ${r.goal_delay_days} day(s).`);
            if (r.autosave_would_add > 0) lines.push(`${inr(r.autosave_would_add)} will be auto-saved.`);
            check.replaceChildren(el("div", { class: "notice " + r.level }, el("div", null,
              el("b", null, r.level === "ok" ? "Looks fine. " : r.level === "caution" ? "Heads up. " : "Think twice. "), ...lines.map((l) => el("div", null, l)))));
            payBtn.textContent = r.level === "stop" ? "Pay anyway" : `Pay ${inr(amount.value)}`;
          } catch (e) { /* ignore */ }
        }, 250);
      };
      amount.addEventListener("input", runCheck);
      cat.addEventListener("change", runCheck);
      const form = el("form", { class: "form", onsubmit: async (e) => {
        e.preventDefault();
        payBtn.disabled = true;
        try {
          const r = await api("/api/pay/prepare", { method: "POST", body: { vpa: d.vpa, name: d.name, amount: amount.value, category: cat.value, note: note.value } });
          showHandoff(r);
        } catch (ex) { err(ex); payBtn.disabled = false; }
      } },
        el("div", { class: "payee" }, el("div", { class: "avatar" }, initials || "₹"),
          el("div", { style: { minWidth: 0 } }, el("h2", null, d.name || d.vpa), el("div", { class: "small faint" }, d.vpa, d.is_merchant ? " · verified merchant QR" : ""))),
        el("label", { class: "field" }, "Amount (₹)" + (d.amount_locked ? " · set by merchant" : ""), amount),
        el("label", { class: "field" }, "Category", cat),
        d.category_reason ? el("div", { class: "tiny faint", style: { marginTop: "-8px" } }, `Suggested from ${d.category_reason}.`) : null,
        el("label", { class: "field" }, "Note", note), check, payBtn,
        el("button", { class: "btn ghost block", type: "button", onclick: () => { history.replaceState(null, "", "/app/pay"); startScreen(); } }, "Scan a different code"));
      area.replaceChildren(el("div", { class: "card" }, form),
        el("div", { class: "card" }, el("h3", null, "Why Flux asks first"),
          el("p", { class: "small muted", style: { marginTop: "10px" } }, "UPI makes paying feel effortless, so it's easy to overspend. A two-second check before you pay is the moment you can still change your mind.")));
      runCheck();
      if (!d.amount) amount.focus();
    }

    function showHandoff(r) {
      const opened = { at: 0 };
      const markOpened = () => { opened.at = Date.now(); };
      const appButtons = IS_MOBILE ? r.links.apps.map((a) =>
        el("a", { class: "app-btn", href: IS_ANDROID ? a.android : a.ios, onclick: markOpened }, "Open " + a.name)) : [];
      const confirmBox = el("div", { class: "stack", style: { gap: "10px" } },
        el("h3", null, "Did the payment go through?"),
        el("div", { class: "row wrap" },
          el("button", { class: "btn primary", onclick: () => finish("paid") }, icon("check"), "Yes, paid"),
          el("button", { class: "btn", onclick: () => finish("failed") }, "No / failed"),
          el("button", { class: "btn ghost", onclick: () => finish("cancelled") }, "Cancel")));
      async function finish(status) {
        try {
          const res = await api(`/api/pay/${r.payment_id}/confirm`, { method: "POST", body: { status } });
          if (status === "paid") {
            ok(`Logged ${inr(r.amount)} to ${r.name}.` + (res.autosaved ? ` ${inr(res.autosaved)} auto-saved to ${res.autosave_goal}.` : ""));
            setTimeout(() => (location.href = "/app"), 900);
          } else { ok("Okay, nothing was logged."); startScreen(); }
        } catch (e) { err(e); }
      }
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && opened.at && Date.now() - opened.at > 1500) confirmBox.scrollIntoView({ behavior: "smooth" });
      }, { once: false });

      const copy = el("button", { class: "btn sm", onclick: () => navigator.clipboard && navigator.clipboard.writeText(r.vpa).then(() => ok("UPI ID copied.")) }, "Copy UPI ID");
      area.replaceChildren(
        el("div", { class: "card stack" },
          el("div", { class: "eyebrow" }, "Paying"),
          el("div", { style: { fontSize: "52px", fontWeight: 850, letterSpacing: "-0.04em", lineHeight: 1 } }, inr(r.amount)),
          el("div", { class: "muted" }, "to ", el("b", null, r.name), " · ", r.vpa),
          IS_MOBILE
            ? el("div", { class: "stack", style: { gap: "8px" } },
              IS_ANDROID ? el("a", { class: "btn primary lg block", href: r.links.generic, onclick: markOpened }, "Choose UPI app") : null,
              el("div", { class: "grid g-2", style: { gap: "8px" } }, appButtons))
            : el("div", { class: "notice info" }, el("div", null, "UPI apps open on phones. Open Flux on your phone to pay in one tap, or pay ",
              el("b", null, r.vpa), " from any UPI app, then come back here.", el("div", { style: { marginTop: "8px" } }, copy))),
          el("div", { class: "tiny faint" }, "Reference ", r.ref, ". Your PIN is entered only in your UPI app.")),
        el("div", { class: "card" }, confirmBox));
    }
  }

  window.addEventListener("pagehide", stopCamera);
  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
