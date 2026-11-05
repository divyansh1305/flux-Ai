"""Friends (money lent and borrowed), reminders (phone notifications) and the weekly note."""
import re

from flask import Blueprint, jsonify

from .. import analytics, friends, reminders, webpush, weekly
from ..db import get_db
from ..security import (ApiError, clean_text, current_user, json_body, login_required, parse_amount, parse_date,
                        rate_limit)

bp = Blueprint("social", __name__, url_prefix="/api")


# ─── Friends ──────────────────────────────────────────────────
@bp.get("/friends")
@login_required
def list_friends():
    u = current_user()
    rows = friends.items(u["id"], include_settled=True)
    return jsonify({"open": [r for r in rows if not r["settled"]], "settled": [r for r in rows if r["settled"]][:20],
                    "totals": friends.totals(u["id"]), "suggestions": friends.suggestions(u["id"]),
                    "upi_id": u["upi_id"] or ""})


@bp.post("/friends")
@login_required
@rate_limit(60, 600, scope="friends_add")
def add_friend():
    data = json_body()
    direction = "i_owe" if data.get("direction") == "i_owe" else "they_owe"
    amount = parse_amount(data.get("amount"), "Amount")
    oid = friends.add(current_user()["id"], clean_text(data.get("person"), "Name", 40, required=True), amount,
                      clean_text(data.get("note"), "What for", 80), direction, parse_date(data.get("date")))
    analytics.track(current_user()["id"], "friend_added", direction)
    return jsonify(friends.row_json(get_db().execute("SELECT * FROM owed WHERE id = ?", (oid,)).fetchone())), 201


@bp.post("/friends/split")
@login_required
@rate_limit(60, 600, scope="friends_split")
def split_payment():
    data = json_body()
    people = []
    for p in data.get("people") or []:
        if not isinstance(p, dict):
            raise ApiError("Bad friend.")
        amount = parse_amount(p.get("amount"), "Share")
        if amount <= 0:
            raise ApiError("Each share must be more than ₹0.")
        people.append({"name": clean_text(p.get("name"), "Name", 40, required=True), "amount": amount})
    try:
        tx_id = int(data.get("transaction_id"))
    except (TypeError, ValueError):
        raise ApiError("Pick a payment to split.")
    ids = friends.split(current_user()["id"], tx_id, people)
    return jsonify({"created": len(ids), "totals": friends.totals(current_user()["id"])}), 201


@bp.post("/friends/<int:oid>/settle")
@login_required
def settle_friend(oid):
    data = json_body()
    tx = data.get("transaction_id")
    return jsonify(friends.settle(current_user()["id"], oid, int(tx) if isinstance(tx, int) else None))


@bp.post("/friends/<int:oid>/not-them")
@login_required
def not_them(oid):
    friends.not_them(current_user()["id"], oid)
    return jsonify({"ok": True})


@bp.delete("/friends/<int:oid>")
@login_required
def delete_friend(oid):
    friends.delete(current_user()["id"], oid)
    return jsonify({"ok": True})


@bp.get("/friends/<int:oid>/message")
@login_required
def friend_message(oid):
    u = current_user()
    r = get_db().execute("SELECT * FROM owed WHERE id = ? AND user_id = ?", (oid, u["id"])).fetchone()
    if r is None:
        raise ApiError("Not found.", 404)
    analytics.track(u["id"], "friend_reminded", "")
    return jsonify({"text": friends.remind_message(u, r, u["lang"])})


# ─── Reminders ────────────────────────────────────────────────
@bp.get("/reminders")
@login_required
def reminder_settings():
    from flask import current_app

    u = current_user()
    phones = get_db().execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (u["id"],)).fetchone()[0]
    items = reminders.inbox(u["id"])
    return jsonify({"public_key": webpush.public_key_b64(webpush.server_key(current_app.instance_path)),
                    "kinds": sorted(reminders.enabled(u), key=reminders.KINDS.index), "all_kinds": list(reminders.KINDS),
                    "phones": phones, "inbox": items, "unread": sum(1 for i in items if not i["read"])})


@bp.patch("/reminders")
@login_required
def set_reminders():
    kinds = json_body().get("kinds")
    if not isinstance(kinds, list) or any(k not in reminders.KINDS for k in kinds):
        raise ApiError("Unknown reminder type.")
    u = current_user()
    get_db().execute("UPDATE users SET reminders = ? WHERE id = ?", (",".join(k for k in reminders.KINDS if k in kinds), u["id"]))
    get_db().commit()
    return jsonify({"kinds": [k for k in reminders.KINDS if k in kinds]})


_B64 = re.compile(r"^[A-Za-z0-9_\-=]+$")


@bp.post("/reminders/subscribe")
@login_required
@rate_limit(20, 600, scope="push_subscribe")
def subscribe():
    data = json_body()
    endpoint = str(data.get("endpoint") or "")
    keys = data.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if len(endpoint) > 1000 or not webpush.allowed_endpoint(endpoint):
        raise ApiError("This browser's notification service isn't supported.")
    try:
        good = bool(_B64.match(p256dh) and _B64.match(auth)) and len(webpush.unb64u(p256dh)) == 65 \
            and len(webpush.unb64u(auth)) == 16
    except ValueError:  # not valid base64 at all
        good = False
    if not good:
        raise ApiError("Bad notification keys from the browser.")
    uid = current_user()["id"]
    db = get_db()
    db.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?,?,?,?)"
               " ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh,"
               " auth = excluded.auth, fails = 0", (uid, endpoint, p256dh, auth))
    db.commit()
    analytics.track(uid, "reminders_on", "")
    nid = reminders.queue(uid, {"kind": "morning", "key": f"hello:{endpoint[-40:]}", "url": "/app/settings",
                                "title": "Reminders are on" if current_user()["lang"] != "hinglish" else "Reminders chalu",
                                "body": "Flux will tell you about bills, late refunds and money friends owe you."
                                if current_user()["lang"] != "hinglish" else
                                "Bills, late refund aur doston ke paise: Flux yaad dilayega."})
    db.commit()
    reached = reminders.push(uid, nid) if nid else 0
    return jsonify({"ok": True, "test_sent": reached > 0})


@bp.post("/reminders/unsubscribe")
@login_required
def unsubscribe():
    endpoint = str(json_body().get("endpoint") or "")
    uid = current_user()["id"]
    db = get_db()
    if endpoint:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (uid, endpoint))
    else:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (uid,))
    db.commit()
    analytics.track(uid, "reminders_off", "")
    return jsonify({"ok": True})


@bp.post("/reminders/read")
@login_required
def mark_read():
    get_db().execute("UPDATE notifications SET read_at = datetime('now') WHERE user_id = ? AND read_at IS NULL",
                     (current_user()["id"],))
    get_db().commit()
    return jsonify({"ok": True})


# ─── Weekly note ──────────────────────────────────────────────
@bp.get("/weekly")
@login_required
def weekly_note():
    analytics.track(current_user()["id"], "weekly_opened", "")
    return jsonify(weekly.note(current_user()))
