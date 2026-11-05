/* Scan & Pay: scan a UPI QR → see what it does to today's number → pay in your own UPI app → Kitna logs it.
   Kitna never moves money and never sees the UPI PIN. */
(function () {
  const { el, icon, api, ok, err, inr, avatar, meta } = window.Kitna;
  const ua = navigator.userAgent;
  const IS_ANDROID = /Android/i.test(ua);
  const IS_IOS = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
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
    const area = el("div", { class: "pay-flow" });
    main.replaceChildren(area);

    const params = new URLSearchParams(location.search);
    if (params.get("vpa")) {
      return showPayee({ vpa: params.get("vpa"), name: params.get("name") || "", amount: Number(params.get("amount")) || null,
        category: "Other", known_payee: false, amount_locked: false, is_merchant: false });
    }
    startScreen(Number(params.get("amount")) || null);

    // ── 1. Scan
    function startScreen(prefillAmount) {
      stopCamera();
      const video = el("video", { playsinline: true, muted: true, autoplay: true });
      const msg = el("div", { class: "msg" }, "Starting camera…");
      const scanner = el("div", { class: "scanner" }, video, el("div", { class: "frame" }), msg);
      const fileIn = el("input", { type: "file", accept: "image/*", class: "sr-only", id: "qr-file" });
      fileIn.onchange = () => fileIn.files[0] && fromImage(fileIn.files[0]);
      const vpa = el("input", { class: "input", placeholder: "UPI ID or phone@upi", autocomplete: "off", autocapitalize: "none", "aria-label": "UPI ID" });
      const manual = el("form", { class: "row", style: { gap: "8px" }, onsubmit: (e) => { e.preventDefault(); handleCode(vpa.value.trim(), prefillAmount); } },
        vpa, el("button", { class: "btn", type: "submit" }, "Next"));
      const again = el("div");
      api("/api/pay/payees").then((list) => {
        if (!list.length) return;
        again.replaceChildren(el("div", { class: "section-title" }, el("span", null, "Pay again")),
          el("div", { class: "people" }, list.slice(0, 8).map((p) => el("button", { class: "person", type: "button", onclick: () => handleCode(p.vpa, prefillAmount) },
            avatar(p.name || p.vpa), el("span", null, (p.name || p.vpa.split("@")[0]).split(" ")[0])))));
      }).catch(() => {});

      area.replaceChildren(
        el("h1", { class: "pay-title" }, "Scan & Pay"),
        scanner,
        el("div", { class: "row", style: { gap: "8px", marginTop: "12px" } },
          el("label", { for: "qr-file", class: "btn block" }, icon("image"), "QR from photo"), fileIn,
          prefillAmount ? el("span", { class: "badge" }, inr(prefillAmount)) : null),
        el("div", { class: "pay-or" }, el("span", null, "or")),
        manual,
        again,
        el("p", { class: "tiny faint pay-foot" }, icon("shield"), "You pay with your PIN in your own UPI app. Kitna never touches your money."),
        el("button", { class: "link pay-cash", type: "button", onclick: () => window.Kitna.addTransactionModal("expense") }, "Paid in cash? Add it"));
      startCamera(video, msg, prefillAmount);
    }

    async function startCamera(video, msg, prefillAmount) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        msg.textContent = "No camera here. Use a photo or a UPI ID.";
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
        video.srcObject = stream;
        await video.play();
        msg.textContent = "Point at any UPI QR";
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
        msg.textContent = e.name === "NotAllowedError" ? "Camera is blocked. Use a photo or a UPI ID." : "Couldn't start the camera.";
      }
    }

    async function fromImage(file) {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = async () => {
        const scale = Math.min(1, 1200 / Math.max(img.width, img.height));
        const code = await decodeFrame(img, Math.round(img.width * scale), Math.round(img.height * scale));
        URL.revokeObjectURL(url);
        if (code) handleCode(code); else err("No QR code found in that photo. Try a closer, clearer one.");
      };
      img.src = url;
    }

    async function handleCode(code, prefillAmount) {
      if (!code) return;
      try {
        const d = await api("/api/pay/parse", { method: "POST", body: { code } });
        if (d.amount == null && prefillAmount) d.amount = prefillAmount;
        showPayee(d);
      } catch (e) { err(e); }
    }

    // ── 2. Amount
    function showPayee(d) {
      stopCamera();
      const amount = el("input", { class: "pay-amount num", type: "number", inputmode: "decimal", min: "1", max: "100000", step: "0.01",
        value: d.amount || "", placeholder: "0", readonly: d.amount_locked ? true : null, "aria-label": "Amount in rupees" });
      const cat = el("select", { class: "input", "aria-label": "Category" }, m.expense_categories.map((c) => el("option", { value: c, selected: c === d.category ? true : null }, c)));
      const note = el("input", { class: "input", maxlength: "50", placeholder: "Note (optional)", value: d.note || "", "aria-label": "Note" });
      const check = el("div", { class: "pay-check small" });
      const payBtn = el("button", { class: "btn primary lg block", type: "submit" }, "Pay");
      let t;
      const runCheck = () => {
        clearTimeout(t);
        const v = Number(amount.value);
        const who = (d.name || d.vpa.split("@")[0]).split(" ").slice(0, 2).join(" ");
        payBtn.textContent = v > 0 ? `Pay ${inr(v)} to ${who}` : "Enter an amount";
        payBtn.disabled = !(v > 0);
        if (!(v > 0)) { check.replaceChildren(); return; }
        t = setTimeout(async () => {
          try {
            const r = await api("/api/transactions/check", { method: "POST", body: { amount: amount.value, category: cat.value } });
            check.className = "pay-check small " + r.level;
            check.replaceChildren(r.warnings.length ? r.warnings[0] : `Fine. ${inr(r.balance_after)} left after this.`);
          } catch (e) { /* the check is a nice-to-have */ }
        }, 250);
      };
      const fit = () => { amount.style.width = Math.max(2, String(amount.value || "0").length + 0.6) + "ch"; };
      amount.addEventListener("input", () => { fit(); runCheck(); });
      cat.addEventListener("change", runCheck);
      fit();
      const form = el("form", { class: "stack", onsubmit: async (e) => {
        e.preventDefault();
        payBtn.disabled = true;
        try {
          const r = await api("/api/pay/prepare", { method: "POST", body: { vpa: d.vpa, name: d.name, amount: amount.value, category: cat.value, note: note.value } });
          showHandoff(r, d);
        } catch (ex) { err(new Error((ex.message || "Something went wrong.") + " No money has left your account.")); payBtn.disabled = false; }
      } },
        el("div", { class: "pay-who" }, avatar(d.name || d.vpa),
          el("div", { style: { minWidth: 0 } }, el("div", { class: "pay-name" }, d.name || d.vpa), el("div", { class: "tiny faint" }, d.vpa))),
        el("label", { class: "pay-amount-wrap" }, el("span", null, "₹"), amount),
        d.amount_locked ? el("div", { class: "tiny faint", style: { textAlign: "center" } }, "Amount set by the shop") : null,
        check,
        el("div", { class: "grid g-2", style: { gap: "8px" } }, cat, note),
        payBtn,
        el("button", { class: "btn ghost block", type: "button", onclick: () => { history.replaceState(null, "", "/app/pay"); startScreen(); } }, "Scan another code"));
      area.replaceChildren(form);
      runCheck();
      if (!d.amount) amount.focus();
    }

    // ── 3. Pay in the UPI app, then say if it went through
    function showHandoff(r, d) {
      const opened = { at: 0 };
      const markOpened = () => { opened.at = Date.now(); };
      const copy = () => navigator.clipboard && navigator.clipboard.writeText(r.vpa).then(() => ok("UPI ID copied. Paste it in your UPI app."));
      let openers;
      if (IS_ANDROID) {
        openers = el("div", { class: "stack", style: { gap: "8px" } },
          el("a", { class: "btn primary lg block", href: r.links.generic, onclick: markOpened }, `Pay ${inr(r.amount)} in your UPI app`),
          el("div", { class: "app-grid" }, r.links.apps.map((a) => el("a", { class: "app-btn", href: a.android, onclick: markOpened }, a.name))));
      } else if (IS_IOS) {
        openers = el("div", { class: "stack", style: { gap: "8px" } }, el("div", { class: "tiny faint", style: { textAlign: "center" } }, "Choose your UPI app"),
          el("div", { class: "app-grid" }, r.links.apps.map((a) => el("a", { class: "app-btn", href: a.ios, onclick: markOpened }, a.name))));
      } else {
        openers = el("div", { class: "notice info" }, el("div", null, "UPI apps open on phones. Pay ", el("b", null, r.vpa), " from your phone, then come back and tap Yes.",
          el("div", { style: { marginTop: "8px" } }, el("button", { class: "btn sm", type: "button", onclick: copy }, "Copy UPI ID"))));
      }
      const yes = el("button", { class: "btn primary block", onclick: () => finish("paid") }, icon("check"), "Yes, it's paid");
      const confirmBox = el("div", { class: "pay-confirm" },
        el("div", { class: "pay-q" }, "Did it go through?"),
        el("div", { class: "grid g-2", style: { gap: "8px" } }, yes, el("button", { class: "btn block", onclick: () => finish("failed") }, "No")));
      async function finish(status) {
        try {
          await api(`/api/pay/${r.payment_id}/confirm`, { method: "POST", body: { status } });
          if (status === "paid") { ok(`Logged ${inr(r.amount)} to ${r.name}.`); setTimeout(() => (location.href = "/app"), 900); }
          else if (status === "failed") { ok("Okay, nothing was logged. If your bank took the money anyway, it must come back within 1 working day (RBI rule)."); history.replaceState(null, "", "/app/pay"); startScreen(); }
          else { ok("Cancelled. Nothing was logged."); history.replaceState(null, "", "/app/pay"); startScreen(); }
        } catch (e) { err(e); }
      }
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && opened.at && Date.now() - opened.at > 1500) yes.focus();
      });
      area.replaceChildren(
        el("div", { class: "pay-sum" },
          el("div", { class: "tiny faint" }, "You're paying"),
          el("div", { class: "pay-big num" }, inr(r.amount)),
          el("div", { class: "small muted" }, r.name, " · ", r.vpa)),
        openers,
        IS_MOBILE ? el("p", { class: "tiny faint", style: { textAlign: "center", margin: "10px 0 0" } },
          d && !d.is_merchant ? "Some apps don't allow paying a person from a link. " : "App didn't open? ",
          el("button", { class: "link-inline", type: "button", onclick: copy }, "Copy the UPI ID"), " and pay in the app.") : null,
        confirmBox,
        el("button", { class: "btn ghost block", style: { marginTop: "8px" }, onclick: () => finish("cancelled") }, "Cancel"));
    }
  }

  window.addEventListener("pagehide", stopCamera);
  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
