"""Product events from the browser, and the private numbers page (totals only, for ADMIN_EMAILS)."""
from functools import wraps

from flask import Blueprint, current_app, jsonify

from .. import analytics
from ..db import get_db
from ..security import ApiError, current_user, json_body, login_required, rate_limit

bp = Blueprint("admin", __name__, url_prefix="/api")


def is_admin(user):
    allowed = {e.strip().lower() for e in (current_app.config.get("ADMIN_EMAILS") or "").split(",") if e.strip()}
    return bool(user) and user["email"].lower() in allowed


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Signed out or not an admin: answer as if the page doesn't exist.
        if not is_admin(current_user()):
            raise ApiError("Not found.", 404)  # don't reveal that the page exists
        return view(*args, **kwargs)
    return wrapped


@bp.post("/events")
@login_required
@rate_limit(120, 600, scope="events")
def client_event():
    data = json_body()
    name = str(data.get("name", ""))[:40]
    if name not in analytics.CLIENT_EVENTS:
        raise ApiError("Unknown event.")
    analytics.track(current_user()["id"], name, str(data.get("prop", ""))[:40])
    get_db().commit()
    return jsonify({"ok": True})


@bp.get("/admin/overview")
@admin_required
def overview():
    return jsonify(analytics.overview())


@bp.post("/admin/rollup")
@admin_required
def rollup_now():
    return jsonify(analytics.nightly())


# ─── Feedback ─────────────────────────────────────────────────
FEEDBACK_KINDS = {"broken": "Something's broken", "confusing": "Confusing", "idea": "Idea", "love": "Love it"}


def _email_admins(app, kind, message, screen, who):
    import threading

    from ..emailer import _template, send_email

    to = [e.strip() for e in (app.config.get("ADMIN_EMAILS") or "").split(",") if e.strip()]
    if not to:
        return

    def run():
        with app.app_context():
            for addr in to:
                import html as _h

                send_email(addr, f"Kitna feedback: {FEEDBACK_KINDS[kind]}", f"{who} on {screen}:\n\n{message}",
                           _template(f"{FEEDBACK_KINDS[kind]} · {screen}",
                                     f"<p style='text-align:left;white-space:pre-wrap'>{_h.escape(message)}</p>"
                                     f"<p>From {_h.escape(who)}. Reply from the numbers page.</p>"))
    if app.config.get("TESTING"):
        return
    threading.Thread(target=run, daemon=True).start()


@bp.post("/feedback")
@login_required
@rate_limit(10, 3600, scope="feedback")
def send_feedback():
    data = json_body()
    kind = data.get("kind")
    if kind not in FEEDBACK_KINDS:
        raise ApiError("Choose what kind of feedback this is.")
    message = "".join(ch for ch in str(data.get("message") or "") if ch.isprintable() or ch == "\n").strip()
    if len(message) < 3:
        raise ApiError("Write a few words so we know what happened.")
    if len(message) > 1500:
        raise ApiError("That's a bit long. Keep it under 1,500 characters.")
    screen = str(data.get("screen") or "")[:40]
    u = current_user()
    db = get_db()
    db.execute("INSERT INTO feedback (user_id, kind, message, screen) VALUES (?,?,?,?)", (u["id"], kind, message, screen))
    analytics.track(u["id"], "feedback_sent", kind)
    db.commit()
    _email_admins(current_app._get_current_object(), kind, message, screen, u["email"])
    return jsonify({"ok": True}), 201


@bp.get("/admin/feedback")
@admin_required
def list_feedback():
    rows = get_db().execute(
        "SELECT f.id, f.kind, f.message, f.screen, f.status, f.created_at, u.email FROM feedback f"
        " JOIN users u ON u.id = f.user_id ORDER BY f.id DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/admin/feedback/<int:fid>/read")
@admin_required
def read_feedback(fid):
    get_db().execute("UPDATE feedback SET status = 'read' WHERE id = ?", (fid,))
    get_db().commit()
    return jsonify({"ok": True})


# ─── Users (support view) ─────────────────────────────────────
# Who uses Kitna and whether it works for them: account, setup, connections, activity counts.
# Deliberately NOT shown: amounts, balances, payment notes, merchants. Kitna promises users that
# their money stays private (privacy policy, DPDP Act 2023); support never needs it.
USER_LIST_SQL = """
SELECT u.id, u.name, u.email, u.created_at, u.onboarded, u.lang,
       (SELECT MAX(created_at) FROM events e WHERE e.user_id = u.id AND e.name = 'screen_opened') AS last_active,
       (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.id) AS payments,
       (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.id AND t.source IN ('sms','notification','email')) AS auto_payments,
       EXISTS (SELECT 1 FROM gmail_accounts g WHERE g.user_id = u.id) AS gmail,
       EXISTS (SELECT 1 FROM ingest_tokens k WHERE k.user_id = u.id) AS phone,
       EXISTS (SELECT 1 FROM push_subscriptions p WHERE p.user_id = u.id) AS reminders
FROM users u
"""


def _user_row(r):
    return {"id": r["id"], "name": r["name"], "email": r["email"], "joined": r["created_at"], "setup_done": bool(r["onboarded"]),
            "lang": r["lang"], "last_active": r["last_active"], "payments": r["payments"], "auto_payments": r["auto_payments"],
            "gmail": bool(r["gmail"]), "phone": bool(r["phone"]), "reminders": bool(r["reminders"])}


@bp.get("/admin/users")
@admin_required
def list_users():
    from flask import request

    q = str(request.args.get("q", "")).strip().lower()[:80]
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    where, args = "", []
    if q:
        where, args = " WHERE lower(u.email) LIKE ? OR lower(u.name) LIKE ?", [f"%{q}%", f"%{q}%"]
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM users u{where}", args).fetchone()[0]
    rows = db.execute(f"{USER_LIST_SQL}{where} ORDER BY u.id DESC LIMIT 50 OFFSET ?", [*args, (page - 1) * 50]).fetchall()
    return jsonify({"total": total, "page": page, "users": [_user_row(r) for r in rows]})


@bp.get("/admin/users.csv")
@admin_required
def export_users():
    import csv
    import io

    from flask import Response

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "email", "joined", "setup_done", "last_active", "payments", "auto_payments", "gmail", "phone_app", "reminders"])
    for r in get_db().execute(f"{USER_LIST_SQL} ORDER BY u.id"):
        u = _user_row(r)
        w.writerow([u["id"], u["name"], u["email"], u["joined"], u["setup_done"], u["last_active"] or "", u["payments"],
                    u["auto_payments"], u["gmail"], u["phone"], u["reminders"]])
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=kitna-users.csv"})


@bp.get("/admin/users/<int:uid>")
@admin_required
def user_detail(uid):
    db = get_db()
    r = db.execute(f"{USER_LIST_SQL} WHERE u.id = ?", (uid,)).fetchone()
    if r is None:
        raise ApiError("No such user.", 404)
    out = _user_row(r)
    u = db.execute("SELECT income_pattern, pay_day, adult_confirmed FROM users WHERE id = ?", (uid,)).fetchone()
    out["money_setup"] = {"income": u["income_pattern"], "pay_day": u["pay_day"], "adult_confirmed": bool(u["adult_confirmed"])}
    g = db.execute("SELECT connected_at, last_sync_at, imported, last_error, needs_reconnect FROM gmail_accounts WHERE user_id = ?", (uid,)).fetchone()
    out["gmail_detail"] = dict(g) if g else None
    t = db.execute("SELECT created_at, last_used_at, uses FROM ingest_tokens WHERE user_id = ?", (uid,)).fetchone()
    out["phone_detail"] = dict(t) if t else None
    out["payments_by_source"] = {s: n for s, n in db.execute(
        "SELECT source, COUNT(*) FROM transactions WHERE user_id = ? GROUP BY source", (uid,))}
    out["unread_messages_30d"] = db.execute(
        "SELECT COUNT(*) FROM events WHERE user_id = ? AND name = 'message_unread' AND created_at >= datetime('now','-30 days')", (uid,)).fetchone()[0]
    out["errors_7d"] = [dict(x) for x in db.execute(
        "SELECT prop AS screen, COUNT(*) AS n FROM events WHERE user_id = ? AND name = 'error_shown' AND created_at >= datetime('now','-7 days')"
        " GROUP BY prop ORDER BY n DESC", (uid,))]
    out["recent_activity"] = [dict(x) for x in db.execute(
        "SELECT name, prop, created_at FROM events WHERE user_id = ? ORDER BY id DESC LIMIT 25", (uid,))]
    out["helper_questions"] = [dict(x) for x in db.execute(
        "SELECT question, lang, answered, created_at FROM help_questions WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid,))]
    out["feedback"] = [dict(x) for x in db.execute(
        "SELECT kind, message, status, created_at FROM feedback WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid,))]
    return jsonify(out)


@bp.get("/admin/help")
@admin_required
def help_questions():
    db = get_db()
    recent = [dict(x) for x in db.execute(
        "SELECT h.question, h.lang, h.answered, h.screen, h.created_at, u.email FROM help_questions h JOIN users u ON u.id = h.user_id"
        " ORDER BY h.id DESC LIMIT 100")]
    langs = {k: n for k, n in db.execute(
        "SELECT lang, COUNT(*) FROM help_questions WHERE created_at >= datetime('now','-30 days') GROUP BY lang")}
    unanswered = db.execute("SELECT COUNT(*) FROM help_questions WHERE answered = 0 AND created_at >= datetime('now','-30 days')").fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM help_questions WHERE created_at >= datetime('now','-30 days')").fetchone()[0]
    return jsonify({"recent": recent, "languages": langs, "unanswered_30d": unanswered, "total_30d": total})
