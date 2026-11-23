"""Kitna on a hosted database (Turso over HTTP), the way it runs on Vercel."""
import json
import sqlite3

import pytest
from conftest import Client, login
from fake_libsql import FakeLibsql

from flux import create_app
from flux.remote_db import RemoteConnection, split_script
from flux.security import limiter


@pytest.fixture
def remote(tmp_path):
    f = FakeLibsql(str(tmp_path / "remote.db"))
    yield f
    f.stop()


@pytest.fixture
def rapp(remote, monkeypatch):
    for k in ("EMAIL_SENDER", "EMAIL_PASSWORD", "GEMINI_API_KEY", "GOOGLE_CLIENT_ID", "SECRET_KEY", "FLUX_ENV", "CRON_SECRET"):
        monkeypatch.delenv(k, raising=False)
    limiter.reset()
    app = create_app({"DATABASE": ":memory:", "DATABASE_URL": remote.url, "DATABASE_TOKEN": remote.token, "TESTING": True,
                      "SECRET_KEY": "test-secret-key-that-is-long-enough-1234", "GEMINI_API_KEY": ""})
    yield app
    limiter.reset()


def test_rows_behave_like_sqlite_rows(remote):
    c = RemoteConnection(remote.url, remote.token)
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, amt REAL, data BLOB)")
    cur = c.execute("INSERT INTO t (name, amt, data) VALUES (?,?,?)", ("chai", 20.5, b"\x00\x01"))
    assert cur.lastrowid == 1 and cur.rowcount == 1 and c.in_transaction
    c.commit()
    r = c.execute("SELECT * FROM t WHERE name = ?", ("chai",)).fetchone()
    assert r["name"] == "chai" and r[0] == 1 and r["amt"] == 20.5 and r["data"] == b"\x00\x01"
    assert dict(r) == {"id": 1, "name": "chai", "amt": 20.5, "data": b"\x00\x01"} and r.keys() == ["id", "name", "amt", "data"]
    assert c.execute("SELECT * FROM t WHERE id = 99").fetchone() is None
    assert [x["name"] for x in c.execute("SELECT name FROM t")] == ["chai"]
    c.close()


def test_uncommitted_writes_are_rolled_back_and_errors_map_to_sqlite(remote):
    a = RemoteConnection(remote.url, remote.token)
    a.execute("CREATE TABLE u (email TEXT UNIQUE)")
    a.execute("INSERT INTO u VALUES ('a@x.in')")
    a.close()  # never committed, like sqlite3 when a request fails
    b = RemoteConnection(remote.url, remote.token)
    assert b.execute("SELECT COUNT(*) FROM u").fetchone()[0] == 0
    b.execute("INSERT INTO u VALUES ('a@x.in')")
    b.commit()
    with pytest.raises(sqlite3.IntegrityError):
        b.execute("INSERT INTO u VALUES ('a@x.in')")
    b.rollback()
    with pytest.raises(sqlite3.OperationalError):
        b.execute("SELECT * FROM missing_table")


def test_split_script_keeps_quotes_and_comments_apart():
    sql = "-- a; comment\nCREATE TABLE a (x TEXT DEFAULT 'a;b');\nINSERT INTO a VALUES ('c''d');\n"
    assert split_script(sql) == ["CREATE TABLE a (x TEXT DEFAULT 'a;b')", "INSERT INTO a VALUES ('c''d')"]


def test_whole_app_works_on_the_hosted_database(rapp, monkeypatch):
    c = Client(rapp)
    login(c, monkeypatch)
    c.patch("/api/account", json={"adult_confirmed": True})
    c.patch("/api/account", json={"income_pattern": "monthly", "pay_day": 1, "current_balance": 5000})
    c.patch("/api/account", json={"onboarded": True})
    r = c.post("/api/transactions", json={"kind": "expense", "amount": 250, "category": "Food & Dining", "note": "Zomato"})
    assert r.status_code == 201, r.json
    d = c.get("/api/dashboard").json
    assert d["recent"][0]["note"] == "Zomato"
    assert c.get("/api/transactions").status_code == 200
    # Deleting the account removes everything (needs foreign keys ON in every server connection)
    assert c.delete("/api/account", json={"confirm": "DELETE"}).status_code == 200
    with rapp.app_context():
        from flux.db import get_db
        assert get_db().execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_daily_cron_needs_the_secret(rapp, monkeypatch):
    c = rapp.test_client()
    assert c.get("/api/cron/daily").status_code == 404
    rapp.config["CRON_SECRET"] = "s3cret-value"
    assert c.get("/api/cron/daily", headers={"Authorization": "Bearer wrong"}).status_code == 404
    r = c.get("/api/cron/daily", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200 and "reminders" in r.json and "numbers" in r.json


def test_vercel_refuses_to_start_without_a_hosted_database(monkeypatch):
    from flux.config import ConfigError

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    with pytest.raises(ConfigError):
        create_app({"SECRET_KEY": "test-secret-key-that-is-long-enough-1234", "TESTING": True})


def test_vercel_config_runs_the_daily_job():
    cfg = json.load(open("vercel.json"))
    assert cfg["crons"][0]["path"] == "/api/cron/daily"


def test_copy_an_old_database_file_into_turso(app, client, user, rapp):
    """Moving from PythonAnywhere: the old flux.db is copied into the hosted database."""
    import importlib.util

    client.post("/api/transactions", json={"kind": "expense", "amount": 99, "category": "Transport", "note": "Auto"})
    spec = importlib.util.spec_from_file_location("copy_to_turso", "scripts/copy_to_turso.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    done = mod.copy(app.config["DATABASE"], rapp)
    assert done["users"] == 1 and done["transactions"] == 1
    with rapp.app_context():
        from flux.db import get_db
        assert get_db().execute("SELECT note FROM transactions").fetchone()["note"] == "Auto"


def test_brevo_is_used_for_email_when_configured(app, monkeypatch):
    import requests

    from flux import emailer

    sent = {}

    class R:
        status_code, text = 201, "{}"

    monkeypatch.setattr(requests, "post", lambda url, **kw: sent.update(url=url, **kw) or R())
    app.config.update(BREVO_API_KEY="xkeysib-test", MAIL_SENDER="flux.wealth.engine@gmail.com", MAIL_PASSWORD="")
    with app.app_context():
        assert emailer.send_email("a@b.in", "Your code", "123456", "<b>123456</b>")
    assert sent["url"].endswith("/v3/smtp/email") and sent["headers"]["api-key"] == "xkeysib-test"
    assert sent["json"]["sender"]["email"] == "flux.wealth.engine@gmail.com" and sent["json"]["to"] == [{"email": "a@b.in"}]
