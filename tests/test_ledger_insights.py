"""Ledger integrity (dedupe, reconciliation, double-entry) and forward-looking insights."""
from datetime import date

import pytest

from flux import clock

TODAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def tok(client):
    return client.post("/api/ingest/token").json["token"]


def sms(app, token, text):
    return app.test_client().post("/api/ingest/sms", json={"text": text}, headers={"Authorization": f"Bearer {token}"}).json


def notif(app, token, package, title, body="", posted_at=None):
    return app.test_client().post("/api/ingest/notification", json={"package": package, "title": title, "body": body, "posted_at": posted_at},
                                  headers={"Authorization": f"Bearer {token}"}).json


def add(client, kind, amount, category, **kw):
    r = client.post("/api/transactions", json={"kind": kind, "amount": amount, "category": category, **kw})
    assert r.status_code == 201, r.json
    return r.json


# ─── De-duplication across sources ───────────────────────────
def test_upi_notification_then_bank_sms_then_statement_is_one_payment(app, client, user):
    t = tok(client)
    assert notif(app, t, "com.google.android.apps.nbu.paisa.user", "₹347 paid to Zomato", "Paid from HDFC Bank •• 1234")["logged"]
    r = sms(app, t, "Rs.347.00 debited from A/c XX1234 on 10-11-26 to VPA zomato@hdfc (UPI Ref No 628811112222). Avl Bal Rs 9,653.00")
    assert not r["logged"] and "another source" in r["reason"]
    stmt = ("Date,Narration,Ref,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
            "10/11/26,UPI/DR/628811112222/ZOMATO/HDFC/zomato@hdfc,1,10/11/26,347.00,,9653.00\n")
    import io
    prev = client.post("/api/import/preview", data={"file": (io.BytesIO(stmt.encode()), "s.csv")}, content_type="multipart/form-data").json
    c = client.post("/api/import/commit", json={"rows": prev["rows"]}).json
    assert c["imported"] == 0 and c["duplicates_skipped"] == 1
    items = [x for x in client.get("/api/transactions").json["items"] if x["kind"] == "expense"]
    assert len(items) == 1
    # The surviving record was enriched with the bank's reference and balance.
    assert client.get("/api/dashboard").json["bank"]["balance"] == 9653.0


def test_two_payments_with_different_refs_are_both_kept(app, client, user):
    t = tok(client)
    assert sms(app, t, "Rs.100.00 debited from A/c XX1 to VPA chai@ybl (UPI Ref No 628800000001)")["logged"]
    assert sms(app, t, "Rs.100.00 debited from A/c XX1 to VPA chai@ybl (UPI Ref No 628800000002)")["logged"]


def test_notification_then_sms_dedupes(app, client, user):
    t = tok(client)
    r = notif(app, t, "com.google.android.apps.nbu.paisa.user", "₹250 paid to Swiggy", "Paid from HDFC Bank •• 1234")
    assert r["logged"] and r["category"] == "Food & Dining"
    r2 = sms(app, t, "Rs.250.00 debited from A/c XX1234 on 10-11-26 to VPA swiggy@icici (UPI Ref No 628899998888)")
    assert not r2["logged"]
    assert notif(app, t, "com.evil.app", "₹1 paid to X")["logged"] is False
    assert notif(app, t, "com.phonepe.app", "Rohit requested ₹200")["logged"] is False


# ─── Reconciliation against bank-reported balance ────────────
def test_reconciliation_detects_missing_transaction(app, client, user):
    t = tok(client)
    assert client.get("/api/ledger").json["reconcile"]["status"] == "no_data"
    sms(app, t, "Rs.250.00 debited from A/c XX1234 on 10-11-26 to VPA swiggy@icici (UPI Ref No 628800000011). Avl Bal Rs 9,750.00")
    sms(app, t, "Rs.100.00 debited from A/c XX1234 on 10-11-26 to VPA uber@axl (UPI Ref No 628800000012). Avl Bal Rs 9,650.00")
    rec = client.get("/api/ledger").json["reconcile"]
    assert rec["status"] == "in_sync"
    # A ₹200 payment happened that Flux never saw, then the next SMS shows the gap.
    sms(app, t, "Rs.50.00 debited from A/c XX1234 on 10-11-26 to VPA chai@ybl (UPI Ref No 628800000013). Avl Bal Rs 9,400.00")
    rec = client.get("/api/ledger").json["reconcile"]
    assert rec["status"] == "drift" and rec["drift"] == -200.0 and "200" in rec["message"]


# ─── Double-entry invariants ─────────────────────────────────
def test_trial_balance_always_balances(client, user):
    add(client, "income", 10000, "Salary")
    g = client.post("/api/goals", json={"title": "Trip", "target": 20000}).json
    add(client, "expense", 347, "Food & Dining")   # + ₹3 auto-save
    client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 2000})
    tb = client.get("/api/ledger").json["trial_balance"]
    assert tb["sum"] == 0
    assert tb["unallocated"] == tb["available"] == client.get("/api/dashboard").json["balance"]


# ─── Recurring bills & safe-to-spend ─────────────────────────
def test_recurring_detection(client, user):
    for d in ("2026-08-05", "2026-09-05", "2026-10-05"):
        add(client, "expense", 649, "Subscriptions", note="Netflix", date=d)
    for d in ("2026-10-01", "2026-10-17"):  # irregular: not a bill
        add(client, "expense", 300, "Shopping", note="Myntra", date=d)
    bills = client.get("/api/insights").json["recurring"]
    assert len(bills) == 1 and bills[0]["name"] == "Netflix" and bills[0]["cadence"] == "monthly"
    assert bills[0]["next_date"] == "2026-11-04" or bills[0]["next_date"] >= "2026-11-04"


def test_safe_to_spend_reserves_bills_and_goals(client, user):
    add(client, "income", 30000, "Salary", date="2026-11-01")
    for d in ("2026-09-25", "2026-10-25"):
        add(client, "expense", 649, "Subscriptions", note="Netflix", date=d)
    client.post("/api/goals", json={"title": "Laptop", "target": 30000, "deadline": "2027-04-30"})
    add(client, "expense", 200, "Food & Dining", date="2026-11-10")
    s = client.get("/api/dashboard").json["safe"]
    # available 30000-1298-200 = 28502 (no autosave: ₹200/₹649 are multiples… 649 isn't, but balance check uses it)
    avail = client.get("/api/dashboard").json["balance"]
    assert s["bills_due"] == 649.0 and s["days_left"] == 21
    expected_daily = round((avail + 200 - 649 - s["goal_reserve"]) / 21)
    assert abs(s["daily"] - expected_daily) <= 1
    assert abs(s["left_today"] - (expected_daily - 200)) <= 1
    assert s["goal_reserve"] == 5000.0  # ₹30,000 over Nov–Apr = 6 months


def test_cashback_report(app, client, user):
    t = tok(client)
    add(client, "income", 20000, "Salary")
    client.post("/api/goals", json={"title": "Trip", "target": 9000})
    add(client, "expense", 4997, "Shopping")   # auto-saves ₹3
    sms(app, t, "Rs 25.00 credited to your a/c XX1234 as cashback from PhonePe on 09-11-26")
    rep = client.get("/api/insights").json["cashback"]
    assert rep["cashback"] == 25.0 and rep["cashback_count"] == 1 and rep["spend"] == 4997.0
    assert "0.50% back" in rep["verdict"] or "0.5" in rep["verdict"]


def test_voice_safe_to_spend_and_bills(client, user):
    add(client, "income", 3100, "Salary", date="2026-11-01")
    r = client.post("/api/voice/command", json={"text": "how much can I spend today"}).json
    assert r["intent"] == "safe_to_spend" and "₹" in r["reply"]
    r = client.post("/api/voice/command", json={"text": "what bills do I have"}).json
    assert r["intent"] == "bills"


# ─── Android companion contract ──────────────────────────────
def test_companion_ping_and_messages_app_notification(app, client, user):
    t = tok(client)
    phone = app.test_client()
    ping = phone.get("/api/ingest/ping", headers={"Authorization": f"Bearer {t}"})
    assert ping.status_code == 200 and ping.json["ok"] is True
    assert phone.get("/api/ingest/ping", headers={"Authorization": "Bearer flx_nope"}).status_code == 401
    # Bank SMS shown by the Messages app → parsed with SMS rules, date taken from the message
    r = notif(app, t, "com.google.android.apps.messaging", "AX-HDFCBK",
              "Rs.250.00 debited from A/c XX1234 on 09-11-26 to VPA zomato@icici UPI Ref 512345678901. Avl Bal Rs 4,120.50")
    assert r["logged"], r
    rows = client.get("/api/transactions").json
    rows = rows.get("items", rows) if isinstance(rows, dict) else rows
    z = [x for x in rows if x.get("ref") == "512345678901" or "Zomato" in (x.get("note") or "")]
    assert z and z[0]["date"] == "2026-11-09"
    # Same payment from GPay a moment later is not double-counted
    again = notif(app, t, "com.google.android.apps.nbu.paisa.user", "₹250 paid to Zomato", "")
    assert not again.get("logged") or again.get("duplicate")


def test_two_identical_chai_payments_same_app_are_both_kept(app, client, user):
    t = tok(client)
    a = notif(app, t, "com.phonepe.app", "₹20 paid to Ramu Tea Stall", "", posted_at=1793000000000)
    b = notif(app, t, "com.phonepe.app", "₹20 paid to Ramu Tea Stall", "", posted_at=1793003600000)
    retry = notif(app, t, "com.phonepe.app", "₹20 paid to Ramu Tea Stall", "", posted_at=1793003600000)
    assert a["logged"] and b["logged"]          # two real payments an hour apart
    assert not retry["logged"]                   # the phone retrying the same notification


def test_same_amount_in_two_different_upi_apps_is_two_payments(app, client, user):
    t = tok(client)
    a = notif(app, t, "com.google.android.apps.nbu.paisa.user", "₹100 paid to Sharma Dairy", "", posted_at=1)
    b = notif(app, t, "com.phonepe.app", "₹100 paid to Gupta Kirana", "", posted_at=2)
    assert a["logged"] and b["logged"]
    # …but the bank SMS for the PhonePe one is matched to it, not logged a third time
    c = sms(app, t, "Rs.100.00 debited from A/c XX1234 on 10-11-26 to VPA gupta.kirana@ybl. Avl Bal Rs 5,000.00")
    assert not c["logged"]


def test_match_my_bank_sets_opening_balance_without_faking_income(app, client, user):
    t = tok(client)
    add(client, "income", 30000, "Salary")
    before_month = client.get("/api/dashboard").json["month"]
    assert client.post("/api/ledger/align").status_code == 400            # no bank balance seen yet
    sms(app, t, "Rs.500.00 debited from A/c XX1234 on 10-11-26 to VPA swiggy@icici (UPI Ref No 512345678901). Avl Bal Rs 80,000.00")
    d = client.get("/api/dashboard").json
    assert d["bank_gap"] > 0
    r = client.post("/api/ledger/align").json
    d2 = client.get("/api/dashboard").json
    goal_cash = sum(g["cash"] for g in client.get("/api/goals").json)
    assert abs(d2["balance"] + goal_cash - 80000) < 0.01 and abs(d2["bank_gap"]) < 0.01
    assert r["adjusted_by"] > 0
    # Opening balance is not income: this month's income figure is unchanged
    assert d2["month"]["income"] == before_month["income"]
    tb = client.get("/api/ledger").json["trial_balance"]
    assert tb["sum"] == 0 and tb["accounts"]["equity:opening_balance"] < 0
