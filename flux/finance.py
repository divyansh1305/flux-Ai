"""Core money logic. Every number shown in the app comes from here.

Ledger rule (one source of truth):
    balance = income - expenses - savings - holdings(at cost)
Savings are money *moved* from the balance into a goal, and investments are money
moved from a goal into an ETF, so nothing is ever double-counted or created.
"""
import calendar
from datetime import timedelta

from flask import g, has_app_context

from .db import get_db
from .security import ApiError
from . import clock

from upi_parse import EXPENSE_CATEGORIES as _EXP, INCOME_CATEGORIES as _INC  # noqa: E402

EXPENSE_CATEGORIES = list(_EXP)
INCOME_CATEGORIES = list(_INC) + ["Paid back"]  # a friend returning their share (see friends.py)
SAVING_CATEGORY = "Goal Saving"


def rupees(paise):
    return round((paise or 0) / 100, 2)


def month_bounds(day=None):
    day = day or clock.today()
    first = day.replace(day=1)
    last = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return first, last


def _memo(key, compute):
    """Per-request cache for aggregate queries. The key includes the connection's
    `total_changes`, which SQLite bumps on every INSERT/UPDATE/DELETE, so any write in
    this request automatically invalidates it – a stale balance is impossible.
    (The dashboard went from 40 queries to 26 with this.)"""
    if not has_app_context():
        return compute()
    conn = get_db()
    cache = g.setdefault("_fin_memo", {})
    k = (key, conn.total_changes)
    if k not in cache:
        cache[k] = compute()
    return cache[k]


def _sum(user_id, kind, start=None, end=None, category=None, goal_id=None):
    if start is None and end is None and category is None and goal_id is None:
        return _memo(("sum", user_id, kind), lambda: _sum_q(user_id, kind))
    return _sum_q(user_id, kind, start, end, category, goal_id)


def own_sum(user_id, kind, start=None, end=None, category=None):
    """Like _sum, but only YOUR money: friends' shares of a split payment aren't your spending, and a friend
    paying you back isn't income. (The balance still uses _sum: it must match the bank.)"""
    total = _sum(user_id, kind, start, end, category)
    db = get_db()
    if kind == "expense":
        sql = ("SELECT COALESCE(SUM(o.amount),0) FROM owed o JOIN transactions t ON t.id = o.transaction_id"
               " WHERE o.user_id = ? AND o.direction = 'they_owe' AND t.kind = 'expense'")
        args = [user_id]
        if start:
            sql += " AND t.date >= ?"
            args.append(start.isoformat())
        if end:
            sql += " AND t.date <= ?"
            args.append(end.isoformat())
        if category:
            sql += " AND t.category = ?"
            args.append(category)
        total -= db.execute(sql, args).fetchone()[0]
    elif kind == "income" and category is None:
        total -= _sum(user_id, "income", start, end, category="Paid back")
    return max(0, total)


def _sum_q(user_id, kind, start=None, end=None, category=None, goal_id=None):
    sql = "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id = ? AND kind = ?"
    args = [user_id, kind]
    if start:
        sql += " AND date >= ?"
        args.append(start.isoformat())
    if end:
        sql += " AND date <= ?"
        args.append(end.isoformat())
    if category:
        sql += " AND category = ?"
        args.append(category)
    if goal_id is not None:
        sql += " AND goal_id = ?"
        args.append(goal_id)
    return get_db().execute(sql, args).fetchone()[0]


def opening_balance(user_id):
    def q():
        row = get_db().execute("SELECT opening_balance FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["opening_balance"] if row else 0
    return _memo(("opening", user_id), q)


def balance(user_id):
    """Spendable money = opening balance + income - expenses - money in goals - money invested (at cost).
    The opening balance is what was in the bank before Kitna started; it is not income, so it never
    inflates spending or savings-rate statistics."""
    return (opening_balance(user_id) + _sum(user_id, "income") - _sum(user_id, "expense") - _sum(user_id, "saving")
            - invested_cost(user_id))


def invested_cost(user_id, goal_id=None):
    if goal_id is None:
        return _memo(("invested", user_id), lambda: _invested_q(user_id))
    return _invested_q(user_id, goal_id)


def _invested_q(user_id, goal_id=None):
    sql = "SELECT COALESCE(SUM(quantity * price),0) FROM investments WHERE user_id = ? AND status = 'holding'"
    args = [user_id]
    if goal_id is not None:
        sql += " AND goal_id = ?"
        args.append(goal_id)
    return get_db().execute(sql, args).fetchone()[0]


def total_saved(user_id):
    """Money set aside in goals: cash still in goals + what was invested from them (at cost)."""
    return _sum(user_id, "saving") + invested_cost(user_id)


# ─── Auto-save ────────────────────────────────────────────────
def compute_autosave(expense_paise, mode, value):
    """How much to set aside for one expense.

    roundup: ₹47 with step ₹10 -> save ₹3 (exact multiples save nothing).
    percent: 5% of ₹400 -> save ₹20.
    """
    if mode == "roundup" and value > 0:
        step = value * 100
        remainder = expense_paise % step
        return 0 if remainder == 0 else step - remainder
    if mode == "percent" and value > 0:
        return round(expense_paise * value / 100)
    return 0


def validate_category(kind, category):
    allowed = INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
    if kind == "saving":
        return SAVING_CATEGORY
    if category not in allowed:
        raise ApiError(f"Unknown category '{category}'.")
    return category


def add_transaction(user, kind, amount, category, note="", day=None, source="manual",
                    goal_id=None, import_hash=None, autosave=True, commit=True, ref=None, origin=None,
                    auto_category=None):
    """Insert one transaction (+ its auto-save, for expenses). Returns a dict."""
    db = get_db()
    day = day or clock.today().isoformat()
    category = validate_category(kind, category)
    if kind == "saving":
        if goal_id is None:
            raise ApiError("A saving needs a goal.")
        if amount > 0 and amount > balance(user["id"]):
            raise ApiError(f"Not enough balance. Available: ₹{rupees(balance(user['id'])):,.2f}")
        if amount < 0 and -amount > _sum(user["id"], "saving", goal_id=goal_id):
            raise ApiError("You can't withdraw more than this goal holds.")

    cur = db.execute(
        "INSERT INTO transactions (user_id, kind, amount, category, note, date, goal_id, source, import_hash, ref, origin,"
        " auto_category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (user["id"], kind, amount, category, note, day, goal_id, source, import_hash, ref, origin or source,
         auto_category),
    )
    tx_id = cur.lastrowid
    result = {"id": tx_id, "autosaved": 0, "autosave_goal": None, "paid_back": None}
    if kind in ("income", "expense"):
        from . import friends

        closed = friends.match_payment(user["id"], tx_id, kind, amount, note, day)
        if closed is not None:
            result["paid_back"] = {"person": closed["person"], "amount": rupees(closed["amount"]),
                                   "direction": closed["direction"]}
            from . import reminders

            if closed["direction"] == "they_owe" and "friends" in reminders.enabled(user):
                hi = "lang" in user.keys() and user["lang"] == "hinglish"
                first, amt = closed["person"].split(" ")[0], f"₹{rupees(closed['amount']):,.0f}"
                reminders.notify_now(user["id"], {
                    "kind": "friends", "key": f"paid-back:{closed['id']}", "url": "/app/friends",
                    "title": f"{first} ne {amt} wapas kar diye" if hi else f"{first} paid you back {amt}",
                    "body": "Kitna ne list se hata diya." if hi else "Ticked off your list. Nothing to do."})

    if kind == "expense" and autosave:
        goal_id_auto = user["autosave_goal_id"]
        if goal_id_auto:
            goal = db.execute(
                "SELECT id, title FROM goals WHERE id = ? AND user_id = ? AND archived = 0",
                (goal_id_auto, user["id"]),
            ).fetchone()
            save = compute_autosave(amount, user["autosave_mode"], user["autosave_value"])
            # Never auto-save money the user doesn't have.
            if goal and save > 0 and balance(user["id"]) >= save:
                db.execute(
                    "INSERT INTO transactions (user_id, kind, amount, category, note, date, goal_id, parent_id, source)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (user["id"], "saving", save, SAVING_CATEGORY, f"Auto-save from {category}",
                     day, goal["id"], tx_id, "autosave"),
                )
                result.update(autosaved=save, autosave_goal=goal["title"])
    if commit:
        db.commit()
    return result


# ─── Summaries ────────────────────────────────────────────────
def month_summary(user_id, day=None):
    first, last = month_bounds(day)
    inc = own_sum(user_id, "income", first, last)
    exp = own_sum(user_id, "expense", first, last)
    sav = _sum(user_id, "saving", first, last)
    rows = get_db().execute(
        "SELECT category, total FROM (SELECT t.category, SUM(t.amount - COALESCE((SELECT SUM(o.amount) FROM owed o"
        " WHERE o.transaction_id = t.id AND o.direction = 'they_owe'), 0)) AS total FROM transactions t"
        " WHERE t.user_id = ? AND t.kind = 'expense' AND t.date BETWEEN ? AND ? GROUP BY t.category)"
        " WHERE total > 0 ORDER BY total DESC",
        (user_id, first.isoformat(), last.isoformat()),
    ).fetchall()
    return {
        "month": first.strftime("%B %Y"),
        "income": rupees(inc),
        "expenses": rupees(exp),
        "saved": rupees(sav),
        "savings_rate": round((inc - exp) / inc * 100, 1) if inc > 0 else None,
        "by_category": [{"category": r["category"], "amount": rupees(r["total"])} for r in rows],
    }


def daily_series(user_id, days=30):
    """Expense and income per day for the last N days (for charts)."""
    start = clock.today() - timedelta(days=days - 1)
    rows = get_db().execute(
        "SELECT date, kind, SUM(amount) AS t FROM transactions WHERE user_id = ? AND date >= ?"
        " AND kind IN ('income','expense') GROUP BY date, kind",
        (user_id, start.isoformat()),
    ).fetchall()
    data = {}
    for r in rows:
        data.setdefault(r["date"], {})[r["kind"]] = r["t"]
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        series.append({
            "date": d,
            "expense": rupees(data.get(d, {}).get("expense", 0)),
            "income": rupees(data.get(d, {}).get("income", 0)),
        })
    return series


# ─── Goals ────────────────────────────────────────────────────
def goals_with_progress(user_id, include_archived=False):
    sql = (
        "SELECT g.*, COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.goal_id = g.id AND t.kind='saving'),0) AS cash,"
        " COALESCE((SELECT SUM(quantity * price) FROM investments i WHERE i.goal_id = g.id AND i.status='holding'),0) AS invested"
        " FROM goals g WHERE g.user_id = ?"
    )
    if not include_archived:
        sql += " AND g.archived = 0"
    sql += " ORDER BY g.created_at"
    out = []
    for g in get_db().execute(sql, (user_id,)).fetchall():
        saved = g["cash"] + g["invested"]
        out.append({
            "cash": rupees(g["cash"]),
            "invested": rupees(g["invested"]),
            "id": g["id"],
            "title": g["title"],
            "target": rupees(g["target"]),
            "saved": rupees(saved),
            "remaining": rupees(max(0, g["target"] - saved)),
            "percent": min(100, round(saved / g["target"] * 100, 1)),
            "deadline": g["deadline"],
            "complete": saved >= g["target"],
        })
    return out


def avg_daily_saving(user_id, days=30):
    start = clock.today() - timedelta(days=days - 1)
    return _sum(user_id, "saving", start) / days


# ─── Budgets ──────────────────────────────────────────────────
def budget_status(user_id, day=None):
    day = day or clock.today()
    first, last = month_bounds(day)
    elapsed = (day - first).days + 1
    total_days = (last - first).days + 1
    rows = get_db().execute(
        "SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category", (user_id,)
    ).fetchall()
    out = []
    for r in rows:
        spent = own_sum(user_id, "expense", first, last, category=r["category"])
        limit = r["monthly_limit"]
        expected_by_now = limit * elapsed / total_days
        if spent > limit:
            state = "over"
        # Early in the month one purchase can look "fast", so only judge pace after day 5
        # (or once half the budget is gone).
        elif spent > expected_by_now * 1.1 and (elapsed >= 5 or spent > limit * 0.5):
            state = "ahead"  # spending faster than the month allows
        else:
            state = "ok"
        out.append({
            "category": r["category"],
            "limit": rupees(limit),
            "spent": rupees(spent),
            "left": rupees(limit - spent),
            "percent": round(spent / limit * 100, 1),
            "state": state,
        })
    return out


# ─── Pre-spend check ──────────────────────────────────────────
def pre_spend_check(user, amount, category):
    uid = user["id"]
    first, last = month_bounds()
    bal = balance(uid)
    warnings = []
    budget = get_db().execute(
        "SELECT monthly_limit FROM budgets WHERE user_id = ? AND category = ?", (uid, category)
    ).fetchone()
    budget_info = None
    if budget:
        spent = own_sum(uid, "expense", first, last, category=category)
        after = spent + amount
        limit = budget["monthly_limit"]
        budget_info = {"limit": rupees(limit), "spent": rupees(spent), "after": rupees(after),
                       "percent_after": round(after / limit * 100, 1)}
        if after > limit:
            warnings.append(f"This puts {category} ₹{rupees(after - limit):,.0f} over your monthly budget.")
        elif after > limit * 0.8:
            warnings.append(f"After this you'll have used {after / limit * 100:.0f}% of your {category} budget.")
    if amount > bal:
        warnings.append(f"This is more than your current balance (₹{rupees(bal):,.0f}).")

    daily = avg_daily_saving(uid)
    goal_delay_days = round(amount / daily) if daily > 0 else None
    level = "ok"
    if any("over" in w or "more than your current balance" in w for w in warnings):
        level = "stop"
    elif warnings:
        level = "caution"
    return {
        "level": level,
        "warnings": warnings,
        "balance_after": rupees(bal - amount),
        "budget": budget_info,
        "goal_delay_days": goal_delay_days,
        "autosave_would_add": rupees(compute_autosave(amount, user["autosave_mode"], user["autosave_value"])),
    }


# ─── Forecast ─────────────────────────────────────────────────
def month_forecast(user_id, day=None):
    day = day or clock.today()
    first, last = month_bounds(day)
    elapsed = (day - first).days + 1
    remaining = (last - day).days
    spent = own_sum(user_id, "expense", first, day)
    income = own_sum(user_id, "income", first, last)
    prev_last = first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    last_month = own_sum(user_id, "expense", prev_first, prev_last)

    WARMUP = 7
    daily = spent / elapsed if elapsed else 0
    method = "Projection = spent so far + (daily average so far × days left)."
    if elapsed < WARMUP and last_month:
        # In the first week, one big day would distort the projection, so blend in last month's pace.
        prev_daily = last_month / prev_last.day
        daily = (spent + prev_daily * (WARMUP - elapsed)) / WARMUP
        method = "Early in the month, so the projection blends this month's spending with last month's daily pace."
    projected = spent + daily * remaining

    alerts = []
    for b in (budget_status(user_id, day) if elapsed >= 5 else []):
        limit_paise = round(b["limit"] * 100)
        spent_cat = round(b["spent"] * 100)
        proj_cat = spent_cat / elapsed * (elapsed + remaining) if elapsed else spent_cat
        if proj_cat > limit_paise:
            alerts.append(f"At this pace {b['category']} will end the month around ₹{rupees(proj_cat):,.0f} "
                          f"(budget ₹{b['limit']:,.0f}).")
    return {
        "spent_so_far": rupees(spent),
        "daily_average": rupees(daily),
        "projected_month_total": rupees(projected),
        "last_month_total": rupees(last_month),
        "income_this_month": rupees(income),
        "projected_left_over": rupees(income - projected) if income else None,
        "days_left": remaining,
        "alerts": alerts,
        "method": method,
    }


# ─── Money Health Score ───────────────────────────────────────
MIN_DAYS_FOR_SCORE = 5


def health_score(user_id):
    """0–100 score from four documented parts. Not a credit score."""
    today = clock.today()
    start30 = today - timedelta(days=29)
    inc30 = _sum(user_id, "income", start30)
    exp30 = _sum(user_id, "expense", start30)
    tips = []

    if inc30 == 0 and exp30 == 0:
        return {"score": None, "parts": [], "days_tracked": 0,
                "tips": ["Add your income and a few expenses to get your score."]}
    # A score from one day of data would be made up, so wait for about a week of real activity.
    days_tracked = get_db().execute(
        "SELECT COUNT(DISTINCT date) FROM transactions WHERE user_id = ? AND date >= ? AND kind IN ('income','expense')",
        (user_id, start30.isoformat())).fetchone()[0]
    if days_tracked < MIN_DAYS_FOR_SCORE:
        return {"score": None, "parts": [], "days_tracked": days_tracked,
                "tips": [f"Your score appears after about a week of tracking ({days_tracked} of {MIN_DAYS_FOR_SCORE} days so far)."]}

    # 1. Savings rate (40): saving 20%+ of income earns full marks.
    rate = (inc30 - exp30) / inc30 if inc30 > 0 else -1
    p_rate = round(max(0.0, min(1.0, rate / 0.20)) * 40)
    if rate < 0.20:
        tips.append("Aim to keep at least 20% of what you earn. Right now you keep "
                    f"{max(rate, 0) * 100:.0f}%.")

    # 2. Budget adherence (25)
    budgets = budget_status(user_id)
    if budgets:
        good = sum(1 for b in budgets if b["state"] == "ok")
        p_budget = round(good / len(budgets) * 25)
        off = [b["category"] for b in budgets if b["state"] != "ok"]
        if off:
            tips.append("Spending is running ahead of budget in: " + ", ".join(off) + ".")
    else:
        p_budget = 0  # no budgets means no points (it used to give 10 for free)
        tips.append("Set a budget for your top 2–3 categories to earn these points.")

    # 3. Tracking consistency (15): logging on 10 of the last 14 days = full marks.
    days_logged = get_db().execute(
        "SELECT COUNT(DISTINCT date) FROM transactions WHERE user_id = ? AND date >= ? AND kind != 'saving'",
        (user_id, (today - timedelta(days=13)).isoformat()),
    ).fetchone()[0]
    p_consistency = round(min(1.0, days_logged / 10) * 15)

    # 4. Safety buffer (20): balance + goal savings covering 3 months of expenses = full marks.
    monthly_exp = exp30 or 1
    cushion = max(0, balance(user_id)) + total_saved(user_id)
    months = cushion / monthly_exp
    p_buffer = round(min(1.0, months / 3) * 20)
    if months < 1:
        tips.append("Build a safety buffer worth one month of expenses first.")

    parts = [
        {"name": "Savings rate", "points": p_rate, "max": 40, "detail": f"{max(rate, 0) * 100:.0f}% of income kept (last 30 days)"},
        {"name": "Budgets", "points": p_budget, "max": 25, "detail": f"{len(budgets)} budget{'' if len(budgets) == 1 else 's'} set" if budgets else "No budgets yet"},
        {"name": "Tracking habit", "points": p_consistency, "max": 15, "detail": f"Logged on {days_logged} of the last 14 days"},
        {"name": "Safety buffer", "points": p_buffer, "max": 20, "detail": ("No spending logged yet" if not exp30 else
                                                                         f"Covers {months:.1f} months of expenses" if months < 99
                                                                         else "Covers more than 8 years of expenses")},
    ]
    return {"score": sum(p["points"] for p in parts), "parts": parts, "tips": tips[:3], "days_tracked": days_tracked}


def snapshot_for_ai(user):
    """Aggregated numbers only (no email, no raw notes) for the AI coach."""
    uid = user["id"]
    return {
        "first_name": user["name"].split()[0],
        "balance": rupees(balance(uid)),
        "this_month": month_summary(uid),
        "budgets": budget_status(uid),
        "goals": goals_with_progress(uid),
        "forecast": month_forecast(uid),
        "health": health_score(uid),
    }


# ─── Learning from corrections ────────────────────────────────
def merchant_key(note):
    """'Zomato · UPI' / 'ZOMATO LTD' / 'zomato' → 'zomato'. Used to remember a user's category choice."""
    import re

    text = (note or "").split("·")[0].lower()
    text = re.sub(r"\b(pvt|private|ltd|limited|llp|india|upi|payment|paid|to)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()[:60]


def rule_category(user_id, note, kind):
    """The category this user told Kitna to always use for this merchant, if any (and valid for `kind`)."""
    key = merchant_key(note)
    if not key:
        return None
    row = get_db().execute("SELECT category FROM merchant_rules WHERE user_id = ? AND merchant_key = ?",
                           (user_id, key)).fetchone()
    if row and row["category"] in (EXPENSE_CATEGORIES if kind == "expense" else INCOME_CATEGORIES):
        return row["category"]
    return None


def categorisation_accuracy(user_id):
    """How often the automatic category was kept, measured from this user's own corrections."""
    row = get_db().execute(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN category != auto_category THEN 1 ELSE 0 END) AS fixed"
        " FROM transactions WHERE user_id = ? AND auto_category IS NOT NULL", (user_id,)).fetchone()
    n, fixed = row["n"] or 0, row["fixed"] or 0
    return {"auto_logged": n, "corrected": fixed, "accuracy": round(100 * (n - fixed) / n, 1) if n else None}
