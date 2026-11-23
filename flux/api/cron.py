"""The once-a-day job, as a web address Vercel Cron calls (there is no always-on server to run scripts).

Vercel sends "Authorization: Bearer $CRON_SECRET". Without a matching secret the address answers 404,
so nobody else can trigger it. Same work as scripts/daily.py: Gmail for everyone, today's reminders,
yesterday's numbers.
"""
import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

from ..security import ApiError

bp = Blueprint("cron", __name__, url_prefix="/api")
log = logging.getLogger("flux.cron")


@bp.get("/cron/daily")
def daily():
    secret = current_app.config.get("CRON_SECRET") or ""
    given = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(given, f"Bearer {secret}"):
        raise ApiError("Not found.", 404)
    from .. import analytics, gmail, reminders

    out = {}
    if gmail.configured():
        try:
            results = gmail.sync_all()
            out["gmail"] = {"accounts": len(results), "logged": sum(r.get("logged", 0) for r in results)}
        except Exception:  # noqa: BLE001  one part failing must not stop the rest
            log.exception("cron: gmail failed")
            out["gmail"] = "failed"
    try:
        out["reminders"] = reminders.run_daily()
    except Exception:  # noqa: BLE001
        log.exception("cron: reminders failed")
        out["reminders"] = "failed"
    out["numbers"] = analytics.nightly()
    return jsonify(out)
