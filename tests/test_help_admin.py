"""Kitna helper (support chat) and the admin People view."""
import json

from conftest import Client, login

from flux import ai
from flux.api import help as helpmod


def ask(client, text, lang="en", history=None):
    msgs = (history or []) + [{"role": "user", "text": text}]
    return client.post("/api/help/chat", json={"messages": msgs, "lang": lang, "screen": "home"})


def test_helper_without_ai_answers_from_the_guide(app, client, user):
    r = ask(client, "How do I split a bill with friends?")
    assert r.status_code == 200
    assert r.json["fallback"] is True and r.json["answered"] is True
    assert "Friends" in r.json["reply"]
    assert {"href": "/app/friends", "label": "Open Friends"} in r.json["links"]


def test_helper_says_what_it_cannot_do_for_off_topic_questions(app, client, user):
    r = ask(client, "Who won the cricket world cup?")
    assert r.json["answered"] is False and "Tell us something" in r.json["reply"]


def test_helper_uses_ai_with_the_guide_and_language_and_keeps_links_safe(app, client, user, monkeypatch):
    seen = {}

    def fake_chat(history, system, **kw):
        seen["system"], seen["history"] = system, history
        return {"reply": "Upcoming tab → Add.", "links": ["/app/plans", "https://evil.example", "/app/admin"], "answered": True}

    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "chat", fake_chat)
    r = ask(client, "plan kaise add karu?", lang="hinglish",
            history=[{"role": "user", "text": "hi"}, {"role": "assistant", "text": "Hello!"}])
    assert r.json["reply"] == "Upcoming tab → Add."
    assert r.json["links"] == [{"href": "/app/plans", "label": "Open Upcoming"}]   # outside links dropped
    assert "Hinglish" in seen["system"] and "KITNA GUIDE" in seen["system"] and "Today's number" in seen["system"]
    assert [h["role"] for h in seen["history"]] == ["user", "model", "user"]


def test_helper_falls_back_when_ai_fails(app, client, user, monkeypatch):
    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "chat", lambda *a, **k: None)
    r = ask(client, "scan camera not opening on iphone")
    assert r.json["fallback"] is True and "Camera" in r.json["reply"]


def test_helper_rejects_bad_input_and_unknown_language_becomes_english(app, client, user):
    assert client.post("/api/help/chat", json={"messages": []}).status_code == 400
    assert client.post("/api/help/chat", json={"messages": [{"role": "assistant", "text": "x"}]}).status_code == 400
    assert ask(client, "how do reminders work", lang="klingon").status_code == 200


def test_helper_questions_are_masked_exported_and_deleted_with_the_account(app, client, user):
    ask(client, "my otp is 123456 what now")
    data = json.loads(client.get("/api/account/export").data)
    assert data["helper_questions"][0]["question"] == "my otp is ###### what now"
    client.delete("/api/account", json={"confirm": "DELETE"})
    from flux.db import get_db

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM help_questions").fetchone()[0] == 0


def test_every_guide_link_is_allowed():
    import re

    for path in re.findall(r"\[(/[^\]]*)\]", helpmod.guide()):
        assert path in helpmod.ALLOWED_LINKS, path


def test_admin_people_view_shows_setup_not_money(app, client, user, monkeypatch):
    client.post("/api/transactions", json={"kind": "expense", "amount": 347, "category": "Food & Dining", "note": "Zomato"})
    ask(client, "how do I connect gmail")
    assert client.get("/api/admin/users").status_code == 404     # not an admin
    app.config["ADMIN_EMAILS"] = "boss@kitna.test"
    boss = Client(app)
    login(boss, monkeypatch, email="boss@kitna.test", name="Boss")
    r = boss.get("/api/admin/users?q=riya").json
    assert r["total"] == 1 and r["users"][0]["email"] == "riya@example.com" and r["users"][0]["payments"] == 1
    d = boss.get(f"/api/admin/users/{r['users'][0]['id']}").json
    blob = json.dumps(d)
    assert "347" not in blob and "Zomato" not in blob                # no amounts or payment notes
    assert d["helper_questions"][0]["question"] == "how do I connect gmail"
    csv = boss.get("/api/admin/users.csv")
    assert csv.status_code == 200 and b"riya@example.com" in csv.data
    h = boss.get("/api/admin/help").json
    assert h["total_30d"] == 1 and h["recent"][0]["email"] == "riya@example.com"
