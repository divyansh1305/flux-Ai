"""In-app feedback and the legal pages."""
import json

from conftest import Client, login


def test_feedback_is_saved_and_only_admins_can_read_it(app, client, user, monkeypatch):
    assert client.post("/api/feedback", json={"kind": "broken", "message": "Swiggy payment didn't show", "screen": "home"}).status_code == 201
    assert client.post("/api/feedback", json={"kind": "nonsense", "message": "hi there"}).status_code == 400
    assert client.post("/api/feedback", json={"kind": "idea", "message": "x"}).status_code == 400
    assert client.get("/api/admin/feedback").status_code == 404           # not an admin: the page doesn't exist
    app.config["ADMIN_EMAILS"] = "boss@kitna.test"
    boss = Client(app)
    login(boss, monkeypatch, email="boss@kitna.test", name="Boss")
    items = boss.get("/api/admin/feedback").json
    assert items[0]["message"] == "Swiggy payment didn't show" and items[0]["status"] == "new"
    boss.post(f"/api/admin/feedback/{items[0]['id']}/read")
    assert boss.get("/api/admin/feedback").json[0]["status"] == "read"


def test_feedback_is_in_the_export_and_goes_with_the_account(app, client, user):
    client.post("/api/feedback", json={"kind": "love", "message": "The friends thing is great"})
    assert json.loads(client.get("/api/account/export").data)["feedback"][0]["kind"] == "love"
    assert client.get("/api/account/knows").json["counts"]["feedback"] == 1
    client.delete("/api/account", json={"confirm": "DELETE"})
    from flux.db import get_db

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 0


def test_terms_and_privacy_show_a_real_contact(app, client):
    app.config["CONTACT_EMAIL"] = "help@example.com"
    t = client.get("/terms").data.decode()
    assert "Terms of use" in t and "mailto:help@example.com" in t and "__CONTACT__" not in t
    assert "help@example.com" in client.get("/privacy").data.decode()
    assert 'href="/terms"' in client.get("/login").data.decode()
