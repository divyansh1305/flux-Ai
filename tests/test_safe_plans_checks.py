"""Personal safe-to-spend, plans, money checks, the 18+ rule and Gmail reconnect."""
from datetime import date

import pytest

from flux import clock

TODAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def add(client, kind, amount, category, **kw):
    r = client.post("/api/transactions", json={"kind": kind, "amount": amount, "category": category, **kw})
    assert r.status_code == 201, r.json
    return r.json


def safe(client):
    return client.get("/api/dashboard").json["safe"]


def tok(client):
    return client.post("/api/ingest/token").json["token"]


def sms(app, token, text):
    return app.test_client().post("/api/ingest/sms", json={"text": text}, headers={"Authorization": f"Bearer {token}"}).json


# ─── Safe to spend ───────────────────────────────────────────
def test_new_user_is_asked_to_set_up_not_shown_zero_as_a_verdict(client, user):
    s = safe(client)
    assert s["status"] == "setup" and s["left_today"] == 0


def test_payday_plans_and_cushion_shape_the_number(client, user):
    add(client, "income", 30000, "Salary", date="2026-11-01")
    client.patch("/api/account", json={"income_pattern": "monthly", "pay_day": 1, "cushion": 1000})
    client.post("/api/plans", json={"title": "Dinner Friday", "amount": 2000, "date": "2026-11-13"})
    client.post("/api/plans", json={"title": "Next month's trip", "amount": 5000, "date": "2026-12-05"})  # after payday: ignored
    s = safe(client)
    assert s["until"] == "2026-12-01" and s["days_left"] == 21 and s["horizon"] == "payday"
    assert s["plans_reserved"] == 2000 and s["cushion"] == 1000
    assert abs(s["daily"] - (30000 - 2000 - 1000) / 21) < 0.01
    labels = [line["label"] for line in s["lines"]]
    assert "Your plans" in labels and "Safety cushion (kept aside)" in labels


def test_unset_pattern_plans_to_month_end(client, user):
    add(client, "income", 21000, "Pocket Money", date="2026-11-01")
    s = safe(client)
    assert s["until"] == "2026-12-01" and s["horizon"] == "month_end" and s["daily"] == 1000


def test_pay_day_late_in_month_and_short_months(client, user):
    add(client, "income", 10000, "Salary", date="2026-11-01")
    client.patch("/api/account", json={"income_pattern": "monthly", "pay_day": 31})
    assert safe(client)["until"] == "2026-11-30"  # November has 30 days
    client.patch("/api/account", json={"pay_day": 5})
    assert safe(client)["until"] == "2026-12-05"


def test_plan_for_today_is_not_counted_twice_once_paid(client, user):
    add(client, "income", 31000, "Salary", date="2026-11-01")
    client.post("/api/plans", json={"title": "Dinner", "amount": 2000, "date": "2026-11-10"})
    before = safe(client)
    assert before["plans_reserved"] == 2000
    add(client, "expense", 1900, "Food & Dining", note="Dinner", date="2026-11-10")
    after = safe(client)
    assert after["plans_reserved"] == 0
    # Paying for the plan doesn't shrink the rest of the month a second time (₹100 under plan is freed up).
    assert abs(after["daily"] - (before["daily"] + 100 / 21)) < 0.01 and after["left_today"] == after["daily"]


def test_sure_and_maybe_income(client, user):
    add(client, "income", 5000, "Freelance", date="2026-11-01")
    client.patch("/api/account", json={"income_pattern": "varies"})
    client.post("/api/plans", json={"kind": "income", "title": "Client A", "amount": 15000, "date": "2026-11-20"})
    client.post("/api/plans", json={"kind": "income", "title": "Client B", "amount": 21000, "date": "2026-11-25", "sure": False})
    s = safe(client)
    assert s["sure_income"] == 15000 and s["maybe_extra_daily"] == 1000  # 21000 / 21 days
    assert abs(s["daily"] - 20000 / 21) < 0.01


# ─── Plans API ───────────────────────────────────────────────
def test_plans_validation_and_isolation(app, client, user, monkeypatch):
    assert client.post("/api/plans", json={"title": "", "amount": 100, "date": "2026-11-12"}).status_code == 400
    assert client.post("/api/plans", json={"title": "X", "amount": -5, "date": "2026-11-12"}).status_code == 400
    assert client.post("/api/plans", json={"title": "X", "amount": 5, "date": "2026-10-01"}).status_code == 400
    p = client.post("/api/plans", json={"title": "Shoes", "amount": 1000, "date": "2026-11-15"}).json
    assert client.patch(f"/api/plans/{p['id']}", json={"done": True}).json["done"] is True

    from conftest import Client, login

    other = Client(app)
    login(other, monkeypatch, email="sam@example.com", name="Sam")
    assert other.delete(f"/api/plans/{p['id']}").status_code == 404
    assert other.get("/api/plans").json == []
    assert client.delete(f"/api/plans/{p['id']}").status_code == 200


# ─── Money checks ────────────────────────────────────────────
def test_failed_payment_is_watched_until_refund_arrives(app, client, user):
    t = tok(client)
    r = sms(app, t, "Your UPI transaction of Rs.850.00 to myntra@ybl has failed. Amount debited from A/c XX1234 will be reversed. Ref 628812345678")
    assert r["logged"] is False and r["watching"] is True
    checks = client.get("/api/checks").json
    assert len(checks) == 1 and checks[0]["type"] == "refund" and "11 Nov" in checks[0]["body"] and "15 Nov" in checks[0]["body"]
    # The same message again doesn't open a second watch.
    sms(app, t, "Your UPI transaction of Rs.850.00 to myntra@ybl has failed. Amount debited from A/c XX1234 will be reversed. Ref 628812345678")
    assert len(client.get("/api/checks").json) == 1
    sms(app, t, "Rs.850.00 credited to A/c XX1234 on 11-11-26. Refund/reversal of UPI txn Ref 628812345678")
    assert client.get("/api/checks").json == []


def test_failed_without_money_taken_is_ignored(app, client, user):
    t = tok(client)
    sms(app, t, "Your payment of Rs 200 failed due to incorrect UPI PIN. No amount was taken.")
    assert client.get("/api/checks").json == []


def test_double_charge_and_dismiss(app, client, user):
    t = tok(client)
    for ref in ("628800000101", "628800000102"):
        assert sms(app, t, f"Rs.499.00 debited from A/c XX1234 on 09-11-26 to VPA blinkit@hdfc (UPI Ref No {ref})")["logged"]
    found = [c for c in client.get("/api/checks").json if c["type"] == "double"]
    assert len(found) == 1 and "499" in found[0]["title"]
    client.post("/api/checks/dismiss", json={"key": found[0]["key"]})
    assert [c for c in client.get("/api/checks").json if c["type"] == "double"] == []


def test_price_rise_on_a_monthly_payment(client, user):
    add(client, "expense", 119, "Subscriptions", note="Spotify", date="2026-09-08")
    add(client, "expense", 119, "Subscriptions", note="Spotify", date="2026-10-08")
    add(client, "expense", 139, "Subscriptions", note="Spotify", date="2026-11-08")
    found = [c for c in client.get("/api/checks").json if c["type"] == "price"]
    assert len(found) == 1 and "119" in found[0]["title"] and "139" in found[0]["title"]


# ─── 18+ and data rights ─────────────────────────────────────
def test_onboarding_needs_age_confirmation(client, user):
    r = client.patch("/api/account", json={"onboarded": True})
    assert r.status_code == 400 and "18" in r.json["error"]
    r = client.patch("/api/account", json={"onboarded": True, "adult_confirmed": True})
    assert r.status_code == 200 and r.json["user"]["onboarded"] and r.json["user"]["adult_confirmed"]


def test_export_includes_plans(client, user):
    client.post("/api/plans", json={"title": "Rent", "amount": 8000, "date": "2026-11-30"})
    data = client.get("/api/account/export").json
    assert data["plans"][0]["title"] == "Rent"


# ─── Gmail dead link ─────────────────────────────────────────
def test_gmail_expired_token_asks_to_reconnect(app, client, user, monkeypatch):
    from flux import gmail

    app.config.update(GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="secret")

    class R:
        status_code = 400

        def json(self):
            return {"error": "invalid_grant"}

    class Dead:
        def post(self, *a, **k):
            return R()

    with app.app_context():
        from flux.db import get_db

        get_db().execute("INSERT INTO gmail_accounts (user_id, email, refresh_token) VALUES (?,?,?)",
                         (user["id"], "riya@gmail.com", gmail._enc("old-token")))
        get_db().commit()
    monkeypatch.setattr(gmail, "_http", Dead())
    r = client.post("/api/gmail/sync", json={}).json
    assert r["needs_reconnect"] is True
    st = client.get("/api/dashboard").json["gmail"]
    assert st["needs_reconnect"] is True


def test_current_balance_from_setup_gives_a_number_right_away(client, user):
    add(client, "expense", 500, "Food & Dining", date="2026-11-09")
    r = client.patch("/api/account", json={"current_balance": 12000, "income_pattern": "monthly", "pay_day": 1})
    assert r.status_code == 200
    d = client.get("/api/dashboard").json
    assert d["balance"] == 12000 and d["safe"]["status"] == "ok" and d["safe"]["confirmed"] is False


def test_what_flux_knows_counts_everything(client, user):
    add(client, "expense", 100, "Food & Dining")
    client.post("/api/plans", json={"title": "Rent", "amount": 8000, "date": "2026-11-30"})
    k = client.get("/api/account/knows").json
    assert k["counts"]["transactions"] == 1 and k["counts"]["plans"] == 1
    assert k["sources"]["gmail"]["connected"] is False and k["sources"]["phone"]["connected"] is False
    assert client.get("/app/privacy-center").status_code == 200 and client.get("/app/plans").status_code == 200


def test_android_download_is_advertised(client, user):
    assert client.get("/api/auth/me").json["features"]["android_apk"].endswith("kitna-android.apk")
