"""Fixing categories, learning merchant rules, measured accuracy and opt-in masked samples."""
import json


def tok(client):
    return client.post("/api/ingest/token").json["token"]


def push(app, token, title, posted_at):
    return app.test_client().post("/api/ingest/notification", headers={"Authorization": f"Bearer {token}"},
                                  json={"package": "com.phonepe.app", "title": title, "body": "", "posted_at": posted_at}).json


def test_fix_category_remember_refile_and_accuracy(app, client, user):
    t = tok(client)
    a = push(app, t, "₹120 paid to Chaayos", 1)
    b = push(app, t, "₹90 paid to Chaayos", 2)
    c = push(app, t, "₹400 paid to Zomato", 3)
    assert a["logged"] and b["logged"] and c["logged"]
    before = client.get("/api/insights").json["accuracy"]
    assert before["auto_logged"] == 3 and before["corrected"] == 0

    # User says Chaayos is "Food & Dining" (whatever Flux guessed) and asks Flux to remember
    target = "Shopping" if a["category"] == "Food & Dining" else "Food & Dining"
    r = client.patch(f"/api/transactions/{a['transaction_id']}", json={"category": target, "remember": True})
    assert r.status_code == 200 and r.json["transaction"]["category"] == target
    assert r.json["refiled"] == 1                         # the ₹90 Chaayos entry was re-filed too
    acc = client.get("/api/insights").json["accuracy"]
    assert acc["corrected"] == 2 and acc["accuracy"] == round(100 / 3, 1)

    # Next Chaayos payment uses the learned rule automatically
    d = push(app, t, "₹150 paid to Chaayos", 4)
    assert d["category"] == target
    assert any(x["merchant_key"] == "chaayos" for x in client.get("/api/rules").json)


def test_edit_validation_and_ownership(app, client, user):
    r = client.post("/api/transactions", json={"kind": "expense", "amount": 50, "category": "Food & Dining", "note": "tea"})
    tx = r.json["transaction"]["id"]
    assert client.patch(f"/api/transactions/{tx}", json={"category": "Salary"}).status_code == 400   # income cat on expense
    assert client.patch(f"/api/transactions/{tx}", json={}).status_code == 400
    assert client.patch("/api/transactions/999999", json={"category": "Shopping"}).status_code == 404
    assert client.patch(f"/api/transactions/{tx}", json={"note": "masala chai"}).json["transaction"]["note"] == "masala chai"


def test_samples_are_opt_in_masked_and_deleted_on_opt_out(app, client, user):
    t = tok(client)
    sms = "Rs.500.00 debited from A/c XX4321 to VPA 9876543210@ybl (UPI Ref No 412345678901). Avl Bal Rs 2,000.00"
    app.test_client().post("/api/ingest/sms", json={"text": sms}, headers={"Authorization": f"Bearer {t}"})
    assert client.get("/api/samples/export").get_data(as_text=True) == ""      # off by default → nothing kept

    assert client.patch("/api/account", json={"contribute_samples": True}).json["user"]["contribute_samples"] is True
    app.test_client().post("/api/ingest/sms", headers={"Authorization": f"Bearer {t}"},
                           json={"text": sms.replace("500.00", "510.00").replace("412345678901", "412345678902")})
    lines = client.get("/api/samples/export").get_data(as_text=True).strip().splitlines()
    assert len(lines) == 1
    s = json.loads(lines[0])
    assert "4321" not in s["text"] and "9876543210" not in s["text"] and "412345678902" not in s["text"]
    assert s["expected"]["amount"] == "510.00" and s["expected"]["direction"] == "debit"

    client.patch("/api/account", json={"contribute_samples": False})
    assert client.get("/api/samples/export").get_data(as_text=True) == ""
