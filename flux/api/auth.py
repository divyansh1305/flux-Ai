"""Sign-in: email one-time codes and Google Sign-In, plus account settings."""
import hashlib
import hmac
import logging
import re
import secrets
import time

from flask import Blueprint, current_app, jsonify, session

from .. import emailer
from ..db import get_db
from ..finance import goals_with_progress
from ..security import (ApiError, clean_text, current_user, json_body, limiter, login_required,
                        rate_limit, start_session)

from .. import analytics


def _is_admin(u):
    from .admin import is_admin

    return is_admin(u)
bp = Blueprint("auth", __name__, url_prefix="/api")
log = logging.getLogger("flux.auth")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")


def _norm_email(value):
    email = clean_text(value, "Email", 254, required=True).lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address.")
    return email


def _hash_code(email, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def user_json(u):
    return {
        "id": u["id"], "name": u["name"], "email": u["email"], "onboarded": bool(u["onboarded"]),
        "autosave_mode": u["autosave_mode"], "autosave_value": u["autosave_value"],
        "autosave_goal_id": u["autosave_goal_id"], "voice_lang": u["voice_lang"],
        "contribute_samples": bool(u["contribute_samples"]),
        "adult_confirmed": bool(u["adult_confirmed"]),
        "income_pattern": u["income_pattern"], "pay_day": u["pay_day"],
        "expected_income": u["expected_income"] / 100, "cushion": u["cushion"] / 100,
        "lang": u["lang"], "upi_id": u["upi_id"] or "",
    }


@bp.post("/auth/otp/request")
@rate_limit(8, 600, scope="otp_request")
def request_otp():
    data = json_body()
    email = _norm_email(data.get("email"))
    db = get_db()
    cfg = current_app.config
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    name = clean_text(data.get("name"), "Name", 60)
    if not user and not name:
        return jsonify({"needs_name": True})

    now = int(time.time())
    existing = db.execute("SELECT last_sent_at FROM otp_codes WHERE email = ?", (email,)).fetchone()
    if existing and now - existing["last_sent_at"] < cfg["OTP_RESEND_COOLDOWN"]:
        wait = cfg["OTP_RESEND_COOLDOWN"] - (now - existing["last_sent_at"])
        raise ApiError(f"Please wait {wait}s before requesting another code.", 429)
    if not limiter.hit(f"otp_email:{email}", 5, 3600):
        raise ApiError("Too many codes requested for this email. Try again in an hour.", 429)

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.execute(
        "INSERT INTO otp_codes (email, code_hash, expires_at, attempts, last_sent_at, pending_name)"
        " VALUES (?,?,?,0,?,?) ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,"
        " expires_at=excluded.expires_at, attempts=0, last_sent_at=excluded.last_sent_at,"
        " pending_name=excluded.pending_name",
        (email, _hash_code(email, code), now + cfg["OTP_TTL_SECONDS"], now, name or None),
    )
    db.commit()

    minutes = cfg["OTP_TTL_SECONDS"] // 60
    if cfg["MAIL_SENDER"] and cfg["MAIL_PASSWORD"]:
        if not emailer.send_otp(email, code, minutes):
            raise ApiError("We couldn't send the email right now. Please try again.", 502)
        return jsonify({"sent": True})

    if cfg["IS_PRODUCTION"]:
        raise ApiError("Email sign-in isn't configured on this server.", 503)
    # Development only: print to the server terminal. The code is NEVER sent to the browser.
    log.warning("DEV MODE sign-in code for %s: %s", email, code)
    print(f"\n  [Flux dev] Sign-in code for {email}: {code}\n", flush=True)
    return jsonify({"sent": True, "dev_mode": True})


@bp.post("/auth/otp/verify")
@rate_limit(20, 600, scope="otp_verify")
def verify_otp():
    data = json_body()
    email = _norm_email(data.get("email"))
    code = re.sub(r"\D", "", str(data.get("code", "")))
    if len(code) != 6:
        raise ApiError("Enter the 6-digit code.")
    db = get_db()
    cfg = current_app.config
    row = db.execute("SELECT * FROM otp_codes WHERE email = ?", (email,)).fetchone()
    if row is None or row["expires_at"] < time.time():
        raise ApiError("This code has expired. Request a new one.")
    if row["attempts"] >= cfg["OTP_MAX_ATTEMPTS"]:
        db.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
        db.commit()
        raise ApiError("Too many wrong attempts. Request a new code.", 429)
    if not hmac.compare_digest(row["code_hash"], _hash_code(email, code)):
        db.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE email = ?", (email,))
        db.commit()
        left = cfg["OTP_MAX_ATTEMPTS"] - row["attempts"] - 1
        raise ApiError(f"Wrong code. {left} attempt(s) left." if left > 0 else "Wrong code. Request a new one.")

    db.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None:
        name = row["pending_name"] or email.split("@")[0]
        cur = db.execute("INSERT INTO users (email, name) VALUES (?, ?)", (email, name))
        user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        analytics.track(user["id"], "signed_up", "email")
    db.commit()
    start_session(user["id"])
    return jsonify({"user": user_json(user), "redirect": "/app" if user["onboarded"] else "/onboarding"})


@bp.post("/auth/google")
@rate_limit(20, 600, scope="google_login")
def google_login():
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    if not client_id:
        raise ApiError("Google Sign-In isn't configured.", 503)
    token = str(json_body().get("credential", ""))
    if not token or len(token) > 4096:
        raise ApiError("Missing Google credential.")
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token

        # Verifies signature, expiry, issuer AND that the token was issued for OUR app.
        info = id_token.verify_oauth2_token(token, g_requests.Request(), client_id)
    except Exception:
        raise ApiError("Google sign-in failed. Please try again.", 401)
    if not info.get("email") or not info.get("email_verified"):
        raise ApiError("Your Google account email isn't verified.", 401)

    email = info["email"].lower()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None:
        name = clean_text(info.get("name") or email.split("@")[0], "Name", 60) or "Flux user"
        cur = db.execute("INSERT INTO users (email, name) VALUES (?, ?)", (email, name))
        analytics.track(cur.lastrowid, "signed_up", "google")
        db.commit()
        user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    start_session(user["id"])
    return jsonify({"user": user_json(user), "redirect": "/app" if user["onboarded"] else "/onboarding"})


@bp.get("/auth/me")
def me():
    from .. import ai

    u = current_user()
    return jsonify({
        "user": user_json(u) if u else None,
        "google_client_id": current_app.config["GOOGLE_CLIENT_ID"] or None,
        "ai_available": ai.available(),
        "features": {"gmail": bool(current_app.config.get("GOOGLE_CLIENT_ID") and current_app.config.get("GOOGLE_CLIENT_SECRET")),
                     "android_apk": current_app.config.get("ANDROID_APK_URL") or None,
                     "admin": bool(u) and _is_admin(u)},
    })


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


# ─── Account ──────────────────────────────────────────────────
@bp.patch("/account")
@login_required
def update_account():
    u = current_user()
    data = json_body()
    fields = {}
    if "name" in data:
        fields["name"] = clean_text(data["name"], "Name", 60, required=True)
    if "autosave_mode" in data:
        if data["autosave_mode"] not in ("off", "roundup", "percent"):
            raise ApiError("Invalid auto-save mode.")
        fields["autosave_mode"] = data["autosave_mode"]
    if "autosave_value" in data:
        try:
            v = int(data["autosave_value"])
        except (TypeError, ValueError):
            raise ApiError("Auto-save value must be a whole number.")
        mode = fields.get("autosave_mode", u["autosave_mode"])
        if mode == "roundup" and v not in (10, 50, 100):
            raise ApiError("Round-up must be to ₹10, ₹50 or ₹100.")
        if mode == "percent" and not 1 <= v <= 20:
            raise ApiError("Auto-save percent must be between 1 and 20.")
        fields["autosave_value"] = v
    if "autosave_goal_id" in data:
        gid = data["autosave_goal_id"]
        if gid is not None:
            ok = get_db().execute("SELECT 1 FROM goals WHERE id = ? AND user_id = ? AND archived = 0",
                                  (gid, u["id"])).fetchone()
            if not ok:
                raise ApiError("Goal not found.", 404)
        fields["autosave_goal_id"] = gid
    if "voice_lang" in data:
        if data["voice_lang"] not in ("en-IN", "hi-IN"):
            raise ApiError("Voice language must be en-IN or hi-IN.")
        fields["voice_lang"] = data["voice_lang"]
    if "contribute_samples" in data:
        fields["contribute_samples"] = 1 if data["contribute_samples"] is True else 0
        if not fields["contribute_samples"]:  # turning it off deletes what was kept
            get_db().execute("DELETE FROM parse_samples WHERE user_id = ?", (u["id"],))
    if data.get("adult_confirmed") is True:
        fields["adult_confirmed"] = 1
    if "lang" in data:
        if data["lang"] not in ("en", "hinglish"):
            raise ApiError("Language must be English or Hinglish.")
        fields["lang"] = data["lang"]
        analytics.track(u["id"], "lang_set", data["lang"])
    if "upi_id" in data:
        vpa = str(data["upi_id"] or "").strip().lower()
        if vpa and not re.fullmatch(r"[a-z0-9._\-]{2,64}@[a-z][a-z0-9.\-]{1,31}", vpa):
            raise ApiError("That doesn't look like a UPI ID (for example name@okhdfcbank).")
        fields["upi_id"] = vpa or None
    if "income_pattern" in data:
        if data["income_pattern"] not in ("unset", "monthly", "varies"):
            raise ApiError("Choose when your money usually comes in.")
        fields["income_pattern"] = data["income_pattern"]
    if "pay_day" in data:
        pd = data["pay_day"]
        if pd is not None:
            try:
                pd = int(pd)
            except (TypeError, ValueError):
                raise ApiError("Pay day must be a date from 1 to 31.")
            if not 1 <= pd <= 31:
                raise ApiError("Pay day must be a date from 1 to 31.")
        fields["pay_day"] = pd
    for key, label in (("expected_income", "Expected income"), ("cushion", "Safety cushion")):
        if key in data:
            try:
                v = round(float(data[key] or 0) * 100)
            except (TypeError, ValueError):
                raise ApiError(f"{label} must be a number.")
            if not 0 <= v <= 10_000_000_00:
                raise ApiError(f"{label} looks too large.")
            fields[key] = v
    if data.get("current_balance") not in (None, ""):
        # "About how much is in your bank right now?" -> the opening balance that makes Flux show that amount.
        from ..finance import balance, opening_balance

        try:
            target = round(float(data["current_balance"]) * 100)
        except (TypeError, ValueError):
            raise ApiError("Balance must be a number.")
        if not -10_000_000_00 <= target <= 10_000_000_00:
            raise ApiError("Balance looks too large.")
        fields["opening_balance"] = target - (balance(u["id"]) - opening_balance(u["id"]))
    if "onboarded" in data:
        if data["onboarded"] and not (fields.get("adult_confirmed") or u["adult_confirmed"]):
            raise ApiError("Flux is for people aged 18 or older. Please confirm your age to continue.")
        fields["onboarded"] = 1 if data["onboarded"] else 0
    if fields.get("adult_confirmed") and not u["adult_confirmed"]:
        analytics.track(u["id"], "setup_step", "age")
    if "income_pattern" in fields and not u["onboarded"]:
        analytics.track(u["id"], "setup_step", "money")
    if fields.get("onboarded") and not u["onboarded"]:
        analytics.track(u["id"], "setup_step", "done")
    if fields.get("cushion") and fields["cushion"] != u["cushion"]:
        analytics.track(u["id"], "cushion_set")
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)  # keys are whitelisted above
        get_db().execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), u["id"]))
        get_db().commit()
    fresh = get_db().execute("SELECT * FROM users WHERE id = ?", (u["id"],)).fetchone()
    return jsonify({"user": user_json(fresh)})


@bp.get("/account/export")
@login_required
def export_account():
    u = current_user()
    db = get_db()
    tx = [dict(r) for r in db.execute(
        "SELECT kind, amount, category, note, date, goal_id, source FROM transactions WHERE user_id = ? ORDER BY date",
        (u["id"],))]
    for t in tx:
        t["amount"] = t["amount"] / 100
    budgets = [{"category": r["category"], "monthly_limit": r["monthly_limit"] / 100}
               for r in db.execute("SELECT * FROM budgets WHERE user_id = ?", (u["id"],))]
    rules = [{"merchant": r["merchant_key"], "category": r["category"]}
             for r in db.execute("SELECT * FROM merchant_rules WHERE user_id = ?", (u["id"],))]
    samples = [r["masked_text"] for r in db.execute("SELECT masked_text FROM parse_samples WHERE user_id = ?", (u["id"],))]
    plans = [{"kind": r["kind"], "title": r["title"], "amount": r["amount"] / 100, "date": r["date"], "sure": bool(r["sure"]),
              "done": bool(r["done"])} for r in db.execute("SELECT * FROM plans WHERE user_id = ? ORDER BY date", (u["id"],))]
    events = [dict(r) for r in db.execute("SELECT name, prop, created_at FROM events WHERE user_id = ? ORDER BY id", (u["id"],))]
    owed = [{"direction": r["direction"], "person": r["person"], "amount": r["amount"] / 100, "note": r["note"],
             "date": r["date"], "settled_at": r["settled_at"]}
            for r in db.execute("SELECT * FROM owed WHERE user_id = ? ORDER BY date", (u["id"],))]
    notes = [{"kind": r["kind"], "title": r["title"], "body": r["body"], "created_at": r["created_at"]}
             for r in db.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id", (u["id"],))]
    phones = db.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (u["id"],)).fetchone()[0]
    resp = jsonify({"profile": user_json(u), "transactions": tx, "budgets": budgets, "merchant_rules": rules,
                    "masked_samples": samples, "plans": plans, "usage_events": events, "friends": owed,
                    "reminders": notes, "phones_with_reminders": phones,
                    "goals": goals_with_progress(u["id"], include_archived=True)})
    resp.headers["Content-Disposition"] = "attachment; filename=flux-my-data.json"
    return resp


@bp.delete("/account")
@login_required
def delete_account():
    if json_body().get("confirm") != "DELETE":
        raise ApiError('Type DELETE to confirm.')
    uid = current_user()["id"]
    db = get_db()
    from .. import gmail

    gmail.disconnect(uid)  # also revokes Flux's access at Google, not just our copy of the token
    db.execute("DELETE FROM users WHERE id = ?", (uid,))  # cascades to all user data
    db.commit()
    session.clear()
    return jsonify({"ok": True})


@bp.get("/account/knows")
@login_required
def what_flux_knows():
    """Plain answer to "what does Flux have about me?": every source and every kind of record, counted."""
    from .. import gmail

    u = current_user()
    db = get_db()
    count = lambda sql: db.execute(sql, (u["id"],)).fetchone()[0]  # noqa: E731
    token = db.execute("SELECT created_at, last_used_at FROM ingest_tokens WHERE user_id = ?", (u["id"],)).fetchone()
    return jsonify({
        "email": u["email"], "member_since": u["created_at"][:10],
        "sources": {"gmail": gmail.status(u["id"]),
                    "phone": {"connected": bool(token), "last_used_at": token["last_used_at"] if token else None}},
        "counts": {
            "transactions": count("SELECT COUNT(*) FROM transactions WHERE user_id = ?"),
            "plans": count("SELECT COUNT(*) FROM plans WHERE user_id = ?"),
            "goals": count("SELECT COUNT(*) FROM goals WHERE user_id = ?"),
            "budgets": count("SELECT COUNT(*) FROM budgets WHERE user_id = ?"),
            "merchant_rules": count("SELECT COUNT(*) FROM merchant_rules WHERE user_id = ?"),
            "bank_balances": count("SELECT COUNT(*) FROM balance_snapshots WHERE user_id = ?"),
            "masked_samples": count("SELECT COUNT(*) FROM parse_samples WHERE user_id = ?"),
            "usage_events": count("SELECT COUNT(*) FROM events WHERE user_id = ?"),
            "friends": count("SELECT COUNT(*) FROM owed WHERE user_id = ?"),
            "reminders": count("SELECT COUNT(*) FROM notifications WHERE user_id = ?"),
            "phones_with_reminders": count("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?"),
        },
        "contribute_samples": bool(u["contribute_samples"]),
    })
