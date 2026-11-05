"""Reminders: the few things worth interrupting someone for, sent to their phone once a day.

What Flux sends (each one can be turned off in Settings):
  refunds  - a failed payment's money is past the RBI deadline (T+1 / T+5): ask the bank, ₹100/day applies
  checks   - a double charge or a subscription price rise was found
  bills    - a bill, subscription or your own plan is due tomorrow
  friends  - friends still owe you money (at most once a week), and "Rahul paid you back" when it happens
  weekly   - Sunday: last week in a few lines
  morning  - today's safe-to-spend number

Rules: at most 3 phone notifications a day, the same reminder is never sent twice (notifications.dedupe_key),
and everything also shows in the app, so people who didn't turn on notifications miss nothing.
"""
import logging
import threading
from datetime import date, timedelta

from flask import current_app, g, has_request_context

from . import clock, webpush
from .db import get_db
from .finance import rupees

log = logging.getLogger("flux.reminders")

KINDS = ("refunds", "checks", "bills", "friends", "weekly", "morning")
PRIORITY = {k: i for i, k in enumerate(KINDS)}
MAX_PUSH_PER_DAY = 3


def enabled(user):
    raw = user["reminders"] if "reminders" in user.keys() else ",".join(KINDS)
    return {k for k in str(raw or "").split(",") if k in KINDS}


def _hi(user):
    return ("lang" in user.keys() and user["lang"] == "hinglish")


def _inr(paise):
    return f"₹{rupees(paise):,.0f}"


def _d(iso):
    return date.fromisoformat(iso).strftime("%-d %b")


def build(user, today=None):
    """Everything worth telling this user today, most important first."""
    from . import checks, insights, weekly

    today = today or clock.today()
    uid, on, hi = user["id"], enabled(user), _hi(user)
    db = get_db()
    out = []

    if "refunds" in on:
        for w in db.execute("SELECT * FROM refund_watch WHERE user_id = ? AND status = 'open' AND date <= ? AND date >= ?",
                            (uid, (today - timedelta(days=6)).isoformat(), (today - timedelta(days=45)).isoformat())):
            amt, to = _inr(w["amount"]), (f" to {w['note']}" if w["note"] else "")
            out.append({"kind": "refunds", "key": f"refund-late:{w['id']}", "url": "/app",
                        "title": f"{amt} refund late hai" if hi else f"Your {amt} refund is late",
                        "body": (f"{_d(w['date'])} ka failed payment{to} abhi tak wapas nahi aaya. Bank se reversal maango: "
                                 "RBI rule se ₹100 roz ka compensation banta hai." if hi else
                                 f"The failed payment{to} on {_d(w['date'])} hasn't come back. Ask your bank for the "
                                 "reversal: RBI rules give you ₹100 for each day of delay.")})

    if "checks" in on:
        hidden = checks._dismissed(uid)
        for c in checks.double_charges(uid) + checks.price_rises(uid):
            if c["key"] in hidden:
                continue
            out.append({"kind": "checks", "key": f"check:{c['key']}"[:120], "url": "/app",
                        "title": c["title"], "body": c["body"][:180]})

    if "bills" in on:
        tomorrow = (today + timedelta(days=1)).isoformat()
        due = [f"{b['name']} ₹{b['amount']:,.0f}" for b in insights.recurring(uid) if b["next_date"] == tomorrow]
        due += [f"{p['title']} {_inr(p['amount'])}" for p in db.execute(
            "SELECT title, amount FROM plans WHERE user_id = ? AND done = 0 AND kind = 'spend' AND date = ?", (uid, tomorrow))]
        if due:
            out.append({"kind": "bills", "key": f"due:{tomorrow}", "url": "/app/plans",
                        "title": "Kal ke payments" if hi else "Due tomorrow",
                        "body": ", ".join(due[:4]) + (". Paise pehle se alag rakhe hain." if hi else
                                                      ". Already kept aside in today's number.")})

    if "friends" in on:
        rows = db.execute("SELECT person, amount FROM owed WHERE user_id = ? AND direction = 'they_owe' AND settled_at IS NULL"
                          " AND date <= ? ORDER BY amount DESC", (uid, (today - timedelta(days=3)).isoformat())).fetchall()
        if rows:
            total = sum(r["amount"] for r in rows)
            first = rows[0]["person"].split(" ")[0]
            others = len({r["person"].lower() for r in rows}) - 1
            year, week, _ = today.isocalendar()
            who = first + (f" aur {others} aur" if hi else f" and {others} other{'s' if others > 1 else ''}") if others else first
            out.append({"kind": "friends", "key": f"friends:{year}-{week}", "url": "/app/friends",
                        "title": f"Doston se {_inr(total)} lene hain" if hi else f"Friends owe you {_inr(total)}",
                        "body": (f"{who} ne abhi tak nahi bheja. Ek tap mein yaad dilao." if hi else
                                 f"{who} still {'has' if not others else 'have'}n't paid. Send a friendly reminder in one tap.")})

    if "weekly" in on and today.weekday() == 6:  # Sunday
        n = weekly.note(user, today)
        if n["has_data"]:
            out.append({"kind": "weekly", "key": f"weekly:{today.isoformat()}", "url": "/app?week=1",
                        "title": "Aapka hafta" if hi else "Your week", "body": " ".join([n["headline"]] + n["lines"][:1])[:180]})

    if "morning" in on:
        sf = insights.safe_to_spend(uid, user)
        if sf["status"] in ("ok", "stop"):
            if sf["status"] == "ok":
                title = (f"Aaj {_inr(round(sf['left_today'] * 100))} safe hai" if hi
                         else f"{_inr(round(sf['left_today'] * 100))} safe to spend today")
                body = (f"{_d(sf['until'])} tak ka hisaab. Bills aur plans pehle se alag rakhe hain." if hi
                        else f"Worked out until {_d(sf['until'])}, with bills and plans already kept aside.")
            else:
                title = "Aaj sirf zaroori kharche" if hi else "Essentials only today"
                body = sf["message"]
            out.append({"kind": "morning", "key": f"morning:{today.isoformat()}", "url": "/app", "title": title, "body": body})

    out.sort(key=lambda x: PRIORITY[x["kind"]])
    return out


# ─── Storing and sending ──────────────────────────────────────
def queue(user_id, item):
    """Save a reminder (once per dedupe key). Returns its id, or None if it was already made before."""
    cur = get_db().execute(
        "INSERT OR IGNORE INTO notifications (user_id, kind, dedupe_key, title, body, url) VALUES (?,?,?,?,?,?)",
        (user_id, item["kind"], item["key"][:120], item["title"][:120], item["body"][:300], item.get("url") or "/app"))
    return cur.lastrowid if cur.rowcount else None


def _key():
    return webpush.server_key(current_app.instance_path)


def vapid_contact():
    sender = current_app.config.get("MAIL_SENDER")
    return f"mailto:{sender}" if sender else "https://fluxai.pythonanywhere.com"


def push(user_id, notif_id):
    """Send one saved reminder to every phone this user turned reminders on for. Returns phones reached."""
    db = get_db()
    n = db.execute("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (notif_id, user_id)).fetchone()
    if n is None:
        return 0
    payload = {"title": n["title"], "body": n["body"], "url": n["url"], "tag": n["kind"], "id": n["id"]}
    post = current_app.config.get("PUSH_POST")  # tests swap in a fake
    key = _key()
    reached = 0
    for s in db.execute("SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall():
        status = webpush.send(s, payload, key, post=post, contact=vapid_contact())
        if 200 <= status < 300:
            reached += 1
            db.execute("UPDATE push_subscriptions SET last_ok_at = datetime('now'), fails = 0 WHERE id = ?", (s["id"],))
        elif status in (404, 410):  # the phone unsubscribed or the app was removed
            db.execute("DELETE FROM push_subscriptions WHERE id = ?", (s["id"],))
        else:
            db.execute("UPDATE push_subscriptions SET fails = fails + 1 WHERE id = ?", (s["id"],))
            db.execute("DELETE FROM push_subscriptions WHERE id = ? AND fails >= 10", (s["id"],))
    if reached:
        db.execute("UPDATE notifications SET pushed = 1 WHERE id = ?", (notif_id,))
    db.commit()
    return reached


def notify_now(user_id, item):
    """Save now; send to the phone right after the request finishes, so nobody waits on the push service."""
    nid = queue(user_id, item)
    if nid and has_request_context():
        g.setdefault("_push_pending", []).append((user_id, nid))
    return nid


def _send_pending(app, pending):
    with app.app_context():
        for user_id, nid in pending:
            try:
                push(user_id, nid)
            except Exception:  # noqa: BLE001
                log.exception("push after request failed")


def init_app(app):
    @app.after_request
    def _flush(resp):
        pending = g.pop("_push_pending", None)
        if pending and resp.status_code < 400:
            if app.config.get("TESTING"):
                _send_pending(app, pending)
            else:
                threading.Thread(target=_send_pending, args=(app, pending), daemon=True).start()
        return resp


def run_daily(today=None):
    """For the daily task: make today's reminders for everyone and push the most important few."""
    today = today or clock.today()
    db = get_db()
    users = db.execute("SELECT * FROM users WHERE onboarded = 1").fetchall()
    made = pushed = 0
    has_phone = {r[0] for r in db.execute("SELECT DISTINCT user_id FROM push_subscriptions")}
    for u in users:
        try:
            new = []
            for item in build(u, today):
                nid = queue(u["id"], item)
                if nid:
                    new.append(nid)
            db.commit()
            made += len(new)
            if u["id"] in has_phone:
                # Only the daily kind counts toward the cap; "reminders are on" and "Rahul paid you back" don't.
                sent_today = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND pushed = 1"
                                        " AND date(created_at) = date('now') AND dedupe_key NOT LIKE 'hello:%'"
                                        " AND dedupe_key NOT LIKE 'paid-back:%'", (u["id"],)).fetchone()[0]
                for nid in new[:max(0, MAX_PUSH_PER_DAY - sent_today)]:
                    if push(u["id"], nid):
                        pushed += 1
        except Exception:  # noqa: BLE001 - one user's data must never stop everyone else's reminders
            db.rollback()
            log.exception("reminders failed for a user")
    return {"users": len(users), "made": made, "pushed": pushed}


def inbox(user_id, days=14):
    rows = get_db().execute(
        "SELECT id, kind, title, body, url, read_at, created_at FROM notifications WHERE user_id = ?"
        " AND created_at >= datetime('now', ?) ORDER BY id DESC LIMIT 30", (user_id, f"-{days} days")).fetchall()
    return [{"id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"], "url": r["url"],
             "read": r["read_at"] is not None, "created_at": r["created_at"]} for r in rows]
