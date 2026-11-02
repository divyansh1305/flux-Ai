"""Scan & Pay: the pause-before-pay flow.

1. /api/pay/parse    read a scanned UPI QR -> payee, amount, suggested category
2. /api/pay/prepare  run the pre-spend check, create a pending payment, return UPI app links
3. user pays in their own UPI app (GPay/PhonePe/…), comes back
4. /api/pay/<id>/confirm  "paid" logs the expense (+ auto-save) automatically
"""
import secrets

from flask import Blueprint, jsonify

from .. import finance, upi
from ..categorize import categorize
from ..db import get_db
from ..finance import rupees
from ..security import ApiError, clean_text, current_user, json_body, login_required, parse_amount, rate_limit

bp = Blueprint("pay", __name__, url_prefix="/api/pay")


def _payee(uid, vpa):
    return get_db().execute("SELECT * FROM payees WHERE user_id = ? AND vpa = ?", (uid, vpa)).fetchone()


def describe(parsed, uid):
    known = _payee(uid, parsed["pa"])
    if known:
        category, why = known["category"], f"you've paid them {known['times_paid']} time(s) before"
    else:
        category, why = upi.category_for(parsed, categorize)
    return {
        "vpa": parsed["pa"],
        "name": parsed["pn"] or (known["name"] if known else "") or parsed["pa"].split("@")[0],
        "amount": float(parsed["am"]) if parsed["am"] is not None else None,
        "amount_locked": parsed["am"] is not None and bool(parsed.get("tr")),
        "note": parsed["tn"],
        "is_merchant": parsed["is_merchant"],
        "category": category,
        "category_reason": why,
        "known_payee": bool(known),
    }


@bp.post("/parse")
@login_required
@rate_limit(60, 60, scope="pay_parse")
def parse():
    data = json_body()
    parsed = upi.parse_upi_uri(clean_text(data.get("code"), "QR code", 1000, required=True))
    return jsonify(describe(parsed, current_user()["id"]))


@bp.post("/prepare")
@login_required
@rate_limit(30, 60, scope="pay_prepare")
def prepare():
    u = current_user()
    data = json_body()
    vpa = clean_text(data.get("vpa"), "UPI ID", 300, required=True).lower()
    if not upi.valid_vpa(vpa):
        raise ApiError("Enter a valid UPI ID, like name@okaxis.")
    name = clean_text(data.get("name"), "Payee name", 80) or vpa.split("@")[0]
    amount = parse_amount(data.get("amount"))
    if amount > 100_000_00:
        raise ApiError("UPI payments are limited to ₹1,00,000.")
    category = clean_text(data.get("category") or "Other", "Category", 40)
    if category not in finance.EXPENSE_CATEGORIES:
        raise ApiError("Unknown category.")
    note = clean_text(data.get("note"), "Note", 50)

    check = finance.pre_spend_check(u, amount, category)
    ref = "FLX" + secrets.token_hex(8).upper()
    db = get_db()
    # Expire this user's stale pending payments so the list stays clean.
    db.execute("UPDATE payments SET status='cancelled' WHERE user_id=? AND status='pending' AND created_at < datetime('now','-1 day')",
               (u["id"],))
    cur = db.execute("INSERT INTO payments (user_id, ref, payee_vpa, payee_name, amount, category, note) VALUES (?,?,?,?,?,?,?)",
                     (u["id"], ref, vpa, name, amount, category, note))
    db.commit()
    links = upi.build_links(vpa, name, f"{amount / 100:.2f}", note or f"Flux {category}", ref)
    return jsonify({"payment_id": cur.lastrowid, "ref": ref, "check": check, "links": links,
                    "amount": rupees(amount), "name": name, "vpa": vpa, "category": category})


@bp.post("/<int:payment_id>/confirm")
@login_required
def confirm(payment_id):
    u = current_user()
    status = json_body().get("status")
    if status not in ("paid", "failed", "cancelled"):
        raise ApiError("status must be paid, failed or cancelled.")
    db = get_db()
    p = db.execute("SELECT * FROM payments WHERE id = ? AND user_id = ?", (payment_id, u["id"])).fetchone()
    if p is None:
        raise ApiError("Payment not found.", 404)
    if p["status"] != "pending":
        raise ApiError("This payment was already recorded.", 409)
    result = {"status": status}
    if status == "paid":
        label = p["payee_name"] or p["payee_vpa"]
        res = finance.add_transaction(u, "expense", p["amount"], p["category"], f"{label} · UPI"[:140],
                                      source="upi", commit=False)
        db.execute("UPDATE payments SET status='paid', transaction_id=? WHERE id=?", (res["id"], p["id"]))
        db.execute("INSERT INTO payees (user_id, vpa, name, category, times_paid) VALUES (?,?,?,?,1)"
                   " ON CONFLICT(user_id, vpa) DO UPDATE SET name=excluded.name, category=excluded.category,"
                   " times_paid = times_paid + 1", (u["id"], p["payee_vpa"], p["payee_name"], p["category"]))
        result.update(transaction_id=res["id"], autosaved=rupees(res["autosaved"]), autosave_goal=res["autosave_goal"])
    else:
        db.execute("UPDATE payments SET status=? WHERE id=?", (status, p["id"]))
    db.commit()
    result["balance"] = rupees(finance.balance(u["id"]))
    return jsonify(result)


@bp.get("/pending")
@login_required
def pending():
    rows = get_db().execute(
        "SELECT id, payee_name, payee_vpa, amount, category, created_at FROM payments WHERE user_id = ? AND status = 'pending'"
        " AND created_at >= datetime('now','-1 day') ORDER BY id DESC LIMIT 5", (current_user()["id"],)).fetchall()
    return jsonify([{**dict(r), "amount": rupees(r["amount"])} for r in rows])


@bp.get("/payees")
@login_required
def payees():
    rows = get_db().execute("SELECT vpa, name, category, times_paid FROM payees WHERE user_id = ? ORDER BY times_paid DESC LIMIT 8",
                            (current_user()["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])
