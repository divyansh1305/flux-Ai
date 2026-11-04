"""SMS auto-tracking, the phone ingest endpoint and the schema migration."""
import sqlite3

import pytest

from flux.sms import parse_sms, split_messages


SMS = [
    ("Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici (UPI Ref No 512345678901). Not you? Call 1800",
     "expense", 250.0, "Food & Dining"),
    ("Sent Rs.1,180.50 From HDFC Bank A/C *1234 To UBER INDIA On 02/11/26 Ref 512345678902 Not You? Call 18002586161",
     "expense", 1180.5, "Transport"),
    ("ICICI Bank Acct XX123 debited for Rs 649.00 on 03-Nov-26; NETFLIX credited. UPI:512345678903. Call 18002662 for dispute",
     "expense", 649.0, "Subscriptions"),
    ("Dear Customer, INR 30,000.00 credited to your A/c XX1234 on 01-11-26 by NEFT from ACME TECH SALARY. Avl Bal INR 41,200",
     "income", 30000.0, "Salary"),
    ("Dear UPI user A/C X1234 debited by 520.0 on date 04Nov26 trf to BLINKIT Refno 512345678904. If not u? call 1800111109",
     "expense", 520.0, "Groceries"),
]


@pytest.mark.parametrize("text,kind,amount,category", SMS)
def test_sms_formats(text, kind, amount, category):
    r = parse_sms(text)
    assert r and r["kind"] == kind and r["amount"] == amount and r["category"] == category, r


@pytest.mark.parametrize("junk", [
    "Your OTP for login is 482913. Do not share it with anyone.",
    "Get cashback upto Rs 500 on your next recharge! Offer valid till Sunday.",
    "Your credit card bill of Rs 4,500 is due on 10-11-26. Minimum due Rs 225.",
    "hello how are you",
])
def test_sms_ignores_non_transactions(junk):
    assert parse_sms(junk) is None


def test_sms_import_with_dedupe(client, user):
    blob = "\n\n".join(t for t, *_ in SMS) + "\n\nYour OTP is 123456"
    assert len(split_messages(blob)) == 6
    r = client.post("/api/import/sms", json={"text": blob}).json
    assert len(r["rows"]) == 5 and r["ignored"] == 1
    c = client.post("/api/import/commit", json={"rows": r["rows"], "source": "sms"}).json
    assert c["imported"] == 5
    again = client.post("/api/import/sms", json={"text": blob}).json
    assert all(row["duplicate"] for row in again["rows"])
    assert any(t["source"] == "sms" for t in client.get("/api/transactions").json["items"])


# ─── Investing ───────────────────────────────────────────────

def test_migrates_v1_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')), onboarded INTEGER NOT NULL DEFAULT 0,
          autosave_mode TEXT NOT NULL DEFAULT 'roundup', autosave_value INTEGER NOT NULL DEFAULT 10,
          autosave_goal_id INTEGER, voice_lang TEXT NOT NULL DEFAULT 'en-IN');
        CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
          amount INTEGER NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', date TEXT NOT NULL,
          goal_id INTEGER, parent_id INTEGER, source TEXT NOT NULL DEFAULT 'manual'
          CHECK (source IN ('manual','voice','import','autosave')), import_hash TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO users (email, name) VALUES ('old@example.com', 'Old');
        INSERT INTO transactions (user_id, kind, amount, category, date) VALUES (1, 'income', 50000, 'Salary', '2026-10-01');
    """)
    conn.commit()
    conn.close()
    from flux import create_app

    create_app({"DATABASE": str(path), "SECRET_KEY": "k" * 40})
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    assert conn.execute("SELECT amount FROM transactions").fetchone()[0] == 50000
    conn.execute("INSERT INTO transactions (user_id, kind, amount, category, date, source) VALUES (1,'expense',100,'Other','2026-10-02','upi')")
    conn.commit()


# ─── Automatic SMS logging (iPhone Shortcuts / forwarders) ──────────
def _token(client):
    r = client.post("/api/ingest/token").json
    assert r["token"].startswith("flx_") and r["url"].endswith("/api/ingest/sms")
    return r["token"]


def test_auto_ingest_logs_sms_without_session(app, client, user):
    token = _token(client)
    phone = app.test_client()  # no cookies, no CSRF: just like iPhone Shortcuts
    sms = "Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici (UPI Ref No 512345678901)."
    r = phone.post("/api/ingest/sms", json={"text": sms}, headers={"Authorization": f"Bearer {token}"}).json
    assert r["logged"] and r["amount"] == 250 and r["category"] == "Food & Dining" and "Flux logged" in r["message"]
    again = phone.post("/api/ingest/sms", json={"text": sms}, headers={"Authorization": f"Bearer {token}"}).json
    assert not again["logged"] and "Already" in again["reason"]
    otp = phone.post("/api/ingest/sms", data="Your OTP is 123456", headers={"Authorization": f"Bearer {token}"}).json
    assert not otp["logged"]
    items = client.get("/api/transactions").json["items"]
    assert len([t for t in items if t["source"] == "sms"]) == 1
    assert client.get("/api/ingest/token").json["uses"] == 3


def test_auto_ingest_rejects_bad_tokens_and_revocation(app, client, user):
    phone = app.test_client()
    sms = {"text": "Rs.100.00 debited from A/c XX1 to VPA a@ybl"}
    assert phone.post("/api/ingest/sms", json=sms).status_code == 401
    assert phone.post("/api/ingest/sms", json=sms, headers={"Authorization": "Bearer flx_wrong"}).status_code == 401
    token = _token(client)
    client.delete("/api/ingest/token")
    assert phone.post("/api/ingest/sms", json=sms, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    new = _token(client)
    assert new != token
    assert phone.post("/api/ingest/sms", json=sms, headers={"Authorization": f"Bearer {new}"}).json["logged"]


def test_token_stored_hashed(app, client, user):
    token = _token(client)
    from flux.db import get_db

    with app.app_context():
        h = get_db().execute("SELECT token_hash FROM ingest_tokens").fetchone()[0]
    assert token not in h and len(h) == 64


