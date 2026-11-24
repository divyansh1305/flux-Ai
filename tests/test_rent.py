"""Kitna Rent: owners see whose rent arrived, who is late, and tenants get their own page."""
import hashlib
import hmac
import json
from datetime import date

import pytest

from flux import clock


def tok(client):
    return client.post("/api/ingest/token").json["token"]


def sms(app, token, text):
    return app.test_client().post("/api/ingest/sms", json={"text": text}, headers={"Authorization": f"Bearer {token}"}).json


@pytest.fixture
def owner(client, user, monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 20))
    r = client.put("/api/rent/property", json={"name": "Sharma PG", "upi_id": "sharmapg@okaxis", "due_day": 5})
    assert r.status_code == 200
    return user


def add(client, **kw):
    body = {"name": "Rahul Verma", "rent": 8500, "room": "101", "phone": "9876543210", "start_month": "2026-11", **kw}
    r = client.post("/api/rent/tenants", json=body)
    assert r.status_code == 201, r.json
    return r.json["ids"][0]


def tenant(client, tid):
    return next(t for t in client.get("/api/rent").json["tenants"] if t["id"] == tid)


def test_new_tenant_is_late_after_due_day_and_named_bank_alert_clears_it(app, client, owner):
    tid = add(client)
    t = tenant(client, tid)
    assert t["money"] == "late" and t["balance"] == 8500 and t["late_days"] == 15
    t_ = tok(client)
    # Tenant pays from GPay; the owner's bank SMS names them → counted as Rahul's rent automatically.
    out = sms(app, t_, "Rs.8500.00 credited to A/c XX1234 on 18-11-26 from VPA rahulverma@okhdfc (UPI Ref No 628811110001)")
    assert out["logged"]
    t = tenant(client, tid)
    assert t["money"] == "paid" and t["balance"] == 0
    ov = client.get("/api/rent").json
    assert ov["collected"] == 8500 and ov["counts"]["paid"] == 1 and ov["unmatched"] == []
    # The money also shows in the owner's own Activity as rent, not as something to sort.
    d = client.get("/api/dashboard").json
    assert d["to_sort_count"] == 0 and d["recent"][0]["category"] == "Rent received"


def test_parent_paying_is_matched_by_the_payer_names_the_owner_gave(app, client, owner):
    tid = add(client, name="Aman Gupta", payer_names="Suresh Gupta")
    sms(app, tok(client), "Rs.8500.00 credited to A/c XX1234 on 18-11-26 from SURESH GUPTA (IMPS Ref 628811110002)")
    assert tenant(client, tid)["money"] == "paid"


def test_unknown_payer_waits_with_likely_tenant_first_and_one_tap_teaches_kitna(app, client, owner):
    a = add(client, name="Rahul Verma", rent=8500)
    b = add(client, name="Priya Nair", rent=7000, room="102")
    t_ = tok(client)
    sms(app, t_, "Rs.7000.00 credited to A/c XX1234 on 18-11-26 from VPA kn1984@ybl (UPI Ref No 628811110003)")
    ov = client.get("/api/rent").json
    assert len(ov["unmatched"]) == 1
    u = ov["unmatched"][0]
    assert u["likely"] == [b] and u["choices"][0]["id"] == b
    assert client.post("/api/rent/assign", json={"transaction_id": u["transaction_id"], "tenant_id": b}).status_code == 200
    assert tenant(client, b)["money"] == "paid" and tenant(client, a)["money"] == "late"
    # Next month the same payer is recognised by itself.
    sms(app, t_, "Rs.7000.00 credited to A/c XX1234 on 19-11-26 from VPA kn1984@ybl (UPI Ref No 628811110004)")
    assert tenant(client, b)["advance"] == 7000
    assert client.get("/api/rent").json["unmatched"] == []


def test_not_rent_stops_asking(app, client, owner):
    add(client)
    sms(app, tok(client), "Rs.2000.00 credited to A/c XX1234 on 18-11-26 from VPA mom@okicici (UPI Ref No 628811110005)")
    u = client.get("/api/rent").json["unmatched"][0]
    client.post("/api/rent/assign", json={"transaction_id": u["transaction_id"], "not_rent": True})
    assert client.get("/api/rent").json["unmatched"] == []


def test_cash_partial_and_old_dues_are_applied_oldest_first(app, client, owner):
    tid = add(client, start_month="2026-10", opening_due=1000)
    t = tenant(client, tid)
    assert t["balance"] == 1000 + 8500 * 2
    client.post(f"/api/rent/tenants/{tid}/payments", json={"amount": 9500, "method": "cash", "date": "2026-11-02"})
    t = tenant(client, tid)
    # Old dues + October covered; November still open and late since 5 Nov.
    assert t["balance"] == 8500 and t["money"] == "late" and t["due_on"] == "2026-11-05"
    d = client.get(f"/api/rent/tenants/{tid}").json
    assert d["months"][0] == {"month": "2026-11", "due_date": "2026-11-05", "rent": 8500, "paid": 0, "status": "due"}
    assert d["wa_phone"] == "919876543210" and "₹8,500" in d["reminder"] and "sharmapg@okaxis" in d["reminder"]
    client.delete(f"/api/rent/payments/{d['payments'][0]['id']}")
    assert tenant(client, tid)["balance"] == 18000


def test_tenant_link_shows_only_their_own_dues_and_a_upi_qr(app, client, owner):
    a = add(client)
    add(client, name="Other Person", room="999")
    link = tenant(client, a)["link"]
    token = link.rsplit("/", 1)[1]
    outsider = app.test_client()  # no sign-in
    assert outsider.get(f"/r/{token}").status_code == 200
    v = outsider.get(f"/api/r/{token}").json
    assert v["tenant"] == "Rahul Verma" and v["property"] == "Sharma PG" and v["upi_id"] == "sharmapg@okaxis"
    assert v["balance"] == 8500 and "Other Person" not in json.dumps(v) and "email" not in json.dumps(v)
    qr = outsider.get(f"/api/r/{token}/qr.svg")
    assert qr.status_code == 200 and qr.mimetype == "image/svg+xml" and b"<svg" in qr.data
    assert outsider.get("/r/not-a-real-token-123").status_code == 404
    assert outsider.get("/api/r/not-a-real-token-123").status_code == 404


def test_no_limit_while_payments_are_off(client, owner):
    for i in range(7):
        add(client, name=f"Tenant {i}", room=str(i))
    assert client.get("/api/rent").json["plan"]["at_limit"] is False


def test_free_plan_limit_and_pro_lifts_it(app, client, owner):
    from flux.db import get_db

    app.config.update(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s")
    for i in range(5):
        add(client, name=f"Tenant {i}", room=str(i))
    r = client.post("/api/rent/tenants", json={"name": "Sixth", "rent": 5000})
    assert r.status_code == 402
    assert client.get("/api/rent").json["plan"]["at_limit"] is True
    with app.app_context():
        get_db().execute("UPDATE users SET plan_until = '2026-12-20' WHERE id = ?", (owner["id"],))
        get_db().commit()
    assert client.post("/api/rent/tenants", json={"name": "Sixth", "rent": 5000}).status_code == 201


def test_bulk_add_and_validation(client, owner):
    r = client.post("/api/rent/tenants", json={"tenants": [{"name": "A One", "rent": 5000}, {"name": "B Two", "rent": 6000}]})
    assert r.status_code == 201 and len(r.json["ids"]) == 2
    assert client.post("/api/rent/tenants", json={"name": "", "rent": 5000}).status_code == 400
    assert client.post("/api/rent/tenants", json={"name": "X", "rent": 5000, "phone": "123"}).status_code == 400
    assert client.put("/api/rent/property", json={"name": "PG", "upi_id": "not a upi"}).status_code == 400


def test_other_users_cannot_touch_my_tenants(app, client, owner, monkeypatch):
    from conftest import login

    tid = add(client)
    other = app.test_client()
    import conftest

    other_client = conftest.Client(app) if hasattr(conftest, "Client") else None
    if other_client is None:
        pytest.skip("no client helper")
    login(other_client, monkeypatch, email="someone@else.com", name="Someone Else")
    assert other_client.get(f"/api/rent/tenants/{tid}").status_code == 404
    assert other_client.patch(f"/api/rent/tenants/{tid}", json={"rent": 1}).status_code == 404
    assert other_client.delete(f"/api/rent/tenants/{tid}").status_code == 404


# ─── Billing ─────────────────────────────────────────────────
def test_billing_is_off_without_keys(client, owner):
    b = client.get("/api/billing").json
    assert b["enabled"] is False and b["plans"][0]["price"] == 299
    assert client.post("/api/billing/order", json={"plan": "rent_month"}).status_code == 503


def test_razorpay_order_verify_and_webhook_give_the_plan_once(app, client, owner, monkeypatch):
    import flux.billing as billing

    app.config.update(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret123", RAZORPAY_WEBHOOK_SECRET="whsec")

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "order_ABC"}

    seen = {}
    monkeypatch.setattr(billing.requests, "post", lambda url, **kw: seen.update(kw) or R())
    o = client.post("/api/billing/order", json={"plan": "rent_year", "amount": 1}).json
    assert o["order_id"] == "order_ABC" and o["amount"] == 299900 and seen["json"]["amount"] == 299900  # price from server
    bad = client.post("/api/billing/verify", json={"razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_1",
                                                    "razorpay_signature": "nope"})
    assert bad.status_code == 400
    sig = hmac.new(b"secret123", b"order_ABC|pay_1", hashlib.sha256).hexdigest()
    ok = client.post("/api/billing/verify", json={"razorpay_order_id": "order_ABC", "razorpay_payment_id": "pay_1",
                                                   "razorpay_signature": sig}).json
    assert ok["until"] == "2027-11-20"
    # The webhook for the same order doesn't add another year.
    body = json.dumps({"event": "order.paid", "payload": {"order": {"entity": {"id": "order_ABC"}},
                                                         "payment": {"entity": {"id": "pay_1"}}}}).encode()
    wsig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    hook = app.test_client().post("/api/billing/webhook", data=body, content_type="application/json",
                                  headers={"X-Razorpay-Signature": wsig})
    assert hook.status_code == 200
    assert client.get("/api/billing").json["until"] == "2027-11-20"
    forged = app.test_client().post("/api/billing/webhook", data=body, content_type="application/json",
                                    headers={"X-Razorpay-Signature": "forged"})
    assert forged.status_code == 400


def test_webhook_alone_activates_a_paid_order(app, client, owner, monkeypatch):
    import flux.billing as billing

    app.config.update(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret123", RAZORPAY_WEBHOOK_SECRET="whsec")

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "order_TAB"}

    monkeypatch.setattr(billing.requests, "post", lambda url, **kw: R())
    client.post("/api/billing/order", json={"plan": "rent_month"})
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_TAB"}}}}).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    app.test_client().post("/api/billing/webhook", data=body, content_type="application/json", headers={"X-Razorpay-Signature": sig})
    b = client.get("/api/billing").json
    assert b["pro"] is True and b["until"] == "2026-12-20" and b["history"][0]["payment_id"] == "pay_9"


def test_public_policy_pages_razorpay_needs(app):
    c = app.test_client()
    for path, words in (("/refunds", "7 days"), ("/contact", "Contact"), ("/terms", "Kitna Rent Pro"), ("/privacy", "collect rent")):
        r = c.get(path)
        assert r.status_code == 200 and words.encode() in r.data, path


def test_owner_sees_rent_tab_flag_and_helper_knows_rent(client, owner):
    assert client.get("/api/auth/me").json["user"]["has_rent"] is True
    from flux.api.help import fallback_answer
    assert "/app/rent" in fallback_answer("how do I collect rent from my PG tenants")["links"]
