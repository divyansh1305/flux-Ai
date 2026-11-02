"""Security layer: auth guard, CSRF, rate limiting, security headers, input validation."""
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import wraps

from flask import abort, g, request, session

from .db import get_db
from . import clock

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_COOKIE = "flux_csrf"
CSRF_HEADER = "X-CSRF-Token"


class ApiError(Exception):
    """Raised anywhere in a request to return a clean JSON error."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ─── Authentication ────────────────────────────────────────────
def current_user():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    user = None
    if uid:
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if user is None:  # account deleted while session alive
            session.clear()
    g.user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            raise ApiError("Please sign in.", 401)
        return view(*args, **kwargs)

    return wrapped


def start_session(user_id):
    """Rotate the session on login so an old cookie can't be reused (session fixation)."""
    session.clear()
    session.permanent = True
    session["uid"] = user_id
    session["csrf"] = secrets.token_urlsafe(32)


# ─── CSRF (double-submit token tied to the session) ───────────
def ensure_csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method in SAFE_METHODS or not request.path.startswith("/api/"):
        return
    if request.path in ("/api/ingest/sms", "/api/ingest/notification"):  # bearer token, no cookies -> no CSRF
        return
    sent = request.headers.get(CSRF_HEADER, "")
    expected = session.get("csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        raise ApiError("Security check failed. Refresh the page and try again.", 403)


def set_csrf_cookie(response):
    token = ensure_csrf_token()
    if request.cookies.get(CSRF_COOKIE) != token:
        from flask import current_app

        response.set_cookie(
            CSRF_COOKIE,
            token,
            secure=current_app.config["SESSION_COOKIE_SECURE"],
            samesite="Lax",
            httponly=False,  # JS must read it to send the header
        )
    return response


# ─── Rate limiting (in-memory, per process) ───────────────────
class RateLimiter:
    """Sliding-window limiter. For multi-server deployments swap for Redis."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key, limit, window):
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def peek(self, key, window=600):
        """How many hits `key` has in the last `window` seconds (doesn't add one)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            while q and now - q[0] > window:
                q.popleft()
            return len(q)

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip():
    # Behind a proxy (Render/Railway) the real IP is the first X-Forwarded-For entry.
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "unknown")


def _bearer_key():
    """Rate-limit key for token-authenticated endpoints: a hash of the token, not the IP.
    Phones on Jio/Airtel share carrier-grade NAT IPs, so per-IP limits would make
    strangers throttle each other."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 12:
        return "t:" + hashlib.sha256(auth[7:].strip().encode()).hexdigest()[:16]
    return "ip:" + client_ip()


def rate_limit(limit, window, scope=None, by="ip"):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            who = _bearer_key() if by == "token" else client_ip()
            key = f"{scope or view.__name__}:{who}"
            if not limiter.hit(key, limit, window):
                raise ApiError("Too many requests. Please wait a moment and try again.", 429)
            return view(*args, **kwargs)

        return wrapped

    return decorator


# ─── Security headers ─────────────────────────────────────────
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://accounts.google.com/gsi/client https://kite.trade",
        "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style",
        "img-src 'self' data: blob: https://*.googleusercontent.com https://kite.trade https://*.zerodha.com",
        "font-src 'self'",
        "connect-src 'self' https://accounts.google.com/gsi/ https://kite.trade",
        "frame-src https://accounts.google.com/gsi/ https://kite.trade https://kite.zerodha.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self' https://kite.trade https://kite.zerodha.com",
        "object-src 'none'",
    ]
)


def apply_security_headers(response):
    from flask import current_app

    h = response.headers
    h["Content-Security-Policy"] = CSP
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "microphone=(self), camera=(self), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    if current_app.config.get("IS_PRODUCTION"):
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"
    return response


# ─── Input validation ─────────────────────────────────────────
MAX_AMOUNT_PAISE = 10_000_000_00  # ₹1 crore per entry


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Expected a JSON body.")
    return data


def parse_amount(value, field="amount", allow_zero=False):
    """Rupees (number or string like '1,250.50') -> paise int."""
    if isinstance(value, bool) or value is None:
        raise ApiError(f"{field} is required.")
    try:
        rupees = float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        raise ApiError(f"{field} must be a number.")
    if rupees != rupees or rupees in (float("inf"), float("-inf")):
        raise ApiError(f"{field} must be a number.")
    paise = round(rupees * 100)
    if paise < 0 or (paise == 0 and not allow_zero):
        raise ApiError(f"{field} must be more than zero.")
    if paise > MAX_AMOUNT_PAISE:
        raise ApiError(f"{field} is too large.")
    return paise


def parse_date(value, field="date"):
    if not value:
        return clock.today().isoformat()
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(f"{field} must be YYYY-MM-DD.")
    if d.year < 2000 or d > clock.today().replace(year=clock.today().year + 1):
        raise ApiError(f"{field} is out of range.")
    return d.isoformat()


def clean_text(value, field, max_len, required=False):
    text = "" if value is None else str(value).strip()
    text = "".join(ch for ch in text if ch.isprintable())
    if required and not text:
        raise ApiError(f"{field} is required.")
    if len(text) > max_len:
        raise ApiError(f"{field} must be at most {max_len} characters.")
    return text


def owned_or_404(table, row_id, user_id):
    if table not in {"goals", "transactions", "merchant_rules"}:
        abort(500)
    row = get_db().execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (row_id, user_id)
    ).fetchone()
    if row is None:
        raise ApiError("Not found.", 404)
    return row
