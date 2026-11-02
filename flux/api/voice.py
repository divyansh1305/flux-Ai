"""Voice assistant + AI coach endpoints."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify

from .. import ai, finance, voice
from ..db import get_db
from ..finance import rupees
from ..security import ApiError, clean_text, current_user, json_body, login_required, parse_amount, rate_limit
from .money import contribute, create_goal_from, create_tx_from

bp = Blueprint("voice", __name__, url_prefix="/api")

CONFIRM_ABOVE = 50_000  # rupees; bigger voice entries need a spoken "yes"
HELP_TEXT = ("You can say things like: 'spent 250 on Swiggy', 'got salary 30000', 'what's my balance', "
             "'how much did I spend on food this month', 'set food budget to 4000', 'add 500 to my laptop goal', "
             "'can I afford 3000 shoes', 'open goals', or 'undo'. Hindi works too: 'maine 200 chai pe kharch kiye'.")


def inr(v):
    v = float(v)
    return f"₹{v:,.0f}" if v == int(v) else f"₹{v:,.2f}"


def _match_goal(uid, name):
    goals = finance.goals_with_progress(uid)
    if not goals:
        return None, goals
    if len(goals) == 1 or not name:
        return (goals[0] if len(goals) == 1 else None), goals
    words = set(name.lower().split())
    best, best_score = None, 0
    for g in goals:
        gw = set(g["title"].lower().split())
        score = len(words & gw) + (2 if name.lower() in g["title"].lower() else 0)
        if score > best_score:
            best, best_score = g, score
    return best, goals


def execute(cmd):
    u = current_user()
    uid = u["id"]
    intent = cmd.get("intent")
    out = {"intent": intent, "refresh": False}

    if intent in ("add_expense", "add_income"):
        kind = "expense" if intent == "add_expense" else "income"
        res = create_tx_from({"kind": kind, "amount": cmd["amount"], "category": cmd.get("category"),
                              "note": cmd.get("note", ""), "date": cmd.get("date")}, source="voice")
        tx = res["transaction"]
        if kind == "expense":
            reply = f"Added {inr(tx['amount'])} for {tx['category']}."
            if res["autosaved"]:
                reply += f" {inr(res['autosaved'])} auto-saved to {res['autosave_goal']}."
            budget = next((b for b in finance.budget_status(uid) if b["category"] == tx["category"]), None)
            if budget and budget["state"] == "over":
                reply += f" Heads up, you're {inr(-budget['left'])} over your {tx['category']} budget."
            elif budget and budget["percent"] >= 80:
                reply += f" {inr(budget['left'])} left in that budget."
        else:
            reply = f"Added {inr(tx['amount'])} income as {tx['category']}."
        reply += f" Balance is now {inr(res['balance'])}."
        out.update(reply=reply, refresh=True, undo={"type": "transaction", "id": tx["id"]})

    elif intent == "check_balance":
        bal = finance.balance(uid)
        saved = finance.total_saved(uid)
        out["reply"] = f"Your balance is {inr(rupees(bal))}" + (f", plus {inr(rupees(saved))} saved in goals." if saved else ".")

    elif intent == "spending_query":
        args = [uid, cmd["from"], cmd["to"]]
        sql = "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND kind='expense' AND date BETWEEN ? AND ?"
        if cmd.get("category"):
            sql += " AND category = ?"
            args.append(cmd["category"])
        total = get_db().execute(sql, args).fetchone()[0]
        what = f" on {cmd['category']}" if cmd.get("category") else ""
        reply = f"You spent {inr(rupees(total))}{what} {cmd['period']}."
        if not cmd.get("category") and total:
            top = get_db().execute(
                "SELECT category, SUM(amount) t FROM transactions WHERE user_id=? AND kind='expense' AND date BETWEEN ? AND ?"
                " GROUP BY category ORDER BY t DESC LIMIT 1", args[:3]).fetchone()
            reply += f" Most of it went to {top['category']} ({inr(rupees(top['t']))})."
        out["reply"] = reply

    elif intent == "budget_status":
        budgets = finance.budget_status(uid)
        if cmd.get("category"):
            b = next((x for x in budgets if x["category"] == cmd["category"]), None)
            out["reply"] = (f"You've used {b['percent']:.0f}% of your {b['category']} budget. {inr(max(b['left'], 0))} left."
                            if b else f"You don't have a {cmd['category']} budget yet. Say 'set {cmd['category']} budget to 3000'.")
        elif not budgets:
            out["reply"] = "You haven't set any budgets yet. Try 'set food budget to 4000'."
        else:
            over = [b["category"] for b in budgets if b["state"] == "over"]
            ahead = [b["category"] for b in budgets if b["state"] == "ahead"]
            parts = [f"You have {len(budgets)} budgets."]
            if over:
                parts.append("Over budget: " + ", ".join(over) + ".")
            if ahead:
                parts.append("Spending too fast: " + ", ".join(ahead) + ".")
            if not over and not ahead:
                parts.append("All of them are on track. Nice!")
            out["reply"] = " ".join(parts)
        out["navigate"] = "/app/budgets"

    elif intent == "set_budget":
        cat = cmd.get("category") or "Other"
        if cat not in finance.EXPENSE_CATEGORIES:
            raise ApiError("I didn't catch which category that budget is for.")
        limit = parse_amount(cmd["amount"])
        get_db().execute("INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?,?,?) ON CONFLICT(user_id, category)"
                         " DO UPDATE SET monthly_limit = excluded.monthly_limit", (uid, cat, limit))
        get_db().commit()
        out.update(reply=f"Done. Your monthly {cat} budget is {inr(rupees(limit))}.", refresh=True)

    elif intent == "goal_status":
        goal, goals = _match_goal(uid, cmd.get("goal"))
        if not goals:
            out["reply"] = "You don't have any goals yet. Try 'create a goal laptop for 60000'."
        elif goal:
            out["reply"] = (f"{goal['title']}: {inr(goal['saved'])} of {inr(goal['target'])} saved, that's {goal['percent']:.0f}%."
                            + (" Goal complete!" if goal["complete"] else f" {inr(goal['remaining'])} to go."))
        else:
            out["reply"] = "Your goals: " + "; ".join(f"{g['title']} {g['percent']:.0f}%" for g in goals[:5]) + "."
        out["navigate"] = "/app/goals"

    elif intent == "create_goal":
        g = create_goal_from({"title": cmd.get("title") or "New Goal", "target": cmd["amount"]})
        out.update(reply=f"Created your goal '{g['title']}' for {inr(g['target'])}.", refresh=True,
                   undo={"type": "goal", "id": g["id"]})

    elif intent == "add_to_goal":
        goal, goals = _match_goal(uid, cmd.get("goal"))
        if not goals:
            raise ApiError("You don't have a goal yet. Say 'create a goal' first.")
        if goal is None:
            raise ApiError("Which goal? You have: " + ", ".join(g["title"] for g in goals[:5]) + ".")
        updated = contribute(goal["id"], parse_amount(cmd["amount"]), source="voice")
        last = get_db().execute("SELECT id FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        out.update(reply=f"Moved {inr(cmd['amount'])} to {updated['title']}. It's now {updated['percent']:.0f}% done.",
                   refresh=True, undo={"type": "transaction", "id": last["id"]})

    elif intent == "can_i_afford":
        amount = parse_amount(cmd["amount"])
        cat = cmd.get("category") or "Other"
        if cat not in finance.EXPENSE_CATEGORIES:
            cat = "Other"
        chk = finance.pre_spend_check(u, amount, cat)
        if chk["level"] == "ok":
            reply = f"Yes, {inr(cmd['amount'])} fits. You'd have {inr(chk['balance_after'])} left."
        elif chk["level"] == "caution":
            reply = "You can, but careful. " + " ".join(chk["warnings"])
        else:
            reply = "I'd skip it for now. " + " ".join(chk["warnings"])
        if chk["goal_delay_days"]:
            reply += f" It would push your goals back about {chk['goal_delay_days']} days."
        out.update(reply=reply, data=chk)

    elif intent == "safe_to_spend":
        from .. import insights

        sd = insights.safe_to_spend(uid)
        out["reply"] = (f"You can safely spend {inr(sd['left_today'])} more today. " if sd["status"] == "ok" else "") + \
            (sd["message"] if sd["status"] != "ok" else
             (f"That keeps {inr(sd['bills_due'])} aside for bills due this month." if sd["bills_due"] else ""))

    elif intent == "bills":
        from .. import insights

        bills = insights.recurring(uid)
        if not bills:
            out["reply"] = "I haven't spotted any regular bills or subscriptions yet. I need to see a payment repeat at least twice."
        else:
            total = sum(b["monthly_cost"] for b in bills)
            nxt = bills[0]
            out["reply"] = (f"You have {len(bills)} regular payments costing about {inr(total)} a month. "
                            f"Next: {nxt['name']} for {inr(nxt['amount'])} around {nxt['next_date']}.")
        out["navigate"] = "/app/coach"

    elif intent == "health_score":
        h = finance.health_score(uid)
        if h["score"] is None:
            out["reply"] = h["tips"][0]
        else:
            weakest = min(h["parts"], key=lambda p: p["points"] / p["max"])
            out["reply"] = f"Your Money Health Score is {h['score']} out of 100. Your weakest area is {weakest['name'].lower()}."
            if h["tips"]:
                out["reply"] += " " + h["tips"][0]
        out["navigate"] = "/app/coach"

    elif intent == "forecast":
        f = finance.month_forecast(uid)
        reply = f"At your current pace you'll spend about {inr(f['projected_month_total'])} this month."
        if f["last_month_total"]:
            diff = f["projected_month_total"] - f["last_month_total"]
            reply += f" That's {inr(abs(diff))} {'more' if diff > 0 else 'less'} than last month."
        if f["alerts"]:
            reply += " " + f["alerts"][0]
        out["reply"] = reply

    elif intent == "undo":
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        row = get_db().execute(
            "SELECT * FROM transactions WHERE user_id=? AND source IN ('voice','manual') AND created_at >= ?"
            " ORDER BY id DESC LIMIT 1", (uid, cutoff)).fetchone()
        if row is None:
            out["reply"] = "There's nothing recent to undo."
        else:
            get_db().execute("DELETE FROM transactions WHERE id=? AND user_id=?", (row["id"], uid))
            get_db().commit()
            out.update(reply=f"Removed the {inr(rupees(abs(row['amount'])))} {row['category']} entry.", refresh=True)

    elif intent == "pay":
        from urllib.parse import urlencode

        vpa = cmd.get("vpa")
        name = cmd.get("payee") or ""
        if not vpa and name:
            rows = get_db().execute("SELECT vpa, name FROM payees WHERE user_id=? ORDER BY times_paid DESC", (uid,)).fetchall()
            words = set(name.lower().split())
            best = max(rows, key=lambda r: len(words & set((r["name"] + " " + r["vpa"].split("@")[0]).lower().split())), default=None)
            if best and words & set((best["name"] + " " + best["vpa"].split("@")[0]).lower().split()):
                vpa, name = best["vpa"], best["name"]
        q = {"amount": f"{float(cmd['amount']):.2f}"}
        if vpa:
            q.update(vpa=vpa, name=name)
            reply = f"Opening payment of {inr(cmd['amount'])} to {name or vpa}. I'll check your budget first."
        else:
            reply = f"Okay, {inr(cmd['amount'])}. Scan their QR code or enter their UPI ID."
        out.update(reply=reply, navigate="/app/pay?" + urlencode(q))

    elif intent == "navigate":
        out.update(reply=f"Opening {cmd.get('page_name', 'that')}.", navigate=cmd["page"])

    elif intent == "logout":
        out.update(reply="Signing you out.", logout=True)

    elif intent == "help":
        out["reply"] = HELP_TEXT

    elif intent == "ask_coach":
        out["reply"] = coach_answer(cmd.get("question", ""))

    else:
        out["reply"] = "Sorry, I didn't get that. Say 'help' to hear what I can do."
    return out


def coach_answer(question):
    u = current_user()
    snap = finance.snapshot_for_ai(u)
    answer = ai.coach_reply(question, snap)
    if answer:
        return answer
    # Offline fallback: still useful, built from real numbers.
    m = snap["this_month"]
    parts = [f"This month you've earned {inr(m['income'])} and spent {inr(m['expenses'])}."]
    if m["by_category"]:
        top = m["by_category"][0]
        parts.append(f"Your biggest category is {top['category']} at {inr(top['amount'])}.")
    if snap["health"]["tips"]:
        parts.append(snap["health"]["tips"][0])
    parts.append("(AI coach is offline, so this is a quick summary.)")
    return " ".join(parts)


VALID_CONFIRMED = {"add_expense", "add_income", "set_budget", "create_goal", "add_to_goal"}
MONEY_MOVES = {"add_expense", "add_income", "add_to_goal"}


@bp.post("/voice/command")
@login_required
@rate_limit(60, 60, scope="voice")
def voice_command():
    data = json_body()
    if data.get("confirmed") and isinstance(data.get("command"), dict):
        # Re-run a command the user confirmed by voice. Re-parse it from text so nothing
        # client-side can inject arbitrary fields.
        text = clean_text(data["command"].get("text"), "Command", 300, required=True)
        cmd = voice.parse(text)
        if cmd.get("intent") == "unknown" and ai.available():
            cmd = voice.parse_with_ai(text, ai.generate) or cmd
        if cmd.get("intent") not in VALID_CONFIRMED:
            raise ApiError("Nothing to confirm.")
        result = execute(cmd)
        result["heard"] = text
        return jsonify(result)

    text = clean_text(data.get("text"), "Command", 300, required=True)
    cmd = voice.parse(text)
    used_ai = False
    if cmd["intent"] == "unknown" and ai.available():
        ai_cmd = voice.parse_with_ai(text, ai.generate)
        if ai_cmd:
            cmd, used_ai = ai_cmd, True

    if cmd["intent"] in MONEY_MOVES and cmd.get("amount", 0) > CONFIRM_ABOVE:
        what = {"add_expense": "an expense", "add_income": "income", "set_budget": "a budget",
                "create_goal": "a goal", "add_to_goal": "a goal transfer"}[cmd["intent"]]
        return jsonify({"intent": cmd["intent"], "heard": text, "needs_confirmation": True,
                        "command": {"text": text},
                        "reply": f"Just checking: add {what} of {inr(cmd['amount'])}? Say yes or no."})
    try:
        result = execute(cmd)
    except ApiError as e:
        return jsonify({"intent": cmd["intent"], "heard": text, "reply": e.message, "error": True})
    result.update(heard=text, understood_by="ai" if used_ai else "rules", command=cmd)
    return jsonify(result)


@bp.post("/voice/undo")
@login_required
def voice_undo():
    data = json_body()
    uid = current_user()["id"]
    kind, obj_id = data.get("type"), data.get("id")
    if not isinstance(obj_id, int):
        raise ApiError("Bad undo request.")
    db = get_db()
    if kind == "transaction":
        cur = db.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (obj_id, uid))
    elif kind == "goal":
        db.execute("DELETE FROM transactions WHERE goal_id=? AND user_id=? AND kind='saving'", (obj_id, uid))
        cur = db.execute("DELETE FROM goals WHERE id=? AND user_id=?", (obj_id, uid))
    else:
        raise ApiError("Bad undo request.")
    db.commit()
    if cur.rowcount == 0:
        raise ApiError("Already undone.", 404)
    return jsonify({"ok": True, "reply": "Undone."})


@bp.post("/coach")
@login_required
@rate_limit(20, 60, scope="coach")
def coach():
    q = clean_text(json_body().get("question"), "Question", 500, required=True)
    return jsonify({"answer": coach_answer(q), "ai": ai.available()})
