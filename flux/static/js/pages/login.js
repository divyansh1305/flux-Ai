/* Signing in starts fresh: forget numbers this browser kept from any earlier session. */
try { Object.keys(localStorage).filter((k) => k.startsWith("fluxc:")).forEach((k) => localStorage.removeItem(k)); } catch (e) { /* ignore */ }
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let email = "";

  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)flux_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  async function post(url, body) {
    const res = await fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }
  function showError(msg) { $("error").textContent = msg; $("error").classList.toggle("hidden", !msg); }
  function busy(btn, on, text) { btn.disabled = on; if (text) btn.textContent = text; }

  async function requestCode() {
    showError("");
    const name = $("name").value.trim();
    busy($("email-btn"), true, "Sending…");
    try {
      const r = await post("/api/auth/otp/request", { email, name: name || undefined });
      if (r.needs_name) {
        $("name-field").classList.remove("hidden");
        $("title").textContent = "Create your account";
        $("subtitle").textContent = "Looks like you're new here. What should we call you?";
        $("name").focus();
        busy($("email-btn"), false, "Send code");
        return;
      }
      $("email-form").classList.add("hidden");
      $("code-form").classList.remove("hidden");
      $("title").textContent = "Check your email";
      $("subtitle").textContent = `We sent a code to ${email}. It expires in 10 minutes.`;
      $("dev-note").classList.toggle("hidden", !r.dev_mode);
      $("code").focus();
    } catch (e) {
      showError(e.message);
    }
    busy($("email-btn"), false, $("name-field").classList.contains("hidden") ? "Continue" : "Send code");
  }

  $("email-form").addEventListener("submit", (e) => {
    e.preventDefault();
    email = $("email").value.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email)) return showError("Enter a valid email address.");
    if (!$("name-field").classList.contains("hidden") && !$("name").value.trim()) return showError("Please enter your name.");
    requestCode();
  });

  $("code").addEventListener("input", () => {
    $("code").value = $("code").value.replace(/\D/g, "").slice(0, 6);
    if ($("code").value.length === 6) $("code-form").requestSubmit();
  });

  $("code-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    busy($("code-btn"), true, "Verifying…");
    try {
      const r = await post("/api/auth/otp/verify", { email, code: $("code").value });
      location.href = r.redirect;
    } catch (err) {
      showError(err.message);
      $("code").value = "";
      busy($("code-btn"), false, "Verify and sign in");
    }
  });

  $("resend").addEventListener("click", requestCode);
  $("change-email").addEventListener("click", () => {
    $("code-form").classList.add("hidden");
    $("email-form").classList.remove("hidden");
    $("title").textContent = "Sign in to Kitna";
    $("subtitle").textContent = "We'll email you a 6-digit code. No password needed.";
    $("dev-note").classList.add("hidden");
  });

  // Google Sign-In (only shown when the server has a client ID configured)
  fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).then((me) => {
    if (me.user) { location.href = "/app"; return; }
    if (!me.google_client_id) return;
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => {
      window.google.accounts.id.initialize({
        client_id: me.google_client_id,
        callback: async (resp) => {
          try { const r = await post("/api/auth/google", { credential: resp.credential }); location.href = r.redirect; }
          catch (e) { showError(e.message); }
        },
      });
      window.google.accounts.id.renderButton($("google-btn"), { theme: "filled_black", size: "large", shape: "pill", width: 320 });
      $("google-wrap").classList.remove("hidden");
    };
    document.head.appendChild(s);
  }).catch(() => {});
})();
