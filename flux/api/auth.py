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
        "features": {"pay": bool(current_app.config.get("FEATURE_PAY")),
                     "gmail": bool(current_app.config.get("GOOGLE_CLIENT_ID") and current_app.config.get("GOOGLE_CLIENT_SECRET")),
                     "invest": bool(current_app.config.get("FEATURE_INVEST"))},
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
    if "onboarded" in data:
        fields["onboarded"] = 1 if data["onboarded"] else 0
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
    resp = jsonify({"profile": user_json(u), "transactions": tx, "budgets": budgets, "merchant_rules": rules,
                    "masked_samples": samples,
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
    db.execute("DELETE FROM users WHERE id = ?", (uid,))  # cascades to all user data
    db.commit()
    session.clear()
    return jsonify({"ok": True})
