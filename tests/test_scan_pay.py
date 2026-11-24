"""Scan & Pay: read a UPI QR, hand a pre-filled request to the user's own UPI app, log it once."""
import pytest

from flux import clock
from flux.security import ApiError
from flux.upi import build_links, parse_upi_uri


def test_parse_merchant_qr():
    p = parse_upi_uri("upi://pay?pa=swiggy.stores@icici&pn=Swiggy%20Limited&mc=5812&tr=ORD123&am=249.00&cu=INR")
    assert p["pa"] == "swiggy.stores@icici" and p["pn"] == "Swiggy Limited"
    assert str(p["am"]) == "249.00" and p["mc"] == "5812" and p["is_merchant"]


def test_parse_person_qr_and_bare_upi_id():
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
    links = build_links("shop@okhdfc", "Chai & Co", "45.5")
    assert links["generic"] == "upi://pay?pa=shop@okhdfc&pn=Chai%20%26%20Co&am=45.50&cu=INR"
    gpay = next(a for a in links["apps"] if a["id"] == "gpay")
    assert gpay["android"].endswith("package=com.google.android.apps.nbu.paisa.user;end")
    assert gpay["ios"].startswith("gpay://upi/pay?pa=shop@okhdfc")
    with pytest.raises(ApiError):
        build_links("x@y\"><script>", "n", "10")


def test_person_link_has_no_made_up_reference():
    # GPay declines person-to-person links carrying a 'tr' the payee didn't issue.
    g = build_links("friend@oksbi", "Ravi", "200", "upi://pay?pa=friend@oksbi&pn=Ravi")["generic"]
    assert "tr=" not in g and "tn=" not in g
    assert g == "upi://pay?pa=friend@oksbi&pn=Ravi&am=200.00&cu=INR"


def test_shop_qr_is_passed_on_unchanged():
    raw = "upi://pay?pa=shop@ybl&pn=Shop&mc=5411&tr=ABC123&mode=02&sign=xyz%2Babc&orgid=000000"
    g = build_links("shop@ybl", "Shop", "99", raw)["generic"]
    for part in ("mc=5411", "tr=ABC123", "mode=02", "orgid=000000", "am=99.00", "cu=INR"):
        assert part in g
    assert "sign=xyz%2Babc" in g


def test_scan_and_pay_end_to_end(client, user):
    client.post("/api/transactions", json={"kind": "income", "amount": 5000, "category": "Salary"})
    d = client.post("/api/pay/parse", json={"code": "upi://pay?pa=zomato@hdfc&pn=Zomato&mc=5812&am=347"}).json
    assert d["category"] == "Food & Dining" and d["amount"] == 347 and d["category_reason"] == "merchant code"
    prep = client.post("/api/pay/prepare", json={"vpa": d["vpa"], "name": d["name"], "amount": 347, "category": d["category"]}).json
    assert prep["links"]["generic"].startswith("upi://pay?pa=zomato@hdfc") and prep["ref"].startswith("KTN")
    # Nothing is logged until the user says it went through.
    assert not any(t["amount"] == 347 for t in client.get("/api/transactions").json["items"])
    r = client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"})
    assert r.status_code == 200
    tx = client.get("/api/transactions").json["items"]
    assert [t["source"] for t in tx if t["amount"] == 347] == ["upi"]
    assert client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"}).status_code == 409
    again = client.post("/api/pay/parse", json={"code": "zomato@hdfc"}).json
    assert again["known_payee"] and again["category"] == "Food & Dining"
    assert [p["vpa"] for p in client.get("/api/pay/payees").json] == ["zomato@hdfc"]


def test_the_bank_sms_for_the_same_payment_is_not_counted_twice(client, user, app):
    client.post("/api/transactions", json={"kind": "income", "amount": 5000, "category": "Salary"})
    prep = client.post("/api/pay/prepare", json={"vpa": "chai@ybl", "name": "Chai Point", "amount": 120, "category": "Food & Dining"}).json
    client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"})
    token = client.post("/api/ingest/token").json["token"]
    day = clock.today().strftime("%d-%m-%y")
    sms = f"Rs.120.00 debited from A/c XX1234 on {day} to VPA chai@ybl (UPI Ref No 512345678901). Not you? Call 1800"
    app.test_client().post("/api/ingest/sms", json={"text": sms}, headers={"Authorization": f"Bearer {token}"})
    assert len([t for t in client.get("/api/transactions").json["items"] if t["amount"] == 120]) == 1


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


def test_voice_pay_opens_scan_and_pay(client, user):
    prep = client.post("/api/pay/prepare", json={"vpa": "rahul.k@okaxis", "name": "Rahul K", "amount": 50, "category": "Other"}).json
    client.post(f"/api/pay/{prep['payment_id']}/confirm", json={"status": "paid"})
    r = client.post("/api/voice/command", json={"text": "pay 200 to rahul"}).json
    assert r["navigate"].startswith("/app/pay?") and "rahul.k%40okaxis" in r["navigate"] and "amount=200.00" in r["navigate"]
    assert client.post("/api/voice/command", json={"text": "scan qr"}).json["navigate"] == "/app/pay"


def test_pay_page_needs_sign_in(app):
    r = app.test_client().get("/app/pay")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_bank_email_completes_a_pending_scan_and_pay(app, client, user):
    from flux.api.ingest import ingest_row
    from flux.db import get_db

    client.post("/api/transactions", json={"kind": "income", "amount": 5000, "category": "Salary"})
    prep = client.post("/api/pay/prepare", json={"vpa": "chai@ybl", "name": "Sharma Chai", "amount": 30,
                                                 "category": "Food & Dining"}).json
    assert prep["links"]["apps"][0]["open_ios"] == "gpay://"
    with app.app_context():
        u = get_db().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        from flux.clock import today
        out = ingest_row(u, {"kind": "expense", "amount": 30.0, "date": today().isoformat(), "note": "******3484",
                             "category": "Other", "raw": "debited Rs 30", "ref": "123456789012"}, "email")
        assert out["logged"] and out["category"] == "Food & Dining"
        p = get_db().execute("SELECT status, transaction_id FROM payments WHERE id = ?", (prep["payment_id"],)).fetchone()
        assert p["status"] == "paid" and p["transaction_id"] == out["transaction_id"]
        t = get_db().execute("SELECT note FROM transactions WHERE id = ?", (out["transaction_id"],)).fetchone()
        assert t["note"].startswith("Sharma Chai")


def test_auto_payment_waits_on_today_then_one_tap_teaches_kitna(app, client, user):
    from flux.api.ingest import ingest_row
    from flux.clock import today
    from flux.db import get_db

    def bank(amount, raw):
        with app.app_context():
            u = get_db().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            r = ingest_row(u, {"kind": "expense", "amount": amount, "date": today().isoformat(), "note": "UPI payment ••3484",
                               "category": "Other", "raw": raw}, "email")
            get_db().commit()
            return r

    first = bank(40.0, "debited 40 a")
    d = client.get("/api/dashboard").json
    assert d["to_sort_count"] == 1 and d["to_sort"][0]["id"] == first["transaction_id"]
    r = client.post(f"/api/transactions/{first['transaction_id']}/sort", json={"category": "Food & Dining", "name": "Sharma Chai"})
    assert r.status_code == 200
    assert client.get("/api/dashboard").json["to_sort_count"] == 0
    # Next payment to the same hidden payee arrives already named and filed, nothing to sort.
    second = bank(25.0, "debited 25 b")
    assert second["category"] == "Food & Dining"
    d = client.get("/api/dashboard").json
    assert d["to_sort_count"] == 0
    assert d["recent"][0]["note"] == "Sharma Chai"
