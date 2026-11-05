"""Plans (money you expect to spend or receive) and money checks."""
from datetime import date, timedelta

from flask import Blueprint, jsonify

from .. import analytics, checks, clock
from ..db import get_db
from ..finance import rupees
from ..security import ApiError, clean_text, current_user, json_body, login_required, parse_amount, parse_date

bp = Blueprint("plans", __name__, url_prefix="/api")


def plan_json(r):
    return {"id": r["id"], "kind": r["kind"], "title": r["title"], "amount": rupees(r["amount"]), "date": r["date"],
            "sure": bool(r["sure"]), "done": bool(r["done"])}


def _payload(data, partial=False):
    out = {}
    if not partial or "title" in data:
        out["title"] = clean_text(data.get("title"), "What it's for", 60, required=True)
    if not partial or "amount" in data:
        amount = parse_amount(data.get("amount"), "Amount")
        if amount <= 0:
            raise ApiError("Amount must be more than zero.")
        out["amount"] = amount
    if not partial or "date" in data:
        d = parse_date(data.get("date"))
        today = clock.today()
        if date.fromisoformat(d) < today - timedelta(days=1):
            raise ApiError("Pick today or a day in the future.")
        if date.fromisoformat(d) > today + timedelta(days=400):
            raise ApiError("Plans can be up to a year ahead.")
        out["date"] = d
    if not partial or "kind" in data:
        kind = data.get("kind", "spend")
        if kind not in ("spend", "income"):
            raise ApiError("A plan is either money going out or money coming in.")
        out["kind"] = kind
    if "sure" in data or not partial:
        out["sure"] = 0 if data.get("sure") is False else 1
    if partial and "done" in data:
        out["done"] = 1 if data["done"] else 0
    return out


@bp.get("/plans")
@login_required
def list_plans():
    uid = current_user()["id"]
    since = (clock.today() - timedelta(days=7)).isoformat()
    rows = get_db().execute("SELECT * FROM plans WHERE user_id = ? AND (date >= ? OR done = 0) ORDER BY date, id",
                            (uid, since)).fetchall()
    return jsonify([plan_json(r) for r in rows])


@bp.post("/plans")
@login_required
def create_plan():
    uid = current_user()["id"]
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM plans WHERE user_id = ? AND done = 0", (uid,)).fetchone()[0] >= 200:
        raise ApiError("That's a lot of open plans. Finish or delete a few first.")
    p = _payload(json_body())
    cur = db.execute("INSERT INTO plans (user_id, kind, title, amount, date, sure) VALUES (?,?,?,?,?,?)",
                     (uid, p["kind"], p["title"], p["amount"], p["date"], p["sure"]))
    analytics.track(uid, "plan_added", p["kind"])
    db.commit()
    return jsonify(plan_json(db.execute("SELECT * FROM plans WHERE id = ?", (cur.lastrowid,)).fetchone())), 201


@bp.patch("/plans/<int:plan_id>")
@login_required
def update_plan(plan_id):
    uid = current_user()["id"]
    db = get_db()
    if not db.execute("SELECT 1 FROM plans WHERE id = ? AND user_id = ?", (plan_id, uid)).fetchone():
        raise ApiError("Plan not found.", 404)
    p = _payload(json_body(), partial=True)
    if p:
        cols = ", ".join(f"{k} = ?" for k in p)  # keys come from _payload's whitelist
        db.execute(f"UPDATE plans SET {cols} WHERE id = ? AND user_id = ?", (*p.values(), plan_id, uid))
        db.commit()
    return jsonify(plan_json(db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()))


@bp.delete("/plans/<int:plan_id>")
@login_required
def delete_plan(plan_id):
    uid = current_user()["id"]
    db = get_db()
    cur = db.execute("DELETE FROM plans WHERE id = ? AND user_id = ?", (plan_id, uid))
    db.commit()
    if not cur.rowcount:
        raise ApiError("Plan not found.", 404)
    return jsonify({"ok": True})


@bp.get("/checks")
@login_required
def list_checks():
    return jsonify(checks.all_checks(current_user()["id"]))


@bp.post("/checks/dismiss")
@login_required
def dismiss_check():
    key = str(json_body().get("key", ""))[:120]
    if not key or ":" not in key:
        raise ApiError("Unknown check.")
    checks.dismiss(current_user()["id"], key)
    return jsonify({"ok": True})
