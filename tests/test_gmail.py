"""Gmail connect: OAuth state check, encrypted token, sync turns bank emails into transactions once."""
import base64
from datetime import datetime

import pytest

from flux import gmail


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class R:
    def __init__(self, code, data):
        self.status_code, self._d, self.text = code, data, str(data)

    def json(self):
        return self._d


EMAILS = {
    "m1": {"subject": "You have done a UPI txn", "html": "<p>Dear Customer,<br>Rs.120.00 has been debited from account 1234 to VPA swiggy@icici SWIGGY on 03-11-26. Your UPI transaction reference number is 630712345678.</p>"},
    "m2": {"subject": "Credit alert", "plain": "Dear Customer, Rs.500.00 has been credited to your account **1234 by VPA rahul@okaxis RAHUL KUMAR on 02-11-26. Your UPI transaction reference number is 630712345679."},
    "m3": {"subject": "Get 10% cashback", "plain": "Get 10% cashback up to Rs 500 on your next UPI payment! Offer valid till 30 Nov."},
}


class FakeGoogle:
    def __init__(self):
        self.calls = []

    def post(self, url, timeout=None, data=None, **kw):
        self.calls.append(("POST", url, data))
        if url == gmail.TOKEN_URL and data.get("grant_type") == "authorization_code":
            return R(200, {"access_token": "ya29.a", "refresh_token": "1//refresh-secret", "scope": "openid email https://www.googleapis.com/auth/gmail.readonly"})
        if url == gmail.TOKEN_URL:
            return R(200, {"access_token": "ya29.b"})
        return R(200, {})

    def get(self, url, timeout=None, headers=None, params=None):
        self.calls.append(("GET", url, params))
        if url.endswith("/profile"):
            return R(200, {"emailAddress": "riya@gmail.com"})
        if url.endswith("/messages"):
            return R(200, {"messages": [{"id": k} for k in EMAILS]})
        mid = url.rsplit("/", 1)[1]
        e = EMAILS[mid]
        part = {"mimeType": "text/html", "body": {"data": b64(e["html"])}} if "html" in e else {"mimeType": "text/plain", "body": {"data": b64(e["plain"])}}
        return R(200, {"id": mid, "internalDate": str(int(datetime(2026, 11, 3).timestamp() * 1000)),
                       "payload": {"headers": [{"name": "Subject", "value": e["subject"]}], "mimeType": "multipart/alternative", "parts": [part]}})


@pytest.fixture
def google(app, monkeypatch):
    app.config.update(GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="secret")
    fake = FakeGoogle()
    monkeypatch.setattr(gmail, "_http", fake)
    return fake


def test_connect_requires_matching_state(app, client, user, google):
    r = client.get("/gmail/connect")
    assert r.status_code == 302 and "accounts.google.com" in r.headers["Location"] and "gmail.readonly" in r.headers["Location"]
    bad = client.get("/gmail/callback?code=abc&state=forged")
    assert "gmail=error" in bad.headers["Location"]
    assert client.get("/api/gmail").json["connected"] is False


def test_full_connect_sync_and_dedupe(app, client, user, google):
    r = client.get("/gmail/connect")
    state = r.headers["Location"].split("state=")[1].split("&")[0]
    done = client.get(f"/gmail/callback?code=abc&state={state}")
    assert done.headers["Location"].startswith("/app")
    st = client.get("/api/gmail").json
    assert st["connected"] and st["email"] == "riya@gmail.com" and st["imported"] == 2
    # refresh token is encrypted at rest
    from flux.db import get_db
    with app.app_context():
        raw = get_db().execute("SELECT refresh_token FROM gmail_accounts").fetchone()[0]
    assert "refresh-secret" not in raw
    rows = client.get("/api/transactions").json["items"]
    swiggy = [x for x in rows if x["note"] == "Swiggy"][0]
    assert swiggy["amount"] == 120 and swiggy["source"] == "email" and swiggy["category"] == "Food & Dining"
    assert not any("cashback" in (x["note"] or "").lower() for x in rows)       # offers ignored
    # syncing again reads nothing twice; the same payment arriving by SMS is not double counted
    again = client.post("/api/gmail/sync", json={"force": True}).json
    assert again["logged"] == 0
    t = client.post("/api/ingest/token").json["token"]
    sms = app.test_client().post("/api/ingest/sms/" + t, data="Sent Rs.120.00 From HDFC Bank A/C *1234 To SWIGGY On 03/11/26 Ref 630712345678").json
    assert not sms["logged"]


def test_disconnect_revokes_and_forgets(app, client, user, google):
    r = client.get("/gmail/connect")
    state = r.headers["Location"].split("state=")[1].split("&")[0]
    client.get(f"/gmail/callback?code=abc&state={state}")
    assert client.delete("/api/gmail").json["ok"]
    assert any(c[1] == gmail.REVOKE_URL for c in google.calls)
    assert client.get("/api/gmail").json["connected"] is False


def test_html_to_text():
    assert gmail.html_to_text("<p>Rs.120&nbsp;debited<br>to <b>X</b></p><style>p{}</style>") == "Rs.120 debited to X"


def test_big_backlog_is_read_in_small_batches(app, client, user, google, monkeypatch):
    many = {f"x{i}": {"subject": "UPI txn", "plain": f"Rs.{100 + i}.00 has been debited from account 1234 to VPA shop{i}@ybl SHOP on 02-11-26. Your UPI transaction reference number is 6307000{i:05d}."} for i in range(95)}
    monkeypatch.setattr(gmail, "BATCH", 40)
    original = dict(EMAILS)
    EMAILS.clear()
    EMAILS.update(many)
    try:
        r = client.get("/gmail/connect")
        state = r.headers["Location"].split("state=")[1].split("&")[0]
        client.get(f"/gmail/callback?code=abc&state={state}")           # first batch only: the redirect is quick
        assert client.get("/api/gmail").json["imported"] == 40
        r2 = client.post("/api/gmail/sync", json={"force": True}).json
        assert r2["more"] is True and r2["logged"] == 40
        r3 = client.post("/api/gmail/sync", json={"force": True}).json
        assert r3["more"] is False and r3["logged"] == 15
        assert client.get("/api/gmail").json["imported"] == 95
    finally:
        EMAILS.clear()
        EMAILS.update(original)
