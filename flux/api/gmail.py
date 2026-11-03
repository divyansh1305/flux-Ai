"""Gmail connect routes. Pages: /gmail/connect, /gmail/callback. API: /api/gmail/*."""
from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from .. import gmail
from ..db import get_db
from ..security import current_user, login_required, rate_limit

bp = Blueprint("gmail", __name__)


def _redirect_uri():
    return current_app.config.get("GMAIL_REDIRECT_URI") or url_for("gmail.callback", _external=True)


@bp.get("/gmail/connect")
def connect():
    user = current_user()
    if user is None:
        return redirect("/login")
    if not gmail.configured():
        return redirect("/app/settings#auto")
    session["gmail_state"] = state = gmail.new_state()
    return redirect(gmail.auth_url(state, _redirect_uri(), login_hint=user["email"]))


@bp.get("/gmail/callback")
def callback():
    user = current_user()
    if user is None:
        return redirect("/login")
    expected = session.pop("gmail_state", None)
    if not expected or request.args.get("state") != expected:        # CSRF protection for OAuth
        return redirect("/app/settings?gmail=error#auto")
    if request.args.get("error") or not request.args.get("code"):
        return redirect("/app/settings?gmail=cancelled#auto")
    try:
        data = gmail.exchange_code(request.args["code"], _redirect_uri())
        gmail.save_account(user["id"], data)
        get_db().commit()
    except gmail.GmailError as e:
        current_app.logger.warning("Gmail connect failed: %s", e)
        return redirect("/app/settings?gmail=error#auto")
    gmail.sync(get_db().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone(), force=True)
    return redirect("/app?gmail=connected")


@bp.get("/api/gmail")
@login_required
def status():
    return jsonify(gmail.status(current_user()["id"]))


@bp.post("/api/gmail/sync")
@login_required
@rate_limit(20, 600, scope="gmail_sync")
def sync_now():
    force = bool((request.get_json(silent=True) or {}).get("force"))
    return jsonify(gmail.sync(current_user(), force=force))


@bp.delete("/api/gmail")
@login_required
def disconnect():
    gmail.disconnect(current_user()["id"])
    get_db().commit()
    return jsonify({"ok": True})

