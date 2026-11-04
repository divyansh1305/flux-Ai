"""The money maths must be exactly right."""
from datetime import date, timedelta

from flux.finance import compute_autosave


def add(client, kind, amount, category, **kw):
    r = client.post("/api/transactions", json={"kind": kind, "amount": amount, "category": category, **kw})
    assert r.status_code == 201, r.json
    return r.json


def test_round_up_maths():
    assert compute_autosave(4700, "roundup", 10) == 300      # ₹47 -> save ₹3
    assert compute_autosave(10100, "roundup", 10) == 900     # ₹101 -> save ₹9 (old code saved ₹99!)
    assert compute_autosave(5000, "roundup", 10) == 0        # exact multiple -> nothing
    assert compute_autosave(12000, "roundup", 100) == 8000   # ₹120 to next ₹100
    assert compute_autosave(40000, "percent", 5) == 2000     # 5% of ₹400
    assert compute_autosave(40000, "off", 5) == 0


def test_balance_never_creates_money(client, user):
    """Old bug: auto-invest created ₹104 out of nothing while balance stayed ₹899."""
    add(client, "income", 1000, "Salary")
    goal = client.post("/api/goals", json={"title": "Laptop", "target": 50000}).json
    r = add(client, "expense", 101, "Food & Dining", note="lunch")
    assert r["autosaved"] == 9
    d = client.get("/api/dashboard").json
    # 1000 - 101 - 9 = 890 in balance, 9 in the goal. Total = 899. No money created.
    assert d["balance"] == 890
    assert d["total_saved"] == 9
    assert d["balance"] + d["total_saved"] == 1000 - 101
    assert client.get("/api/goals").json[0]["saved"] == 9


def test_autosave_skips_when_balance_too_low(client, user):
    client.post("/api/goals", json={"title": "Trip", "target": 5000})
    r = add(client, "expense", 47, "Transport")
    assert r["autosaved"] == 0  # no income yet, so nothing to move


def test_deleting_expense_removes_its_autosave(client, user):
    add(client, "income", 500, "Pocket Money")
    client.post("/api/goals", json={"title": "Trip", "target": 5000})
    r = add(client, "expense", 47, "Transport")
    client.delete(f"/api/transactions/{r['transaction']['id']}")
    d = client.get("/api/dashboard").json
    assert d["balance"] == 500 and d["total_saved"] == 0


def test_goal_contribution_and_limits(client, user):
    add(client, "income", 1000, "Salary")
    g = client.post("/api/goals", json={"title": "Phone", "target": 20000}).json
    r = client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 400})
    assert r.json["goal"]["saved"] == 400 and r.json["balance"] == 600
    assert client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 5000}).status_code == 400
    assert client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 500, "withdraw": True}).status_code == 400
    r = client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 100, "withdraw": True})
    assert r.json["goal"]["saved"] == 300 and r.json["balance"] == 700
    client.delete(f"/api/goals/{g['id']}")
    assert client.get("/api/dashboard").json["balance"] == 1000


def test_validation(client, user):
    bad = [
        {"kind": "expense", "amount": -5, "category": "Food & Dining"},
        {"kind": "expense", "amount": 0, "category": "Food & Dining"},
        {"kind": "expense", "amount": "abc", "category": "Food & Dining"},
        {"kind": "expense", "amount": 1e12, "category": "Food & Dining"},
        {"kind": "expense", "amount": 10, "category": "Hacking"},
        {"kind": "transfer", "amount": 10, "category": "Food & Dining"},
        {"kind": "expense", "amount": 10, "category": "Food & Dining", "date": "31-31-2020"},
        {"kind": "expense", "amount": 10, "category": "Food & Dining", "note": "x" * 500},
    ]
    for body in bad:
        assert client.post("/api/transactions", json=body).status_code == 400, body


def test_paise_precision(client, user):
    for _ in range(10):
        add(client, "income", 0.1, "Gift")
    assert client.get("/api/dashboard").json["balance"] == 1.0


def test_budgets_and_pre_spend_check(client, user):
    add(client, "income", 20000, "Salary")
    assert client.put("/api/budgets/Food & Dining", json={"limit": 3000}).status_code == 200
    add(client, "expense", 2500, "Food & Dining")
    chk = client.post("/api/transactions/check", json={"amount": 800, "category": "Food & Dining"}).json
    assert chk["level"] == "stop"
    assert any("over your monthly budget" in w for w in chk["warnings"])
    ok = client.post("/api/transactions/check", json={"amount": 100, "category": "Transport"}).json
    assert ok["level"] == "ok"
    b = client.get("/api/budgets").json[0]
    assert b["spent"] == 2500 and b["left"] == 500


def test_health_score_reflects_money_not_clicks(client, user):
    """Old bug: score went UP with every expense because it counted activity."""
    from datetime import timedelta

    from flux import clock

    add(client, "income", 10000, "Salary")
    add(client, "expense", 2000, "Rent")
    for i in range(1, 6):  # a week of real tracking, so a score is shown at all
        add(client, "expense", 50, "Food & Dining", date=(clock.today() - timedelta(days=i)).isoformat())
    good = client.get("/api/insights").json["health"]["score"]
    for _ in range(5):
        add(client, "expense", 1500, "Shopping")
    worse = client.get("/api/insights").json["health"]["score"]
    assert worse < good
    assert 0 <= worse <= 100


def test_forecast(client, user):
    add(client, "expense", 300, "Food & Dining")
    f = client.get("/api/insights").json["forecast"]
    assert f["spent_so_far"] == 300
    assert f["projected_month_total"] >= 300


def test_transactions_filter_and_paging(client, user):
    add(client, "income", 100, "Gift")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    for i in range(30):
        add(client, "expense", 10 + i, "Food & Dining", date=yesterday)
    r = client.get("/api/transactions?kind=expense&size=25").json
    assert len(r["items"]) == 25 and r["has_more"]
    r2 = client.get("/api/transactions?kind=expense&size=25&page=2").json
    assert len(r2["items"]) == 5 and not r2["has_more"]


def test_exports(client, user):
    add(client, "income", 100, "Gift", note="birthday")
    csv_body = client.get("/api/transactions/export?format=csv").get_data(as_text=True)
    assert "birthday" in csv_body
    pdf = client.get("/api/transactions/export?format=pdf")
    assert pdf.data[:4] == b"%PDF"
    rep = client.get("/api/reports/monthly.pdf")
    assert rep.data[:4] == b"%PDF"
    data = client.get("/api/account/export").json
    assert data["transactions"][0]["amount"] == 100


def test_dates_use_indian_time_not_server_utc(client, user, monkeypatch):
    """Old bug: a UTC server logged evening (IST) payments as 'yesterday'."""
    from datetime import date

    from flux import clock

    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 2))
    r = add(client, "expense", 99, "Food & Dining")
    assert r["transaction"]["date"] == "2026-11-02"


def test_no_score_from_one_day_of_data_and_no_free_budget_points(client, user):
    add(client, "income", 30000, "Salary")
    add(client, "expense", 100, "Food & Dining")
    h = client.get("/api/insights").json["health"]
    assert h["score"] is None and "week" in h["tips"][0]


def test_setup_checklist_tracks_progress(client, user):
    s = client.get("/api/setup").json
    assert s["done"] == 0 and [x["key"] for x in s["steps"]][:2] == ["auto", "income"]
    client.patch("/api/account", json={"income_pattern": "monthly", "pay_day": 1})
    from datetime import timedelta

    from flux import clock

    client.post("/api/plans", json={"title": "Dinner", "amount": 2000, "date": (clock.today() + timedelta(days=3)).isoformat()})
    s2 = client.get("/api/setup").json
    done = {x["key"] for x in s2["steps"] if x["done"]}
    assert {"income", "plan"} <= done and s2["done"] == 2