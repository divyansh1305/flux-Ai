"""Scan & Pay, SMS auto-tracking, investing, and the schema migration."""
import sqlite3

import pytest

from flux import market
from flux.security import ApiError
from flux.sms import parse_sms, split_messages
from flux.upi import build_links, parse_upi_uri


# ─── UPI parsing (NPCI linking spec) ─────────────────────────
def test_parse_merchant_qr():
    p = parse_upi_uri("upi://pay?pa=swiggy.stores@icici&pn=Swiggy%20Limited&mc=5812&tr=ORD123&am=249.00&cu=INR")
    assert p["pa"] == "swiggy.stores@icici" and p["pn"] == "Swiggy Limited"
    assert str(p["am"]) == "249.00" and p["mc"] == "5812" and p["is_merchant"]


def test_parse_static_person_qr_and_bare_vpa():
    p = parse_upi_uri("upi://pay?pa=rahul.k@okaxis&pn=Rahul%20K&cu=INR")
    assert p["am"] is None and not p["is_merchant"]
    assert parse_upi_uri("riya@ybl")["pa"] == "riya@ybl"


@pytest.mark.parametrize("bad", [
    "https://evil.com/?pa=x@y", "upi://pay?pn=NoVpa", "upi://pay?pa=not-a-vpa", "upi://pay?pa=a@bank&am=-5",
    "upi://pay?pa=a@bank&am=500000", "upi://pay?pa=a@bank&cu=USD", "javascript:alert(1)", "x" * 2000,
])
def test_parse_rejects_bad_codes(bad):
    with pytest.raises(ApiError):
        parse_upi_uri(bad)


def test_links_are_encoded_and_cannot_be_injected():
    links = build_links("shop@okhdfc", "Chai & Co", "45.5", "tea & snacks", "FLX1")
    assert links["generic"].startswith("upi://pay?pa=shop@okhdfc&pn=Chai%20%26%20Co&am=45.50&cu=INR")
    assert "tn=tea%20%26%20snacks" in links["generic"]
    gpay = next(a for a in links["apps"] if a["id"] == "gpay")
    assert gpay["android"].endswith("package=com.google.android.apps.nbu.paisa.user;end")
    with pytest.raises(ApiError):
        build_links("x@y\"><script>", "n", "10", "", "")


# ─── Scan & Pay flow ─────────────────────────────────────────
def test_scan_and_pay_end_to_end(client, user):
    client.post("/api/transactions", json={"kind": "income", "amount": 5000, "category": "Salary"})
    client.post("/api/goals", json={"title": "Trip", "target": 10000})
    d = client.post("/api/pay/parse", json={"code": "upi://pay?pa=zomato@hdfc&pn=Zomato&mc=5812&am=347"}).json
    assert d["category"] == "Food & Dining" and d["amount"] == 347 and d["category_reason"] == "merchant code"
    prep = client.post("/api/pay/prepare", json={"vpa": d["vpa"], "name": d["name"], "amount": 347, "category": d["category"]}).json
    assert prep["links"]["generic"].startswith("upi://pay?pa=zomato@hdfc")
    assert prep["check"]["level"] in ("ok", "caution")
    # Nothing is logged until the user confirms they paid.
    assert client.get("/api/dashboard").json["balance"] == 5000
    r = client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"}).json
    assert r["autosaved"] == 3  # ₹347 rounds up to ₹350
    assert r["balance"] == 5000 - 347 - 3
    tx = client.get("/api/transactions").json["items"]
    assert any(t["source"] == "upi" and t["amount"] == 347 for t in tx)
    # Can't confirm twice.
    assert client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"}).status_code == 409
    # Flux remembers the payee's category next time.
    again = client.post("/api/pay/parse", json={"code": "zomato@hdfc"}).json
    assert again["known_payee"] and again["category"] == "Food & Dining"


def test_failed_payment_logs_nothing(client, user):
    prep = client.post("/api/pay/prepare", json={"vpa": "shop@ybl", "amount": 100, "category": "Shopping"}).json
    client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "failed"})
    assert client.get("/api/transactions").json["items"] == []


def test_pay_validation_and_isolation(app, client, user, monkeypatch):
    assert client.post("/api/pay/prepare", json={"vpa": "bad", "amount": 10}).status_code == 400
    assert client.post("/api/pay/prepare", json={"vpa": "ab@ybl", "amount": 200000}).status_code == 400
    prep = client.post("/api/pay/prepare", json={"vpa": "ab@ybl", "amount": 10, "category": "Other"}).json
    from conftest import Client, login

    other = Client(app)
    login(other, monkeypatch, "eve@example.com", "Eve", 424242)
    assert other.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"}).status_code == 404


# ─── SMS auto-tracking ───────────────────────────────────────
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
@pytest.fixture
def prices(monkeypatch):
    market.clear_cache()
    table = {"NIFTYBEES": 280.0, "GOLDBEES": 70.0, "JUNIORBEES": 750.0, "LIQUIDBEES": 1000.0}
    monkeypatch.setattr(market, "fetch_price", lambda s: table.get(s))
    yield table
    market.clear_cache()


def test_invest_practice_flow(client, user, prices):
    client.post("/api/transactions", json={"kind": "income", "amount": 10000, "category": "Salary"})
    g = client.post("/api/goals", json={"title": "Emergency", "target": 50000}).json
    client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 3000})
    opts = client.get("/api/invest/options").json
    assert opts["mode"] == "practice" and opts["instruments"][0]["price"] == 280.0
    prep = client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "NIFTYBEES", "amount": 1000}).json
    assert prep["quantity"] == 3 and prep["estimated_cost"] == 840
    assert prep["kite_order"] == {"exchange": "NSE", "tradingsymbol": "NIFTYBEES", "quantity": 3,
                                  "transaction_type": "BUY", "order_type": "MARKET", "product": "CNC"}
    client.post(f"/api/invest/{prep['investment_id']}/complete", json={"status": "success"})
    goal = client.get("/api/goals").json[0]
    # Goal progress is unchanged: ₹840 moved from cash into the ETF.
    assert goal["saved"] == 3000 and goal["cash"] == 2160 and goal["invested"] == 840
    assert client.get("/api/dashboard").json["balance"] == 7000
    h = client.get("/api/invest/holdings").json
    assert h["items"][0]["quantity"] == 3 and h["value"] == 840
    prices["NIFTYBEES"] = 300.0
    market.clear_cache()
    s = client.post(f"/api/invest/{h['items'][0]['id']}/sell", json={}).json
    assert s["proceeds"] == 900 and s["profit"] == 60
    assert client.get("/api/goals").json[0]["saved"] == 3060
    # Balance never moved: the profit stays inside the goal.
    assert client.get("/api/dashboard").json["balance"] == 7000


def test_invest_limits(client, user, prices):
    client.post("/api/transactions", json={"kind": "income", "amount": 1000, "category": "Salary"})
    g = client.post("/api/goals", json={"title": "X", "target": 5000}).json
    client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 500})
    assert client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "JUNIORBEES", "amount": 500}).status_code == 400
    assert client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "RELIANCE", "amount": 500}).status_code == 400
    assert client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "NIFTYBEES", "amount": 2000}).status_code == 400
    assert client.post("/api/invest/prepare", json={"goal_id": 9999, "symbol": "NIFTYBEES", "amount": 300}).status_code == 404


def test_invest_without_live_price_needs_manual_price(client, user, monkeypatch):
    market.clear_cache()
    monkeypatch.setattr(market, "fetch_price", lambda s: None)
    client.post("/api/transactions", json={"kind": "income", "amount": 1000, "category": "Salary"})
    g = client.post("/api/goals", json={"title": "X", "target": 5000}).json
    client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 600})
    assert client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "GOLDBEES", "amount": 500}).status_code == 400
    r = client.post("/api/invest/prepare", json={"goal_id": g["id"], "symbol": "GOLDBEES", "amount": 500, "price": 70}).json
    assert r["quantity"] == 7


def test_kite_mode_when_key_configured(app, client, user, prices):
    app.config["KITE_API_KEY"] = "kitekey123"
    assert client.get("/api/invest/options").json["mode"] == "kite"
    assert "https://kite.trade" in client.get("/app/invest").headers["Content-Security-Policy"]


# ─── Voice: paying ──────────────────────────────────────────
def test_voice_pay_uses_known_payee(app, client, user):
    app.config["FEATURE_PAY"] = True
    prep = client.post("/api/pay/prepare", json={"vpa": "rahul.k@okaxis", "name": "Rahul K", "amount": 50, "category": "Other"}).json
    client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"})
    r = client.post("/api/voice/command", json={"text": "pay 200 to rahul"}).json
    assert r["navigate"].startswith("/app/pay?") and "rahul.k%40okaxis" in r["navigate"] and "amount=200.00" in r["navigate"]


# ─── Migration from schema v1 ────────────────────────────────
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
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
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


def test_auto_ingest_skips_scan_and_pay_duplicates(app, client, user):
    prep = client.post("/api/pay/prepare", json={"vpa": "zomato@hdfc", "name": "Zomato", "amount": 347, "category": "Food & Dining"}).json
    client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"})
    token = _token(client)
    r = app.test_client().post("/api/ingest/sms", json={"text": "Rs.347.00 debited from A/c XX1234 to VPA zomato@hdfc Ref 512300000001"},
                               headers={"Authorization": f"Bearer {token}"}).json
    assert not r["logged"] and "another source" in r["reason"]
    assert len(client.get("/api/transactions").json["items"]) == 1
