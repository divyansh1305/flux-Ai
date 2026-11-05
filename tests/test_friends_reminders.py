"""Friends (split, auto tick-off), reminders (Web Push end to end), the Sunday note, PDF statements, Hinglish."""
import io
import json
import struct
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from flux import clock, webpush

TODAY = date(2026, 11, 15)  # a Sunday


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def add(client, kind, amount, category, **kw):
    r = client.post("/api/transactions", json={"kind": kind, "amount": amount, "category": category, **kw})
    assert r.status_code == 201, r.json
    return r.json


def ready(client):
    assert client.patch("/api/account", json={"adult_confirmed": True, "onboarded": True}).status_code == 200


# ─── A fake phone: makes real keys, receives pushes and decrypts them like a browser does ──
class Phone:
    def __init__(self, endpoint="https://fcm.googleapis.com/fcm/send/abc123"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = b"0123456789abcdef"
        self.endpoint = endpoint
        self.inbox, self.status = [], 201

    def subscription(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": webpush.b64u(webpush._point(self.key.public_key())),
                                                   "auth": webpush.b64u(self.auth)}}

    def decrypt(self, body):  # RFC 8188 / 8291 receiver side, written independently of flux.webpush
        salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
        as_public = body[21:21 + idlen]
        ct = body[21 + idlen:]
        assert rs == 4096 and len(as_public) == 65
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
        ua_public = webpush._point(self.key.public_key())
        hk = lambda salt, ikm, info, n: HKDF(hashes.SHA256(), n, salt, info).derive(ikm)  # noqa: E731
        ikm = hk(self.auth, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
        cek = hk(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = hk(salt, ikm, b"Content-Encoding: nonce\x00", 12)
        plain = AESGCM(cek).decrypt(nonce, ct, None)
        assert plain.endswith(b"\x02")
        return json.loads(plain[:-1])

    def post(self, url, data, headers, timeout):
        assert url == self.endpoint and headers["Content-Encoding"] == "aes128gcm"
        assert headers["Authorization"].startswith("vapid t=")
        self.inbox.append(self.decrypt(data))

        class R:
            status_code = self.status
        return R()


@pytest.fixture
def phone(app):
    p = Phone()
    app.config["PUSH_POST"] = p.post
    return p


# ─── Web Push building blocks ────────────────────────────────
def test_vapid_token_is_a_valid_es256_jwt_for_the_push_service():
    key = ec.generate_private_key(ec.SECP256R1())
    h = webpush.vapid_headers("https://web.push.apple.com/abc", key, "mailto:a@b.c", now=1_800_000_000)
    token, k = h["Authorization"][len("vapid t="):].split(", k=")
    head, claims, sig = token.split(".")
    raw = webpush.unb64u(sig)
    key.public_key().verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                            f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert json.loads(webpush.unb64u(claims)) == {"aud": "https://web.push.apple.com", "exp": 1_800_000_000 + 43200, "sub": "mailto:a@b.c"}
    assert k == webpush.public_key_b64(key)


def test_only_real_push_services_are_allowed():
    good = ["https://fcm.googleapis.com/fcm/send/x", "https://web.push.apple.com/x", "https://updates.push.services.mozilla.com/x"]
    bad = ["https://evil.com/x", "http://fcm.googleapis.com/x", "https://fcm.googleapis.com.evil.com/x",
           "https://fcm.googleapis.com:8443/x", "https://127.0.0.1/x", "file:///etc/passwd"]
    assert all(webpush.allowed_endpoint(u) for u in good)
    assert not any(webpush.allowed_endpoint(u) for u in bad)


def test_server_key_is_created_once_and_kept(tmp_path):
    webpush._key_cache.clear()
    a = webpush.public_key_b64(webpush.server_key(str(tmp_path)))
    webpush._key_cache.clear()
    assert webpush.public_key_b64(webpush.server_key(str(tmp_path))) == a
    assert oct((tmp_path / "vapid_private.key").stat().st_mode & 0o777) == "0o600"


# ─── Turning reminders on ────────────────────────────────────
def test_subscribe_sends_an_encrypted_test_the_phone_can_read(client, user, phone):
    r = client.post("/api/reminders/subscribe", json=phone.subscription())
    assert r.status_code == 200 and r.json["test_sent"] is True
    assert phone.inbox[0]["title"] == "Reminders are on" and phone.inbox[0]["url"] == "/app/settings"
    info = client.get("/api/reminders").json
    assert info["phones"] == 1 and len(webpush.unb64u(info["public_key"])) == 65


def test_subscribe_refuses_other_addresses_and_bad_keys(client, user):
    p = Phone("https://evil.example.com/hook")
    assert client.post("/api/reminders/subscribe", json=p.subscription()).status_code == 400
    p = Phone()
    sub = p.subscription()
    sub["keys"]["auth"] = "short"
    assert client.post("/api/reminders/subscribe", json=sub).status_code == 400


def test_a_phone_that_unsubscribed_is_forgotten(client, user, phone, app):
    phone.status = 410
    client.post("/api/reminders/subscribe", json=phone.subscription())
    assert client.get("/api/reminders").json["phones"] == 0


def test_reminder_types_can_be_turned_off(client, user):
    assert client.patch("/api/reminders", json={"kinds": ["bills", "friends"]}).json["kinds"] == ["bills", "friends"]
    assert client.patch("/api/reminders", json={"kinds": ["spam"]}).status_code == 400


# ─── Friends ─────────────────────────────────────────────────
def test_split_counts_only_your_share_but_balance_stays_real(client, user):
    add(client, "income", 10000, "Salary")
    tx = add(client, "expense", 2000, "Food & Dining", note="Dinner at Social")["transaction"]
    r = client.post("/api/friends/split", json={"transaction_id": tx["id"], "people": [
        {"name": "Rahul Sharma", "amount": 500}, {"name": "Priya", "amount": 500}, {"name": "Aman", "amount": 500}]})
    assert r.status_code == 201 and r.json["totals"]["they_owe"] == 1500
    d = client.get("/api/dashboard").json
    assert d["balance"] == 8000                       # the bank really has 8,000
    assert d["month"]["expenses"] == 500              # but you only spent 500
    assert d["month"]["by_category"][0] == {"category": "Food & Dining", "amount": 500}
    assert d["safe"]["owed_to_you"] == 1500           # shown, not counted
    too_much = client.post("/api/friends/split", json={"transaction_id": tx["id"], "people": [{"name": "X", "amount": 600}]})
    assert too_much.status_code == 400


def test_friend_paying_back_on_upi_is_ticked_off_by_itself(client, user, phone):
    client.post("/api/reminders/subscribe", json=phone.subscription())
    add(client, "income", 10000, "Salary")
    tx = add(client, "expense", 1000, "Food & Dining", note="Pizza")["transaction"]
    client.post("/api/friends/split", json={"transaction_id": tx["id"], "people": [{"name": "Rahul Sharma", "amount": 500}]})
    back = add(client, "income", 500, "Other Income", note="RAHUL SHARMA")  # what the bank SMS says
    assert back["paid_back"] == {"person": "Rahul Sharma", "amount": 500, "direction": "they_owe"}
    f = client.get("/api/friends").json
    assert f["open"] == [] and f["settled"][0]["settled"] is True
    d = client.get("/api/dashboard").json
    assert d["month"]["income"] == 10000              # being paid back isn't income
    assert phone.inbox[-1]["title"] == "Rahul paid you back ₹500"


def test_same_amount_without_a_name_is_asked_not_guessed(client, user):
    add(client, "income", 5000, "Salary")
    client.post("/api/friends", json={"person": "Priya Singh", "amount": 300, "note": "Movie"})
    tx = add(client, "income", 300, "Other Income", note="UPI credit")["transaction"]
    f = client.get("/api/friends").json
    assert len(f["open"]) == 1 and f["suggestions"][0]["suggested_tx_id"] == tx["id"]
    oid = f["suggestions"][0]["id"]
    assert client.post(f"/api/friends/{oid}/settle", json={"transaction_id": tx["id"]}).json["settled"] is True
    assert client.get("/api/friends").json["open"] == []


def test_money_you_owe_is_kept_aside_in_todays_number(client, user):
    add(client, "income", 3000, "Pocket Money")
    before = client.get("/api/dashboard").json["safe"]["pool"]
    client.post("/api/friends", json={"person": "Aman", "amount": 600, "direction": "i_owe"})
    s = client.get("/api/dashboard").json["safe"]
    assert s["pool"] == before - 600 and any(l["label"] == "Money you owe friends" for l in s["lines"])
    add(client, "expense", 600, "Transfers", note="AMAN GUPTA")   # you pay him on UPI
    assert client.get("/api/friends").json["totals"]["i_owe"] == 0


def test_reminder_message_includes_upi_id(client, user):
    assert client.patch("/api/account", json={"upi_id": "not a upi"}).status_code == 400
    client.patch("/api/account", json={"upi_id": "riya@okhdfcbank"})
    oid = client.post("/api/friends", json={"person": "Rahul", "amount": 450, "note": "cab"}).json["id"]
    text = client.get(f"/api/friends/{oid}/message").json["text"]
    assert "₹450" in text and "cab" in text and "riya@okhdfcbank" in text


def test_friends_data_is_private_to_each_user(client, user, app, monkeypatch):
    from conftest import Client, login

    oid = client.post("/api/friends", json={"person": "Rahul", "amount": 450}).json["id"]
    other = Client(app)
    login(other, monkeypatch, email="sam@example.com", name="Sam")
    assert other.get(f"/api/friends/{oid}/message").status_code == 404
    other.delete(f"/api/friends/{oid}")
    assert len(client.get("/api/friends").json["open"]) == 1


# ─── Daily reminders ─────────────────────────────────────────
def test_daily_reminders_pick_the_important_few_and_never_repeat(client, user, phone, app):
    ready(client)
    client.post("/api/reminders/subscribe", json=phone.subscription())
    add(client, "income", 20000, "Salary", date=(TODAY - timedelta(days=20)).isoformat())
    for months_ago in (2, 1):  # Netflix on the 16th → due tomorrow
        d = (TODAY.replace(day=16) - timedelta(days=30 * months_ago)).isoformat()
        add(client, "expense", 649, "Subscriptions", note="Netflix", date=d)
    client.post("/api/plans", json={"kind": "spend", "title": "Dinner", "amount": 2000, "date": (TODAY + timedelta(days=1)).isoformat()})
    client.post("/api/friends", json={"person": "Rahul", "amount": 500, "date": (TODAY - timedelta(days=5)).isoformat()})
    add(client, "expense", 300, "Food & Dining", note="Swiggy", date=(TODAY - timedelta(days=2)).isoformat())
    from flux import reminders

    phone.inbox.clear()
    with app.app_context():
        first = reminders.run_daily(TODAY)
        again = reminders.run_daily(TODAY)
    kinds = [n["tag"] for n in phone.inbox]
    assert first["made"] >= 4 and len(phone.inbox) == 3 and again == {"users": 1, "made": 0, "pushed": 0}
    assert kinds == ["bills", "friends", "weekly"]  # most important first; morning waits in the app
    bills = phone.inbox[0]
    assert "Netflix" in bills["body"] and "Dinner" in bills["body"]
    inbox = client.get("/api/reminders").json["inbox"]
    assert {i["kind"] for i in inbox} >= {"bills", "friends", "weekly", "morning"}


def test_late_refund_reminder_quotes_the_rbi_rule(client, user, app):
    ready(client)
    add(client, "income", 5000, "Salary")
    from flux import reminders
    from flux.db import get_db

    with app.app_context():
        get_db().execute("INSERT INTO refund_watch (user_id, amount, date, note, fingerprint) VALUES (?,?,?,?,?)",
                         (user["id"], 45000, (TODAY - timedelta(days=7)).isoformat(), "Zomato", "f1"))
        get_db().commit()
        u = get_db().execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        items = reminders.build(u, TODAY)
    assert items[0]["kind"] == "refunds" and "₹450" in items[0]["title"] and "₹100" in items[0]["body"]


# ─── Sunday note and Hinglish ────────────────────────────────
def test_weekly_note_compares_with_usual_weeks(client, user):
    for weeks_ago in (1, 2, 3):
        add(client, "expense", 1000 if weeks_ago > 1 else 600, "Food & Dining", note="Lunch",
            date=(TODAY - timedelta(days=7 * weeks_ago - 3)).isoformat())
    n = client.get("/api/weekly").json
    assert n["spent"] == 600 and n["usual"] == 1000
    assert n["headline"] == "You spent ₹600 this week, ₹400 less than usual. Nice."
    client.patch("/api/account", json={"lang": "hinglish"})
    assert client.get("/api/weekly").json["headline"].startswith("Is hafte ₹600 kharch hue, aam se ₹400 kam")
    assert client.patch("/api/account", json={"lang": "klingon"}).status_code == 400


# ─── PDF statements ──────────────────────────────────────────
def _statement_pdf(password=None):
    from reportlab.lib import pdfencrypt
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    enc = pdfencrypt.StandardEncryption(password, canPrint=1, strength=128) if password else None
    c = canvas.Canvas(buf, pagesize=A4, encrypt=enc)
    y = 780
    for row in [[(40, "Date"), (110, "Narration"), (400, "Withdrawal Amt."), (480, "Deposit Amt."), (550, "Closing Balance")],
                [(40, "01/11/26"), (110, "UPI-SWIGGY-swiggy@icici-430512345678"), (450, "450.00"), (590, "24,550.00")],
                [(40, "02/11/26"), (110, "UPI-RAHUL SHARMA-rahul@okaxis"), (530, "500.00"), (590, "25,050.00")],
                [(110, "dinner share")],
                [(40, "03/11/26"), (110, "NEFT CR-ACME TECH PVT LTD-SALARY"), (530, "45,000.00"), (590, "70,050.00")]]:
        for x, t in row:
            (c.drawRightString if t[0].isdigit() and "." in t else c.drawString)(x, y, t)
        y -= 16
    c.save()
    return buf.getvalue()


def _preview(client, data, password=None):
    form = {"file": (io.BytesIO(data), "statement.pdf")}
    if password:
        form["password"] = password
    return client.post("/api/import/preview", data=form, content_type="multipart/form-data")


def test_pdf_statement_reads_columns_and_multiline_narration(client, user):
    r = _preview(client, _statement_pdf())
    assert r.status_code == 200 and r.json["format"] == "pdf"
    rows = [(x["date"], x["kind"], x["amount"], x["category"]) for x in r.json["rows"]]
    assert rows == [("2026-11-01", "expense", 450.0, "Food & Dining"), ("2026-11-02", "income", 500.0, "Other Income"),
                    ("2026-11-03", "income", 45000.0, "Salary")]
    assert "dinner share" in r.json["rows"][1]["raw"] and r.json["rows"][2]["balance"] == 70050.0
    c = client.post("/api/import/commit", json={"rows": r.json["rows"], "format": "pdf"})
    assert c.json["imported"] == 3


def test_password_protected_pdf_asks_then_opens(client, user):
    data = _statement_pdf("DIVY0513")
    first = _preview(client, data).json
    assert first["needs_password"] is True and first["wrong"] is False
    assert _preview(client, data, "nope").json["wrong"] is True
    assert len(_preview(client, data, "DIVY0513").json["rows"]) == 3


def test_not_a_statement_is_refused_clearly(client, user):
    r = client.post("/api/import/preview", data={"file": (io.BytesIO(b"%PDF-1.4 garbage"), "x.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and "PDF" in r.json["error"]


# ─── Your data ───────────────────────────────────────────────
def test_export_and_delete_cover_friends_and_reminders(client, user, phone, app):
    client.post("/api/reminders/subscribe", json=phone.subscription())
    client.post("/api/friends", json={"person": "Rahul", "amount": 450})
    exp = json.loads(client.get("/api/account/export").data)
    assert exp["friends"][0]["person"] == "Rahul" and exp["phones_with_reminders"] == 1 and exp["reminders"]
    knows = client.get("/api/account/knows").json["counts"]
    assert knows["friends"] == 1 and knows["phones_with_reminders"] == 1
    assert client.delete("/api/account", json={"confirm": "DELETE"}).status_code == 200
    from flux.db import get_db

    with app.app_context():
        for t in ("owed", "notifications", "push_subscriptions"):
            assert get_db().execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_bank_sms_from_a_friend_ticks_them_off(client, user, app):
    add(client, "income", 5000, "Salary")
    tx = add(client, "expense", 900, "Food & Dining", note="Dominos")["transaction"]
    client.post("/api/friends/split", json={"transaction_id": tx["id"], "people": [{"name": "Rahul", "amount": 300},
                                                                                  {"name": "Priya Singh", "amount": 300}]})
    token = client.post("/api/ingest/token").json["token"]
    sms = ("Dear Customer, Rs.300.00 credited to your A/c XX1234 on 15-11-26 by UPI ref no 430512345678 "
           "from PRIYA SINGH (priya.s@okicici). -Kotak Bank")
    r = app.test_client().post("/api/ingest/sms", json={"text": sms}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 201), r.json
    open_rows = client.get("/api/friends").json["open"]
    assert [o["person"] for o in open_rows] == ["Rahul"]  # Priya ticked off, Rahul (same amount) left alone


def test_a_friend_paying_a_day_before_the_bill_still_counts(client, user):
    add(client, "income", 5000, "Salary")
    tx = add(client, "expense", 600, "Food & Dining", note="Pizza", date=TODAY.isoformat())["transaction"]
    client.post("/api/friends/split", json={"transaction_id": tx["id"], "people": [{"name": "Rahul", "amount": 300}]})
    back = add(client, "income", 300, "Other Income", note="RAHUL", date=(TODAY - timedelta(days=1)).isoformat())
    assert back["paid_back"]["person"] == "Rahul"
