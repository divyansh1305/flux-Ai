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
    @login_required
    def wrapped(*args, **kwargs):
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
