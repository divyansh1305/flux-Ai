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
