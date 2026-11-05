"""Automatic transaction logging from bank SMS, without opening Flux.

iPhone: a Shortcuts automation ("When I get a message containing 'debited'… → Get contents
of URL") POSTs the SMS text here. Android: any SMS-forwarder app can do the same.

Auth is a personal bearer token (no cookies), so this endpoint is exempt from CSRF.
Only a SHA-256 hash of the token is stored; it can be revoked from Settings any time.
"""
import hashlib
import re
import secrets

from flask import Blueprint, jsonify, request

from .. import finance
from ..db import get_db
from ..finance import rupees
from ..security import ApiError, client_ip, current_user, limiter, login_required, rate_limit
from ..sms import parse_sms
from .statement import _hash
from ..observability import count_ingest

bp = Blueprint("ingest", __name__, url_prefix="/api")
PREFIX = "flx_"


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


@bp.get("/ingest/token")
@login_required
def token_status():
    row = get_db().execute("SELECT created_at, last_used_at, uses FROM ingest_tokens WHERE user_id = ?",
                           (current_user()["id"],)).fetchone()
    return jsonify({"active": bool(row), **(dict(row) if row else {})})


@bp.post("/ingest/token")
@login_required
@rate_limit(10, 3600, scope="ingest_token")
def create_token():
    """Create (or rotate) the token. The plain token is returned exactly once."""
    token = PREFIX + secrets.token_urlsafe(32)
    db = get_db()
    db.execute("INSERT INTO ingest_tokens (user_id, token_hash) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET"
               " token_hash = excluded.token_hash, created_at = datetime('now'), last_used_at = NULL, uses = 0",
               (current_user()["id"], _digest(token)))
    from .. import analytics

    analytics.track(current_user()["id"], "connected", "phone")
    db.commit()
    base = request.host_url.rstrip("/")
    return jsonify({"token": token, "url": base + "/api/ingest/sms", "iphone_url": f"{base}/api/ingest/sms/{token}",
                    "server": base})


@bp.delete("/ingest/token")
@login_required
def revoke_token():
    get_db().execute("DELETE FROM ingest_tokens WHERE user_id = ?", (current_user()["id"],))
    get_db().commit()
    return jsonify({"active": False})


def _user_from_token(path_token=None):
    auth = request.headers.get("Authorization", "")
    token = path_token or (auth[7:].strip() if auth.lower().startswith("bearer ") else "")
    # Tokens carry 256 bits of randomness, so guessing is hopeless; this cap just sheds junk
    # traffic. A *valid* token is never blocked, even if someone on the same carrier NAT IP sprays.
    bad_key = f"ingest_bad_token:{client_ip()}"
    row = None
    if token.startswith(PREFIX) and len(token) <= 100:   # one indexed lookup on a hash – cheap
        row = get_db().execute("SELECT user_id FROM ingest_tokens WHERE token_hash = ?", (_digest(token),)).fetchone()
    if row is None:
        if limiter.peek(bad_key) >= 30:
            raise ApiError("Too many requests. Please wait a moment and try again.", 429)
        limiter.hit(bad_key, 10**9, 600)
        raise ApiError("Missing or invalid token.", 401)
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    db.execute("UPDATE ingest_tokens SET last_used_at = datetime('now'), uses = uses + 1 WHERE user_id = ?", (user["id"],))
    return user


@bp.get("/ingest/ping")
@rate_limit(30, 60, scope="ingest_ping", by="token")
def ingest_ping():
    """Lets the Android app / Shortcut check that the token works, without logging anything."""
    user = _user_from_token()
    get_db().commit()
    return jsonify({"ok": True, "name": user["name"].split()[0]})


SMS_APPS = {"com.google.android.apps.messaging", "com.samsung.android.messaging"}


def ingest_row(user, row, source):
    """Log one parsed transaction (from SMS or a notification) with de-duplication + balance capture."""
    from .. import ledger

    db = get_db()
    amount = round(row["amount"] * 100)
    h = _hash(user["id"], row)
    if row.get("posted_at"):  # the phone's notification timestamp tells two identical ₹20 chai payments apart
        h = _hash(user["id"], {**row, "raw": f"{row['raw']}|{row['posted_at']}"})
    if db.execute("SELECT 1 FROM transactions WHERE user_id = ? AND import_hash = ?", (user["id"], h)).fetchone():
        count_ingest(source, "duplicate")
        return {"logged": False, "reason": "Already logged."}
    origin = row.get("origin") or source
    dup = ledger.find_duplicate(user["id"], row["kind"], amount, row["date"], row.get("ref"), source, origin=origin)
    if dup:
        # Same payment seen another way (e.g. Scan & Pay, then the bank SMS). Keep one record,
        # but enrich it with the bank reference and the balance the bank reported.
        if row.get("ref"):
            db.execute("UPDATE transactions SET ref = COALESCE(ref, ?) WHERE id = ? AND user_id = ?", (row["ref"], dup, user["id"]))
        if row.get("balance") is not None:
            ledger.record_snapshot(user["id"], round(row["balance"] * 100), row["date"], source, row.get("account_last4"), dup)
        count_ingest(source, "duplicate")
        return {"logged": False, "reason": "Already logged from another source (matched and enriched).", "transaction_id": dup}
    learned = finance.rule_category(user["id"], row["note"], row["kind"])
    if learned:
        row["category"] = learned
    res = finance.add_transaction(user, row["kind"], amount, row["category"], row["note"], row["date"],
                                  source=source, import_hash=h, ref=row.get("ref"), origin=origin, commit=False,
                                  auto_category=row["category"])
    if user["contribute_samples"] and row.get("sample_text"):
        from upi_parse import mask_text

        db.execute("INSERT INTO parse_samples (user_id, transaction_id, source, masked_text) VALUES (?,?,?,?)",
                   (user["id"], res["id"], source, mask_text(row["sample_text"])[:600]))
    if row.get("balance") is not None:
        ledger.record_snapshot(user["id"], round(row["balance"] * 100), row["date"], source, row.get("account_last4"), res["id"])
    if row["kind"] == "income" and (row.get("category") == "Refund" or re.search(r"refund|revers", row.get("raw", ""), re.I)):
        from .. import checks

        checks.resolve_by_refund(user["id"], amount, row["date"])
    count_ingest(source, "logged")
    from .. import analytics

    analytics.track(user["id"], "auto_payment", source)
    sign = "-" if row["kind"] == "expense" else "+"
    msg = f"Flux logged {sign}₹{row['amount']:,.2f} · {row['note']} ({row['category']})"
    if res["autosaved"]:
        msg += f" · ₹{rupees(res['autosaved']):,.2f} set aside"
    return {"logged": True, "message": msg, "transaction_id": res["id"], "kind": row["kind"], "amount": row["amount"],
            "category": row["category"], "balance": rupees(finance.balance(user["id"]))}


def _message_text():
    """Accept the SMS as JSON {"text": ...}, a form field, or the raw body (iPhone Shortcuts 'File')."""
    data = request.get_json(silent=True)
    if isinstance(data, dict) and data.get("text"):
        return str(data["text"])
    if request.form.get("text"):
        return request.form["text"]
    return request.get_data(as_text=True) or ""


@bp.post("/ingest/sms/<token>")
@rate_limit(60, 60, scope="ingest_sms", by="token")
def ingest_sms_link(token):
    """iPhone one-link setup: the personal link carries the token, so the Shortcut needs no headers."""
    return _ingest_sms(_user_from_token(token))


@bp.post("/ingest/sms")
@rate_limit(60, 60, scope="ingest_sms", by="token")
def ingest_sms():
    return _ingest_sms(_user_from_token())


def _ingest_sms(user):
    db = get_db()
    text = _message_text()
    row = parse_sms(str(text)[:2000])
    if row is not None:
        row["sample_text"] = str(text)[:600]
    if row is None:
        from .. import checks

        watching = checks.detect_failed(user["id"], str(text)[:2000])
        db.commit()
        count_ingest("sms", "watch" if watching else "skipped")
        if not watching:
            from .. import analytics

            analytics.track(user["id"], "message_unread", "sms")
            db.commit()
        if watching:
            return jsonify({"logged": False, "watching": True,
                            "reason": "Failed payment noted. Flux will watch for the money to come back."})
        return jsonify({"logged": False, "reason": "Not a bank transaction (OTPs and offers are ignored)."})
    out = ingest_row(user, row, "sms")
    db.commit()
    return jsonify(out)


@bp.post("/ingest/notification")
@rate_limit(120, 60, scope="ingest_notification", by="token")
def ingest_notification():
    """Called by the Flux Android companion app (NotificationListenerService)."""
    from upi_parse import NOTIFICATION_PACKAGES, parse_notification

    from .. import clock

    user = _user_from_token()
    db = get_db()
    data = request.get_json(silent=True) or {}
    package = str(data.get("package", ""))[:120]
    if package not in NOTIFICATION_PACKAGES:
        db.commit()
        count_ingest("notification", "rejected")
        return jsonify({"logged": False, "reason": "App not supported."})
    tx = parse_notification(str(data.get("title", ""))[:300], str(data.get("body", ""))[:1000], package, clock.today())
    if tx is None:
        from .. import checks

        checks.detect_failed(user["id"], f"{str(data.get('title', ''))[:300]}. {str(data.get('body', ''))[:1000]}")
        db.commit()
        count_ingest("notification", "skipped")
        return jsonify({"logged": False, "reason": "Not a completed payment."})
    row = {"date": (tx.txn_date or clock.today()).isoformat(), "kind": "expense" if tx.is_debit else "income", "amount": float(tx.amount),
           "category": tx.category, "note": (tx.merchant or tx.extra.get("app") or "UPI payment")[:60], "raw": tx.raw[:120],
           "ref": tx.reference, "balance": float(tx.balance) if tx.balance is not None else None,
           "account_last4": tx.account_last4,
           # A bank SMS displayed by the Messages app is the same channel as a forwarded SMS.
           "origin": "sms" if package in SMS_APPS else package,
           "posted_at": str(data.get("posted_at", ""))[:20] or None,
           "sample_text": f"{str(data.get('title', ''))[:200]}. {str(data.get('body', ''))[:400]}".strip(". ")}
    out = ingest_row(user, row, "notification")
    db.commit()
    return jsonify(out)
