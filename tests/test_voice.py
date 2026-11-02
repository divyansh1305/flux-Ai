"""Voice commands: parsing (English/Hindi/Hinglish) and end-to-end execution."""
import pytest

from flux.voice import parse

CASES = [
    ("spent 250 on swiggy", "add_expense", 250, "Food & Dining"),
    ("I paid ₹1,200 for petrol", "add_expense", 1200, "Transport"),
    ("300 groceries", "add_expense", 300, "Groceries"),
    ("add expense 5k rent", "add_expense", 5000, "Rent"),
    ("spent two hundred fifty on lunch", "add_expense", 250, "Food & Dining"),
    ("maine 200 rupaye chai pe kharch kiye", "add_expense", 200, "Food & Dining"),
    ("मैंने 500 रुपये पेट्रोल पर खर्च किए", "add_expense", 500, "Transport"),
    ("paanch sau ka khana", "add_expense", 500, "Food & Dining"),
    ("bought headphones for 1.5 thousand", "add_expense", 1500, "Shopping"),
    ("got salary 30000", "add_income", 30000, "Salary"),
    ("received 2000 from papa", "add_income", 2000, "Pocket Money"),
    ("papa se 2000 mile", "add_income", 2000, "Pocket Money"),
    ("earned 4500 from freelance", "add_income", 4500, "Freelance"),
]


@pytest.mark.parametrize("text,intent,amount,category", CASES)
def test_parse_transactions(text, intent, amount, category):
    cmd = parse(text)
    assert cmd["intent"] == intent, cmd
    assert cmd["amount"] == amount, cmd
    assert cmd["category"] == category, cmd


@pytest.mark.parametrize("text,intent", [
    ("what's my balance", "check_balance"),
    ("how much money do I have", "check_balance"),
    ("kitne paise bache hain", "check_balance"),
    ("बैलेंस कितना है", "check_balance"),
    ("how much did I spend this month", "spending_query"),
    ("how much did I spend on food this week", "spending_query"),
    ("is mahine kitna kharch kiya", "spending_query"),
    ("set food budget to 4000", "set_budget"),
    ("how am I doing on my budgets", "budget_status"),
    ("create a goal laptop for 60000", "create_goal"),
    ("add 500 to my laptop goal", "add_to_goal"),
    ("how is my laptop goal", "goal_status"),
    ("can I afford 3000 shoes", "can_i_afford"),
    ("kya main 2000 ke headphones le sakta hoon", "can_i_afford"),
    ("what's my score", "health_score"),
    ("how much will I spend by end of month", "forecast"),
    ("undo", "undo"),
    ("open goals", "navigate"),
    ("budgets", "navigate"),
    ("log out", "logout"),
    ("what can you do", "help"),
    ("why am I always broke?", "ask_coach"),
])
def test_parse_intents(text, intent):
    assert parse(text)["intent"] == intent, parse(text)


def test_hindi_words_are_not_mistaken_for_numbers():
    # "do" means "give/do", not 2, unless followed by sau/hazaar.
    assert parse("what do I spend most on?")["intent"] == "ask_coach"
    assert parse("do sau ka petrol")["amount"] == 200


def test_spending_query_details():
    cmd = parse("how much did I spend on food this week")
    assert cmd["category"] == "Food & Dining" and cmd["period"] == "this week"


def test_goal_parsing():
    assert parse("create a goal laptop for 60000")["title"] == "Laptop"
    assert parse("new goal goa trip 15k")["title"] == "Goa Trip"
    assert parse("add 500 to my laptop goal")["goal"] == "laptop"


def say(client, text):
    r = client.post("/api/voice/command", json={"text": text})
    assert r.status_code == 200, r.json
    return r.json


def test_voice_end_to_end(client, user):
    r = say(client, "got salary 30000")
    assert "30,000" in r["reply"] and r["refresh"]
    say(client, "create a goal laptop for 60000")
    r = say(client, "spent 47 on uber")
    assert "₹47" in r["reply"] and "auto-saved" in r["reply"]
    assert "balance" in say(client, "what's my balance")["reply"].lower()
    r = say(client, "add 1000 to laptop goal")
    assert "Laptop" in r["reply"]
    say(client, "set food budget to 3000")
    r = say(client, "spent 2900 on zomato")
    assert "left in that budget" in r["reply"] or "over" in r["reply"]
    r = say(client, "can I afford 500 pizza")
    assert "budget" in r["reply"].lower()
    assert "spent" in say(client, "how much did I spend this month")["reply"].lower()
    assert "score" in say(client, "what's my score")["reply"].lower()
    r = say(client, "open budgets")
    assert r["navigate"] == "/app/budgets"


def test_voice_undo(client, user):
    say(client, "got salary 1000")
    r = say(client, "spent 100 on books")
    assert client.post("/api/voice/undo", json=r["undo"]).status_code == 200
    assert client.get("/api/dashboard").json["balance"] == 1000
    say(client, "spent 50 on tea")
    say(client, "undo")
    assert client.get("/api/dashboard").json["balance"] == 1000


def test_big_amounts_need_confirmation(client, user):
    r = say(client, "got salary 90000")
    assert r["needs_confirmation"]
    assert client.get("/api/dashboard").json["balance"] == 0
    r = client.post("/api/voice/command", json={"confirmed": True, "command": r["command"]}).json
    assert client.get("/api/dashboard").json["balance"] == 90000


def test_voice_errors_are_spoken_not_crashes(client, user):
    r = say(client, "add 500 to my goal")
    assert r.get("error") and "goal" in r["reply"].lower()


def test_coach_works_offline(client, user):
    say(client, "got salary 1000")
    r = client.post("/api/coach", json={"question": "how am I doing?"}).json
    assert "1,000" in r["answer"]


def test_ai_output_is_validated():
    from flux.voice import parse_with_ai

    assert parse_with_ai("x", lambda *a, **k: {"intent": "delete_all_users"}) is None
    assert parse_with_ai("x", lambda *a, **k: {"intent": "navigate", "page": "https://evil.com"}) is None
    assert parse_with_ai("x", lambda *a, **k: {"intent": "add_expense"}) is None  # no amount
    cmd = parse_with_ai("x", lambda *a, **k: {"intent": "add_expense", "amount": 99, "category": "Hacking"})
    assert cmd["category"] == "Other" and cmd["amount"] == 99
