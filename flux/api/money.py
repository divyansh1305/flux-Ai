"""Transactions, budgets, goals, dashboard numbers and exports."""
import csv
import io
import json
from datetime import timedelta

from flask import Blueprint, Response, jsonify, request, send_file

from .. import clock, finance
from ..db import get_db
from ..finance import rupees
from ..security import (ApiError, clean_text, current_user, json_body, login_required, owned_or_404,
                        parse_amount, parse_date, rate_limit)

bp = Blueprint("money", __name__, url_prefix="/api")


def tx_json(r):
    return {
        "id": r["id"], "kind": r["kind"], "amount": rupees(r["amount"]), "category": r["category"],
        "note": r["note"], "date": r["date"], "goal_id": r["goal_id"], "source": r["source"],
        "parent_id": r["parent_id"],
        "auto_category": r["auto_category"] if "auto_category" in r.keys() else None,
    }


@bp.get("/meta")
def meta():
    return jsonify({"expense_categories": finance.EXPENSE_CATEGORIES,
                    "income_categories": finance.INCOME_CATEGORIES})


# ─── Transactions ─────────────────────────────────────────────
def _filtered_rows(uid, args, limit=None, offset=0):
    sql = "SELECT * FROM transactions WHERE user_id = ?"
    params = [uid]
    kind = args.get("kind")
    if kind in ("income", "expense", "saving"):
        sql += " AND kind = ?"
        params.append(kind)
    if args.get("category"):
        sql += " AND category = ?"
        params.append(args["category"][:40])
    if args.get("from"):
        sql += " AND date >= ?"
        params.append(parse_date(args["from"], "from"))
    if args.get("to"):
        sql += " AND date <= ?"
        params.append(parse_date(args["to"], "to"))
    if args.get("q"):
        sql += " AND (note LIKE ? OR category LIKE ?)"
        q = "%" + args["q"][:60].replace("%", "").replace("_", "") + "%"
        params += [q, q]
    sql += " ORDER BY date DESC, id DESC"
    if limit:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    return get_db().execute(sql, params).fetchall()


@bp.get("/transactions")
@login_required
def list_transactions():
    uid = current_user()["id"]
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(100, max(1, int(request.args.get("size", 25))))
    except ValueError:
        raise ApiError("Bad page number.")
    rows = _filtered_rows(uid, request.args, limit=size + 1, offset=(page - 1) * size)
    return jsonify({"items": [tx_json(r) for r in rows[:size]], "page": page, "has_more": len(rows) > size})


def create_tx_from(data, source="manual"):
    u = current_user()
    kind = data.get("kind")
    if kind not in ("income", "expense"):
        raise ApiError("kind must be 'income' or 'expense'.")
    amount = parse_amount(data.get("amount"))
    category = clean_text(data.get("category") or ("Other" if kind == "expense" else "Other Income"),
                          "Category", 40)
    note = clean_text(data.get("note"), "Note", 140)
    day = parse_date(data.get("date"))
    result = finance.add_transaction(u, kind, amount, category, note, day, source=source,
                                     auto_category=category if source == "voice" else None)
    row = get_db().execute("SELECT * FROM transactions WHERE id = ?", (result["id"],)).fetchone()
    return {"transaction": tx_json(row), "autosaved": rupees(result["autosaved"]),
            "autosave_goal": result["autosave_goal"], "balance": rupees(finance.balance(u["id"]))}


@bp.post("/transactions")
@login_required
@rate_limit(120, 60, scope="tx_create")
def create_transaction():
    return jsonify(create_tx_from(json_body())), 201


@bp.delete("/transactions/<int:tx_id>")
@login_required
def delete_transaction(tx_id):
    uid = current_user()["id"]
    owned_or_404("transactions", tx_id, uid)
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, uid))  # auto-save child cascades
    db.commit()
    return jsonify({"ok": True, "balance": rupees(finance.balance(uid))})


@bp.patch("/transactions/<int:tx_id>")
@login_required
@rate_limit(120, 60, scope="tx_edit")
def edit_transaction(tx_id):
    """Fix a category or note. With remember=true, Flux uses this category for the merchant from now on
    and re-files earlier automatic entries for it that the user hasn't touched."""
    u = current_user()
    db = get_db()
    row = owned_or_404("transactions", tx_id, u["id"])
    if row["kind"] not in ("income", "expense"):
        raise ApiError("Only income and expenses can be edited. Savings are managed from Goals.")
    data = json_body()
    fields = {}
    if "category" in data:
        fields["category"] = finance.validate_category(row["kind"], clean_text(data["category"], "Category", 40, required=True))
    if "note" in data:
        fields["note"] = clean_text(data["note"], "Note", 140)
    if not fields:
        raise ApiError("Nothing to change.")
    cols = ", ".join(f"{k} = ?" for k in fields)  # keys whitelisted above
    db.execute(f"UPDATE transactions SET {cols} WHERE id = ? AND user_id = ?", (*fields.values(), tx_id, u["id"]))
    refiled = 0
    note = fields.get("note", row["note"])
    if data.get("remember") is True and "category" in fields:
        key = finance.merchant_key(note)
        if not key:
            raise ApiError("Add a merchant name in the note so Flux knows what to remember.")
        db.execute("INSERT INTO merchant_rules (user_id, merchant_key, category) VALUES (?,?,?)"
                   " ON CONFLICT(user_id, merchant_key) DO UPDATE SET category = excluded.category",
                   (u["id"], key, fields["category"]))
        # Re-file earlier *automatic* entries for this merchant that still carry the automatic category.
        for r in db.execute("SELECT id, note FROM transactions WHERE user_id = ? AND kind = ? AND id != ?"
                            " AND auto_category IS NOT NULL AND category = auto_category AND category != ?",
                            (u["id"], row["kind"], tx_id, fields["category"])).fetchall():
            if finance.merchant_key(r["note"]) == key:
                db.execute("UPDATE transactions SET category = ? WHERE id = ?", (fields["category"], r["id"]))
                refiled += 1
    db.commit()
    fresh = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    return jsonify({"transaction": tx_json(fresh), "refiled": refiled})


@bp.get("/rules")
@login_required
def list_rules():
    rows = get_db().execute("SELECT id, merchant_key, category, created_at FROM merchant_rules WHERE user_id = ?"
                            " ORDER BY merchant_key", (current_user()["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.delete("/rules/<int:rule_id>")
@login_required
def delete_rule(rule_id):
    uid = current_user()["id"]
    owned_or_404("merchant_rules", rule_id, uid)
    get_db().execute("DELETE FROM merchant_rules WHERE id = ? AND user_id = ?", (rule_id, uid))
    get_db().commit()
    return jsonify({"ok": True})


@bp.get("/samples/export")
@login_required
def export_samples():
    """Opt-in: masked messages + the category the user kept, as JSONL test cases for upi-parse.
    The file is downloaded by the user; nothing is sent anywhere by Flux."""
    rows = get_db().execute(
        "SELECT s.source, s.masked_text, t.kind, t.amount, t.category, t.auto_category, t.date FROM parse_samples s"
        " JOIN transactions t ON t.id = s.transaction_id WHERE s.user_id = ? ORDER BY s.id", (current_user()["id"],)).fetchall()
    lines = [json.dumps({"text": r["masked_text"], "source": r["source"],
                         "expected": {"direction": "debit" if r["kind"] == "expense" else "credit",
                                      "amount": f"{r['amount'] / 100:.2f}", "category": r["category"]},
                         "flux_predicted_category": r["auto_category"]}, ensure_ascii=False) for r in rows]
    resp = Response("\n".join(lines) + ("\n" if lines else ""), mimetype="application/x-ndjson")
    resp.headers["Content-Disposition"] = "attachment; filename=flux-parser-samples.jsonl"
    return resp


@bp.post("/transactions/check")
@login_required
def check_spend():
    data = json_body()
    amount = parse_amount(data.get("amount"))
    category = clean_text(data.get("category") or "Other", "Category", 40)
    return jsonify(finance.pre_spend_check(current_user(), amount, category))


@bp.get("/transactions/export")
@login_required
@rate_limit(20, 60, scope="export")
def export_transactions():
    u = current_user()
    rows = _filtered_rows(u["id"], request.args)
    fmt = request.args.get("format", "csv")
    if fmt == "pdf":
        from ..reports import transactions_pdf

        buf = transactions_pdf(u, [tx_json(r) for r in rows])
        return send_file(buf, as_attachment=True, download_name="flux-transactions.pdf", mimetype="application/pdf")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Type", "Category", "Amount (INR)", "Note", "Source"])
    for r in rows:
        note = r["note"]
        if note[:1] in ("=", "+", "-", "@"):  # block spreadsheet formula injection
            note = "'" + note
        w.writerow([r["date"], r["kind"], r["category"], f"{r['amount'] / 100:.2f}", note, r["source"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=flux-transactions.csv"})


# ─── Dashboard ────────────────────────────────────────────────
def setup_status(uid):
    """New-user checklist: earn trust step by step instead of showing scores built on nothing."""
    from .. import ledger

    db = get_db()
    one = lambda sql: db.execute(sql, (uid,)).fetchone() is not None  # noqa: E731
    has_income = one("SELECT 1 FROM transactions WHERE user_id = ? AND kind = 'income' LIMIT 1")
    has_auto = one("SELECT 1 FROM ingest_tokens WHERE user_id = ?")
    has_budget = one("SELECT 1 FROM budgets WHERE user_id = ?")
    has_goal = one("SELECT 1 FROM goals WHERE user_id = ? AND archived = 0")
    has_bank = one("SELECT 1 FROM balance_snapshots WHERE user_id = ?")
    gap = ledger.bank_gap(uid)
    steps = [
        {"key": "income", "title": "Add your monthly income", "sub": "Pocket money, salary or stipend", "done": has_income,
         "action": "income"},
        {"key": "auto", "title": "Turn on automatic tracking", "sub": "Payments log themselves from your phone",
         "done": has_auto, "href": "/app/settings"},
        {"key": "budget", "title": "Set one budget", "sub": "Food is a good place to start", "done": has_budget,
         "href": "/app/budgets"},
        {"key": "goal", "title": "Pick something to save for", "sub": "Round-ups go here automatically", "done": has_goal,
         "href": "/app/goals"},
        {"key": "bank", "title": "Match Flux with your bank", "done": bool(has_bank and gap is not None and abs(gap) < 1),
         "sub": "One tap, after your first bank SMS arrives" if not has_bank else "Your bank balance is ready to match",
         "action": "align" if has_bank else None},
    ]
    done = sum(1 for s in steps if s["done"])
    return {"steps": steps, "done": done, "total": len(steps), "complete": done == len(steps)}


@bp.get("/setup")
@login_required
def setup():
    return jsonify(setup_status(current_user()["id"]))


@bp.get("/dashboard")
@login_required
def dashboard():
    u = current_user()
    uid = u["id"]
    recent = get_db().execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 6", (uid,)
    ).fetchall()
    from .. import insights, ledger

    return jsonify({
        "balance": rupees(finance.balance(uid)),
        "safe": insights.safe_to_spend(uid),
        "bank": ledger.latest_bank_balance(uid),
        "reconcile": ledger.reconcile(uid),
        "bank_gap": ledger.bank_gap(uid),
        "total_saved": rupees(finance.total_saved(uid)),
        "month": finance.month_summary(uid),
        "budgets": finance.budget_status(uid),
        "goals": finance.goals_with_progress(uid),
        "health": finance.health_score(uid),
        "forecast": finance.month_forecast(uid),
        "series": finance.daily_series(uid, 30),
        "recent": [tx_json(r) for r in recent],
        "setup": setup_status(uid),
    })


# ─── Budgets ──────────────────────────────────────────────────
@bp.get("/budgets")
@login_required
def list_budgets():
    return jsonify(finance.budget_status(current_user()["id"]))


@bp.put("/budgets/<path:category>")
@login_required
def set_budget(category):
    if category not in finance.EXPENSE_CATEGORIES:
        raise ApiError("Unknown category.")
    limit = parse_amount(json_body().get("limit"), "limit")
    db = get_db()
    db.execute("INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?,?,?)"
               " ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
               (current_user()["id"], category, limit))
    db.commit()
    return jsonify(finance.budget_status(current_user()["id"]))


@bp.delete("/budgets/<path:category>")
@login_required
def delete_budget(category):
    db = get_db()
    db.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?", (current_user()["id"], category))
    db.commit()
    return jsonify(finance.budget_status(current_user()["id"]))


# ─── Goals ────────────────────────────────────────────────────
@bp.get("/goals")
@login_required
def list_goals():
    return jsonify(finance.goals_with_progress(current_user()["id"]))


def create_goal_from(data):
    u = current_user()
    title = clean_text(data.get("title"), "Goal name", 60, required=True)
    target = parse_amount(data.get("target"), "target")
    deadline = parse_date(data["deadline"], "deadline") if data.get("deadline") else None
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM goals WHERE user_id = ? AND archived = 0", (u["id"],)).fetchone()[0]
    if count >= 20:
        raise ApiError("You can have up to 20 active goals.")
    cur = db.execute("INSERT INTO goals (user_id, title, target, deadline) VALUES (?,?,?,?)",
                     (u["id"], title, target, deadline))
    # First goal automatically becomes the auto-save destination.
    if u["autosave_goal_id"] is None:
        db.execute("UPDATE users SET autosave_goal_id = ? WHERE id = ?", (cur.lastrowid, u["id"]))
    db.commit()
    return next(g for g in finance.goals_with_progress(u["id"]) if g["id"] == cur.lastrowid)


@bp.post("/goals")
@login_required
def create_goal():
    return jsonify(create_goal_from(json_body())), 201


def contribute(goal_id, amount_paise, source="manual"):
    u = current_user()
    goal = owned_or_404("goals", goal_id, u["id"])
    finance.add_transaction(u, "saving", amount_paise, finance.SAVING_CATEGORY,
                            "Added to goal" if amount_paise > 0 else "Withdrawn from goal",
                            source=source, goal_id=goal["id"])
    return next(g for g in finance.goals_with_progress(u["id"]) if g["id"] == goal_id)


@bp.post("/goals/<int:goal_id>/contribute")
@login_required
def contribute_goal(goal_id):
    data = json_body()
    amount = parse_amount(data.get("amount"))
    if data.get("withdraw"):
        amount = -amount
    goal = contribute(goal_id, amount)
    return jsonify({"goal": goal, "balance": rupees(finance.balance(current_user()["id"]))})


@bp.patch("/goals/<int:goal_id>")
@login_required
def update_goal(goal_id):
    uid = current_user()["id"]
    owned_or_404("goals", goal_id, uid)
    data = json_body()
    db = get_db()
    if "title" in data:
        db.execute("UPDATE goals SET title = ? WHERE id = ?", (clean_text(data["title"], "Goal name", 60, True), goal_id))
    if "target" in data:
        db.execute("UPDATE goals SET target = ? WHERE id = ?", (parse_amount(data["target"], "target"), goal_id))
    if "archived" in data:
        db.execute("UPDATE goals SET archived = ? WHERE id = ?", (1 if data["archived"] else 0, goal_id))
        if data["archived"]:
            db.execute("UPDATE users SET autosave_goal_id = NULL WHERE id = ? AND autosave_goal_id = ?", (uid, goal_id))
    db.commit()
    return jsonify(finance.goals_with_progress(uid, include_archived=True))


@bp.delete("/goals/<int:goal_id>")
@login_required
def delete_goal(goal_id):
    """Deleting a goal returns its savings to the balance (the saving rows go away)."""
    uid = current_user()["id"]
    owned_or_404("goals", goal_id, uid)
    db = get_db()
    db.execute("DELETE FROM transactions WHERE user_id = ? AND goal_id = ? AND kind = 'saving'", (uid, goal_id))
    db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, uid))
    db.commit()
    return jsonify({"ok": True, "balance": rupees(finance.balance(uid))})


# ─── Insights ─────────────────────────────────────────────────
@bp.get("/insights")
@login_required
def insights():
    uid = current_user()["id"]
    today = clock.today()
    this_first, _ = finance.month_bounds(today)
    prev_last = this_first - timedelta(days=1)
    from .. import insights

    return jsonify({
        "health": finance.health_score(uid),
        "recurring": insights.recurring(uid),
        "cashback": insights.cashback_report(uid),
        "accuracy": finance.categorisation_accuracy(uid),
        "forecast": finance.month_forecast(uid),
        "this_month": finance.month_summary(uid, today),
        "last_month": finance.month_summary(uid, prev_last),
    })


@bp.get("/reports/monthly.pdf")
@login_required
@rate_limit(10, 60, scope="report")
def monthly_report():
    from ..reports import monthly_pdf

    u = current_user()
    buf = monthly_pdf(u, finance.snapshot_for_ai(u))
    return send_file(buf, as_attachment=True, download_name="flux-monthly-report.pdf", mimetype="application/pdf")


@bp.get("/ledger")
@login_required
def ledger_view():
    """Books check: double-entry trial balance, bank reconciliation, latest bank-reported balance."""
    from .. import ledger

    uid = current_user()["id"]
    return jsonify({"trial_balance": ledger.trial_balance(uid), "reconcile": ledger.reconcile(uid),
                    "bank": ledger.latest_bank_balance(uid)})


@bp.post("/ledger/align")
@login_required
@rate_limit(10, 600, scope="ledger_align")
def ledger_align():
    """"Match my bank": set the opening balance so Flux agrees with the bank's latest reported balance."""
    from .. import ledger

    uid = current_user()["id"]
    out = ledger.align_to_bank(uid)
    if out is None:
        raise ApiError("Flux hasn't seen a bank balance yet. It reads it from bank SMS (\"Avl Bal\") or statements.")
    get_db().commit()
    return jsonify({**out, "balance": rupees(finance.balance(uid))})
