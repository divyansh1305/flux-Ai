"""Flux — spend smarter, save automatically."""
import os

from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import Config
from .db import init_db
from .security import (ApiError, apply_security_headers, check_csrf, current_user, ensure_csrf_token,
                       set_csrf_cookie)

PAGES_DIR = os.path.join(os.path.dirname(__file__), "pages")

PUBLIC_PAGES = {"/": "landing.html", "/login": "login.html", "/privacy": "privacy.html"}
APP_PAGES = {
    "/onboarding": "onboarding.html",
    "/app": "dashboard.html",
    "/app/transactions": "transactions.html",
    "/app/budgets": "budgets.html",
    "/app/goals": "goals.html",
    "/app/import": "import.html",
    "/app/coach": "coach.html",
    "/app/pay": "pay.html",
    "/app/invest": "invest.html",
    "/app/share": "share.html",
    "/app/settings": "settings.html",
}


def create_app(overrides=None):
    from dotenv import load_dotenv

    load_dotenv()
    cfg = Config(overrides)
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(cfg.as_flask_dict())
    from . import observability

    observability.configure_logging()

    if cfg.IS_PRODUCTION:
        from werkzeug.middleware.proxy_fix import ProxyFix

        # Render's proxy = 1 hop. Behind Cloudflare too, set TRUSTED_PROXY_HOPS=2 so rate limits see the real
        # user IP instead of Cloudflare's (otherwise everyone on one Cloudflare edge would share a limit).
        hops = max(1, min(3, int(os.environ.get("TRUSTED_PROXY_HOPS", "1"))))
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)

    init_db(app)
    observability.init_app(app)   # first before_request: request id + timer
    from . import backup

    backup.init_app(app)

    from .api import auth, ingest, invest, money, pay, statement, voice

    for bp in (auth.bp, money.bp, statement.bp, voice.bp, pay.bp, invest.bp, ingest.bp):
        app.register_blueprint(bp)

    @app.before_request
    def _before():
        check_csrf()

    @app.after_request
    def _after(resp):
        set_csrf_cookie(resp)
        return apply_security_headers(resp)

    # ─── Pages ────────────────────────────────────────────────
    def page(name):
        resp = send_from_directory(PAGES_DIR, name)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    for path, name in PUBLIC_PAGES.items():
        def public_view(name=name, path=path):
            if path in ("/", "/login") and current_user() is not None:
                return redirect("/app")
            ensure_csrf_token()
            return page(name)

        app.add_url_rule(path, f"page_{name}", public_view)

    for path, name in APP_PAGES.items():
        def app_view(name=name):
            if current_user() is None:
                return redirect("/login")
            return page(name)

        app.add_url_rule(path, f"page_{name}", app_view)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest",
                                   mimetype="application/manifest+json")

    # ─── Errors: clean JSON for the API, never a stack trace ──
    @app.errorhandler(ApiError)
    def _api_error(e):
        return jsonify({"error": e.message}), e.status

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if request.path.startswith("/api/"):
            msg = "File too large (max 2 MB)." if e.code == 413 else (e.description or e.name)
            return jsonify({"error": msg}), e.code
        if e.code == 404:
            return send_from_directory(PAGES_DIR, "404.html"), 404
        return e

    @app.errorhandler(Exception)
    def _crash(e):
        app.logger.exception("Unhandled error on %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Something went wrong on our side. Please try again."}), 500
        return "Something went wrong. Please try again.", 500

    return app
