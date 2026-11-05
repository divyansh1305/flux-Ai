"""Gmail connect: turn bank alert emails into transactions, with no setup on the phone.

Flow (standard OAuth 2.0 web-server flow, read-only scope):
  /gmail/connect  → Google consent screen → /gmail/callback?code=… → we keep only an
  encrypted refresh token. Each sync searches the inbox for bank-alert words, reads the
  new matching emails once, runs them through upi-parse, and logs real debits/credits
  with the same de-duplication as SMS and notifications. Email content is never stored.

Google rules (honest): gmail.readonly is a "restricted" scope. In Google Cloud "Testing"
mode up to 100 test users can connect (they see an "unverified app" notice). Opening it
to everyone needs Google's verification and a security assessment.
"""
import base64
import hashlib
import html
import logging
import re
import secrets
from datetime import date, datetime, timezone

import requests
from flask import current_app

from .db import get_db

log = logging.getLogger("flux.gmail")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.readonly"
# Words that appear in Indian bank alert emails. Promotions/social tabs are skipped.
QUERY = ('(debited OR credited OR "Sent Rs" OR "Received Rs" OR "UPI" OR "spent on" OR "has been debited") '
         '-category:promotions -category:social -category:forums')
FIRST_SYNC_DAYS = 30
MAX_PER_SYNC = 150
# Emails read per sync call, fetched in parallel. Keeps each call to a second or two, so the one web worker
# on a small server is never stuck for half a minute (the rest are picked up by the next call).
BATCH = 40
PARALLEL = 8
_http = requests.Session()


class GmailError(Exception):
    pass


class GmailReconnect(GmailError):
    """Google no longer accepts Kitna's token (user removed access, or an app in Testing mode hit its 7-day limit)."""


def configured():
    c = current_app.config
    return bool(c.get("GOOGLE_CLIENT_ID") and c.get("GOOGLE_CLIENT_SECRET"))


# ─── token storage (encrypted) ────────────────────────────────
def _fernet():
    from cryptography.fernet import Fernet

    key = hashlib.sha256((current_app.config["SECRET_KEY"] + "|gmail-tokens").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _enc(text):
    return _fernet().encrypt(text.encode()).decode()


def _dec(blob):
    return _fernet().decrypt(blob.encode()).decode()


# ─── OAuth ────────────────────────────────────────────────────
def auth_url(state, redirect_uri, login_hint=None):
    from urllib.parse import urlencode

    q = {"client_id": current_app.config["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri, "response_type": "code",
         "scope": SCOPES, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state}
    if login_hint:
        q["login_hint"] = login_hint
    return AUTH_URL + "?" + urlencode(q)


def new_state():
    return secrets.token_urlsafe(24)


def exchange_code(code, redirect_uri):
    r = _http.post(TOKEN_URL, timeout=15, data={
        "code": code, "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"], "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise GmailError(f"Google said {r.status_code}: {r.text[:200]}")
    data = r.json()
    if "gmail.readonly" not in data.get("scope", ""):
        raise GmailError("Gmail permission wasn't given. Please tick the Gmail box on Google's screen.")
    if not data.get("refresh_token"):
        raise GmailError("Google didn't return a long-term token. Disconnect Kitna in your Google account and try again.")
    return data


def _access_token(refresh_token):
    r = _http.post(TOKEN_URL, timeout=15, data={
        "refresh_token": refresh_token, "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise GmailReconnect("Gmail access was removed or expired. Please connect Gmail again.")
    return r.json()["access_token"]


def _profile_email(access):
    r = _http.get(API + "/profile", timeout=15, headers={"Authorization": f"Bearer {access}"})
    return r.json().get("emailAddress", "") if r.status_code == 200 else ""


def save_account(user_id, token_data):
    access = token_data["access_token"]
    email = _profile_email(access)
    get_db().execute(
        "INSERT INTO gmail_accounts (user_id, email, refresh_token) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET"
        " email = excluded.email, refresh_token = excluded.refresh_token, connected_at = datetime('now'), last_error = NULL,"
        " needs_reconnect = 0",
        (user_id, email or "your Gmail", _enc(token_data["refresh_token"])))
    return email


def disconnect(user_id):
    db = get_db()
    row = db.execute("SELECT refresh_token FROM gmail_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        try:
            _http.post(REVOKE_URL, timeout=10, data={"token": _dec(row["refresh_token"])})
        except Exception:  # still delete locally
            log.warning("could not revoke Gmail token")
    db.execute("DELETE FROM gmail_accounts WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM gmail_seen WHERE user_id = ?", (user_id,))


def status(user_id):
    row = get_db().execute("SELECT * FROM gmail_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {"connected": False, "available": configured()}
    return {"connected": True, "available": True, "email": row["email"], "last_sync_at": row["last_sync_at"],
            "imported": row["imported"], "error": row["last_error"], "needs_reconnect": bool(row["needs_reconnect"])}


# ─── reading emails ───────────────────────────────────────────
def _b64(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</td>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def message_text(payload):
    """Plain text of a Gmail message payload (prefers text/plain, falls back to HTML)."""
    plain, rich = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_b64(data))
        elif data and mime == "text/html":
            rich.append(html_to_text(_b64(data)))
        for p in part.get("parts") or []:
            walk(p)

    walk(payload or {})
    text = " ".join(plain) if plain else " ".join(rich)
    return re.sub(r"\s+", " ", text).strip()


def _subject(payload):
    for h in (payload or {}).get("headers") or []:
        if h.get("name", "").lower() == "subject":
            return h.get("value", "")
    return ""


def sync(user, force=False, min_minutes=10):
    """Fetch new bank-alert emails and log them. Returns counts. Safe to call often."""
    from .api.ingest import ingest_row
    from .sms import parse_sms

    db = get_db()
    acct = db.execute("SELECT * FROM gmail_accounts WHERE user_id = ?", (user["id"],)).fetchone()
    if not acct:
        return {"connected": False}
    if not force and acct["last_sync_at"]:
        last = datetime.fromisoformat(acct["last_sync_at"]).replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last).total_seconds() < min_minutes * 60:
            return {"connected": True, "skipped": "checked recently", "logged": 0}
    try:
        access = _access_token(_dec(acct["refresh_token"]))
        days = FIRST_SYNC_DAYS if not acct["last_sync_at"] else 3
        r = _http.get(API + "/messages", timeout=20, headers={"Authorization": f"Bearer {access}"},
                      params={"q": f"{QUERY} newer_than:{days}d", "maxResults": MAX_PER_SYNC})
        if r.status_code != 200:
            raise GmailError(f"Gmail search failed ({r.status_code}).")
        ids = [m["id"] for m in r.json().get("messages", [])]
        seen = {row["msg_id"] for row in db.execute("SELECT msg_id FROM gmail_seen WHERE user_id = ?", (user["id"],))}
        todo = list(reversed([i for i in ids if i not in seen]))      # oldest first
        batch, more = todo[:BATCH], len(todo) > BATCH

        def fetch(mid):
            try:
                return mid, _http.get(f"{API}/messages/{mid}", timeout=20, headers={"Authorization": f"Bearer {access}"},
                                      params={"format": "full"})
            except requests.RequestException:
                return mid, None

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            fetched = list(pool.map(fetch, batch))                    # network in parallel, database in order
        logged = skipped = 0
        for mid, m in fetched:
            if m is None:  # network hiccup: leave it unseen so the next call retries it
                more = True
                continue
            db.execute("INSERT OR IGNORE INTO gmail_seen (user_id, msg_id) VALUES (?,?)", (user["id"], mid))
            if m.status_code != 200:
                continue
            msg = m.json()
            payload = msg.get("payload") or {}
            text = (_subject(payload) + ". " + message_text(payload))[:3000]
            received = date.fromtimestamp(int(msg.get("internalDate", "0")) / 1000) if msg.get("internalDate") else None
            row = parse_sms(text, received_on=received)
            if row is None:
                from .checks import detect_failed

                if not detect_failed(user["id"], text, received):
                    from .analytics import track

                    track(user["id"], "message_unread", "email")
                skipped += 1
                continue
            row["origin"] = "gmail"
            row["sample_text"] = text[:600]
            out = ingest_row(user, row, "email")
            logged += 1 if out.get("logged") else 0
        if more:  # keep the first-sync window (30 days) and the "check now" path open until the backlog is done
            db.execute("UPDATE gmail_accounts SET imported = imported + ?, last_error = NULL WHERE user_id = ?",
                       (logged, user["id"]))
        else:
            db.execute("UPDATE gmail_accounts SET last_sync_at = ?, imported = imported + ?, last_error = NULL WHERE user_id = ?",
                       (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), logged, user["id"]))
        db.commit()
        return {"connected": True, "logged": logged, "skipped": skipped, "checked": len(batch), "more": more}
    except GmailError as e:
        db.execute("UPDATE gmail_accounts SET last_error = ?, needs_reconnect = ? WHERE user_id = ?",
                   (str(e)[:200], 1 if isinstance(e, GmailReconnect) else 0, user["id"]))
        db.commit()
        return {"connected": True, "error": str(e), "logged": 0, "needs_reconnect": isinstance(e, GmailReconnect)}
    except requests.RequestException:
        log.exception("Gmail sync network error")
        return {"connected": True, "error": "Couldn't reach Gmail right now. Kitna will try again later.", "logged": 0}


def sync_all():
    """For the daily scheduled task: sync every connected account."""
    db = get_db()
    users = db.execute("SELECT u.* FROM users u JOIN gmail_accounts g ON g.user_id = u.id").fetchall()
    out = []
    for u in users:
        for _ in range(10):  # a big backlog is read in batches
            r = sync(u, force=True)
            if not r.get("more"):
                break
        out.append(r)
    return out
