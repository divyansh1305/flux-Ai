"""Regression tests: one for each security hole found in the original Flux code."""
import base64
import json

from conftest import Client, login


def test_forged_google_token_is_rejected(app, client):
    """Old bug: /api/google-login decoded the JWT without checking its signature."""
    app.config["GOOGLE_CLIENT_ID"] = "123-test.apps.googleusercontent.com"
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    forged = b({"alg": "none"}) + "." + b({"email": "victim@example.com", "email_verified": True}) + ".x"
    r = client.post("/api/auth/google", json={"credential": forged})
    assert r.status_code == 401
    assert client.get("/api/auth/me").json["user"] is None


def test_otp_is_never_returned_in_response(client):
    """Old bug: when SMTP failed the API sent the OTP back to the browser."""
    r = client.post("/api/auth/otp/request", json={"email": "a@example.com", "name": "A"})
    assert r.status_code == 200
    assert "otp" not in r.json and "code" not in r.json
    assert not any(ch.isdigit() for ch in json.dumps(r.json))


def test_otp_is_stored_hashed(app, client, monkeypatch):
    import flux.api.auth as auth
    from flux.db import get_db

    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 654321)
    client.post("/api/auth/otp/request", json={"email": "h@example.com", "name": "H"})
    with app.app_context():
        row = get_db().execute("SELECT code_hash FROM otp_codes WHERE email='h@example.com'").fetchone()
    assert "654321" not in row["code_hash"] and len(row["code_hash"]) == 64


def test_otp_brute_force_is_blocked(client, monkeypatch):
    """Old bug: unlimited guesses on a 6-digit code."""
    import flux.api.auth as auth

    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 111111)
    client.post("/api/auth/otp/request", json={"email": "b@example.com", "name": "B"})
    for _ in range(5):
        assert client.post("/api/auth/otp/verify", json={"email": "b@example.com", "code": "000000"}).status_code == 400
    # Even the right code fails after 5 wrong attempts.
    r = client.post("/api/auth/otp/verify", json={"email": "b@example.com", "code": "111111"})
    assert r.status_code in (400, 429)
    assert client.get("/api/auth/me").json["user"] is None


def test_otp_expires(app, client, monkeypatch):
    import flux.api.auth as auth
    from flux.db import get_db

    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 222222)
    client.post("/api/auth/otp/request", json={"email": "e@example.com", "name": "E"})
    with app.app_context():
        get_db().execute("UPDATE otp_codes SET expires_at = 0")
        get_db().commit()
    assert client.post("/api/auth/otp/verify", json={"email": "e@example.com", "code": "222222"}).status_code == 400


def test_no_admin_panel(client):
    """Old bug: /api/admin/users listed every user with no login."""
    assert client.get("/api/admin/users").status_code == 404
    assert client.get("/admin").status_code == 404


def test_api_requires_login(client):
    for url in ["/api/dashboard", "/api/transactions", "/api/goals", "/api/budgets", "/api/account/export"]:
        assert client.get(url).status_code == 401, url
    assert client.post("/api/voice/command", json={"text": "balance"}).status_code == 401


def test_app_pages_redirect_when_logged_out(client):
    r = client.get("/app")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_csrf_required_for_writes(client, user):
    r = client.c.post("/api/transactions", json={"kind": "income", "amount": 100, "category": "Salary"})
    assert r.status_code == 403
    r = client.post("/api/transactions", json={"kind": "income", "amount": 100, "category": "Salary"})
    assert r.status_code == 201


def test_users_cannot_see_each_others_data(app, monkeypatch):
    a, b = Client(app), Client(app)
    login(a, monkeypatch, "a@example.com", "Alice", 100001)
    login(b, monkeypatch, "b@example.com", "Bob", 100002)
    tx = a.post("/api/transactions", json={"kind": "income", "amount": 5000, "category": "Salary"}).json
    goal = a.post("/api/goals", json={"title": "Laptop", "target": 50000}).json
    assert b.get("/api/transactions").json["items"] == []
    assert b.delete(f"/api/transactions/{tx['transaction']['id']}").status_code == 404
    assert b.post(f"/api/goals/{goal['id']}/contribute", json={"amount": 10}).status_code == 404
    assert b.post("/api/voice/undo", json={"type": "goal", "id": goal["id"]}).status_code == 404
    assert len(a.get("/api/goals").json) == 1


def test_no_free_pro_or_fake_verification_endpoints(client, user):
    """Old bugs: free Pro via /api/verify-pro-payment and hardcoded '123456' verification."""
    assert client.post("/api/verify-pro-payment", json={}).status_code == 404
    assert client.post("/api/security/verify-email", json={"otp": "123456"}).status_code == 404


def test_security_headers(app):
    r = app.test_client().get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    ck = r.headers.getlist("Set-Cookie")
    assert any("flux_session" in c and "HttpOnly" in c for c in ck)


def test_session_rotates_on_login(client, monkeypatch):
    before = client.c.get_cookie("flux_session").value
    login(client, monkeypatch)
    assert client.c.get_cookie("flux_session").value != before


def test_production_refuses_weak_secret(monkeypatch, tmp_path):
    import pytest

    from flux import create_app
    from flux.config import ConfigError

    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ConfigError):
        create_app({"ENV": "production", "DATABASE": str(tmp_path / "x.db")})


def test_production_without_email_does_not_leak_or_fake(app, client):
    app.config["IS_PRODUCTION"] = True
    r = client.post("/api/auth/otp/request", json={"email": "p@example.com", "name": "P"})
    assert r.status_code == 503


def test_errors_do_not_leak_internals(client, user):
    r = client.post("/api/transactions", data="not json", content_type="application/json")
    assert r.status_code == 400 and "Traceback" not in r.get_data(as_text=True)


def test_csv_export_blocks_formula_injection(client, user):
    client.post("/api/transactions", json={"kind": "income", "amount": 10, "category": "Gift", "note": "=HYPERLINK(1)"})
    body = client.get("/api/transactions/export?format=csv").get_data(as_text=True)
    assert "'=HYPERLINK" in body


def test_delete_account_removes_everything(app, client, user):
    client.post("/api/transactions", json={"kind": "income", "amount": 10, "category": "Gift"})
    assert client.delete("/api/account", json={"confirm": "nope"}).status_code == 400
    assert client.delete("/api/account", json={"confirm": "DELETE"}).status_code == 200
    from flux.db import get_db

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_ingest_limits_are_per_token_not_per_ip_and_token_spraying_is_blocked(app, client, user):
    """Phones behind one carrier NAT IP must not throttle each other; guessing tokens must."""
    t = client.post("/api/ingest/token").json["token"]
    phone = app.test_client()
    # 30 wrong guesses from this IP → further attempts (even with new fake tokens) get 429
    for i in range(30):
        assert phone.post("/api/ingest/sms", json={"text": "x"}, headers={"Authorization": f"Bearer flx_fake{i}"}).status_code == 401
    assert phone.post("/api/ingest/sms", json={"text": "x"}, headers={"Authorization": "Bearer flx_fake_new"}).status_code == 429
    # …but the real user's phone on the same IP still gets through
    assert phone.post("/api/ingest/sms", json={"text": "Your OTP is 1"}, headers={"Authorization": f"Bearer {t}"}).status_code == 200
