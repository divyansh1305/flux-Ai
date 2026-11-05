"""Product events, nightly totals and the private numbers page."""
from conftest import Client, login


def tok(client):
    return client.post("/api/ingest/token").json["token"]


def test_events_follow_a_real_journey_and_hold_no_money_data(app, client, monkeypatch):
    user = login(client, monkeypatch)
    client.patch("/api/account", json={"adult_confirmed": True})
    client.patch("/api/account", json={"income_pattern": "monthly", "pay_day": 1})
    client.patch("/api/account", json={"onboarded": True})
    t = tok(client)
    app.test_client().post("/api/ingest/sms", json={"text": "Rs.250.00 debited from A/c XX1234 to VPA swiggy@icici (UPI Ref No 628800000777)"},
                           headers={"Authorization": f"Bearer {t}"})
    app.test_client().post("/api/ingest/sms", json={"text": "Dear customer your a/c statement for Oct is ready"},
                           headers={"Authorization": f"Bearer {t}"})
    client.post("/api/plans", json={"title": "Dinner with Aman", "amount": 2000})
    client.post("/api/events", json={"name": "screen_opened", "prop": "home"})
    client.post("/api/voice/command", json={"text": "aaj kitna kharch kar sakta hoon"})
    with app.app_context():
        from flux.db import get_db

        rows = [tuple(r) for r in get_db().execute("SELECT name, prop FROM events WHERE user_id = ? ORDER BY id", (user["id"],))]
    names = [n for n, _ in rows]
    assert ("signed_up", "email") in rows and ("setup_step", "age") in rows and ("setup_step", "done") in rows
    assert ("connected", "phone") in rows and ("auto_payment", "sms") in rows and ("message_unread", "sms") in rows
    assert ("plan_added", "spend") in rows and ("screen_opened", "home") in rows and "asked_flux" in names
    blob = " ".join(f"{n} {p}" for n, p in rows).lower()
    assert "250" not in blob and "swiggy" not in blob and "aman" not in blob and "2000" not in blob


def test_browser_can_only_send_whitelisted_events(client, user):
    assert client.post("/api/events", json={"name": "auto_payment", "prop": "sms"}).status_code == 400
    assert client.post("/api/events", json={"name": "screen_opened", "prop": "my salary is 50000"}).status_code == 200
    k = client.get("/api/account/knows").json
    assert k["counts"]["usage_events"] >= 1


def test_numbers_page_is_only_for_admins(app, client, monkeypatch):
    login(client, monkeypatch, email="owner@example.com", name="Owner")
    assert client.get("/api/admin/overview").status_code == 404
    assert client.get("/app/admin").status_code == 404
    app.config["ADMIN_EMAILS"] = "owner@example.com"
    other = Client(app)
    login(other, monkeypatch, email="friend@example.com", name="Friend")
    assert other.get("/api/admin/overview").status_code == 404
    d = client.get("/api/admin/overview").json
    assert d["totals"]["users"] == 2 and d["funnel"][0]["users"] == 2
    assert client.get("/app/admin").status_code == 200 and client.get("/api/auth/me").json["features"]["admin"] is True
    r = client.post("/api/admin/rollup").json
    assert len(r["rolled_up"]) >= 1


def test_rollup_counts_a_day(app, client, user):
    client.post("/api/events", json={"name": "screen_opened", "prop": "home"})
    with app.app_context():
        from flux import analytics, clock

        stats = analytics.rollup(clock.today())
        assert stats["signups"] == 1 and stats["active_users"] == 1
        stats = analytics.rollup(clock.today())  # running twice doesn't double-count
        from flux.db import get_db

        assert get_db().execute("SELECT value FROM daily_stats WHERE metric='signups'").fetchone()[0] == 1


def test_deleting_account_deletes_events(app, client, user):
    client.post("/api/events", json={"name": "screen_opened", "prop": "home"})
    client.delete("/api/account", json={"confirm": "DELETE"})
    with app.app_context():
        from flux.db import get_db

        assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
