import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flux import create_app  # noqa: E402
from flux.security import limiter  # noqa: E402


class Client:
    """Test client that behaves like the real frontend (sends the CSRF header)."""

    def __init__(self, app):
        self.c = app.test_client()
        self.c.get("/login")  # receive session + CSRF cookie

    @property
    def csrf(self):
        ck = self.c.get_cookie("flux_csrf")
        return ck.value if ck else ""

    def _h(self, kw):
        h = kw.pop("headers", {}) or {}
        h.setdefault("X-CSRF-Token", self.csrf)
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h(kw), **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h(kw), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(kw), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(kw), **kw)


@pytest.fixture
def app(tmp_path, monkeypatch):
    for k in ("EMAIL_SENDER", "EMAIL_PASSWORD", "GEMINI_API_KEY", "GOOGLE_CLIENT_ID", "SECRET_KEY", "FLUX_ENV"):
        monkeypatch.delenv(k, raising=False)
    limiter.reset()
    app = create_app({"DATABASE": str(tmp_path / "test.db"), "TESTING": True,
                      "SECRET_KEY": "test-secret-key-that-is-long-enough-1234", "GEMINI_API_KEY": ""})
    yield app
    limiter.reset()


@pytest.fixture
def client(app):
    return Client(app)


def login(client, monkeypatch, email="riya@example.com", name="Riya Sharma", code=123456):
    import flux.api.auth as auth

    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: code)
    r = client.post("/api/auth/otp/request", json={"email": email, "name": name})
    assert r.status_code == 200, r.json
    r = client.post("/api/auth/otp/verify", json={"email": email, "code": f"{code:06d}"})
    assert r.status_code == 200, r.json
    return r.json["user"]


@pytest.fixture
def user(client, monkeypatch):
    return login(client, monkeypatch)
