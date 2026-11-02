"""Invest goal savings in diversified ETFs.

Real mode: the order opens in Zerodha's own Kite Publisher window. The user logs in to
*their* Zerodha account and confirms there, so the shares land in their own demat
account. Flux never holds money or places orders itself (no broker licence needed and
no automated orders under SEBI's API/algo rules).

Practice mode (no KITE_API_KEY): same flow with virtual orders, clearly labelled.
"""
import math

from flask import Blueprint, current_app, jsonify

from .. import clock, finance, market
from ..db import get_db
from ..finance import rupees
from ..security import ApiError, current_user, json_body, login_required, owned_or_404, parse_amount, rate_limit

bp = Blueprint("invest", __name__, url_prefix="/api/invest")


def _mode():
    return "kite" if current_app.config.get("KITE_API_KEY") else "practice"


@bp.get("/options")
@login_required
def options():
    items = []
    for ins in market.INSTRUMENTS:
        items.append({**ins, "price": market.price(ins["symbol"])})
    return jsonify({"mode": _mode(), "kite_api_key": current_app.config.get("KITE_API_KEY") or None, "instruments": items,
                    "disclaimer": "Investments can go down as well as up. Flux shows options, it doesn't give advice."})


@bp.post("/prepare")
@login_required
@rate_limit(20, 60, scope="invest_prepare")
def prepare():
    u = current_user()
    data = json_body()
    goal = owned_or_404("goals", data.get("goal_id"), u["id"])
    symbol = str(data.get("symbol", "")).upper()
    if symbol not in market.SYMBOLS:
        raise ApiError("Pick one of the listed funds.")
    budget = parse_amount(data.get("amount"))
    price_rupees = market.price(symbol)
    if not price_rupees:
        manual = data.get("price")
        if manual is None:
            raise ApiError("Live price unavailable right now. Enter the current price shown in your broker app.")
        price_rupees = parse_amount(manual, "price") / 100
    price_paise = round(price_rupees * 100)
    qty = math.floor(budget / price_paise)
    if qty < 1:
        raise ApiError(f"One unit of {symbol} costs about ₹{price_rupees:,.2f}. Increase the amount.")
    cost = qty * price_paise
    cash_in_goal = get_db().execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND goal_id=? AND kind='saving'",
        (u["id"], goal["id"])).fetchone()[0]
    if cost > cash_in_goal:
        raise ApiError(f"This goal has ₹{rupees(cash_in_goal):,.2f} in cash. Add money to it first.")
    db = get_db()
    db.execute("UPDATE investments SET status='cancelled' WHERE user_id=? AND status='pending'", (u["id"],))
    cur = db.execute("INSERT INTO investments (user_id, goal_id, symbol, quantity, price, mode) VALUES (?,?,?,?,?,?)",
                     (u["id"], goal["id"], symbol, qty, price_paise, _mode()))
    db.commit()
    return jsonify({
        "investment_id": cur.lastrowid, "mode": _mode(), "symbol": symbol, "quantity": qty,
        "price": rupees(price_paise), "estimated_cost": rupees(cost), "goal": goal["title"],
        # Exactly what Kite Publisher's kite.add() expects:
        "kite_order": {"exchange": "NSE", "tradingsymbol": symbol, "quantity": qty, "transaction_type": "BUY",
                       "order_type": "MARKET", "product": "CNC"},
    })


@bp.post("/<int:inv_id>/complete")
@login_required
def complete(inv_id):
    u = current_user()
    status = json_body().get("status")
    if status not in ("success", "cancelled"):
        raise ApiError("status must be success or cancelled.")
    db = get_db()
    inv = db.execute("SELECT * FROM investments WHERE id=? AND user_id=?", (inv_id, u["id"])).fetchone()
    if inv is None:
        raise ApiError("Not found.", 404)
    if inv["status"] != "pending":
        raise ApiError("Already recorded.", 409)
    if status == "cancelled":
        db.execute("UPDATE investments SET status='cancelled' WHERE id=?", (inv_id,))
        db.commit()
        return jsonify({"ok": True})
    cost = inv["quantity"] * inv["price"]
    # Move the cost out of the goal's cash; the goal's progress now counts the holding instead.
    finance.add_transaction(u, "saving", -cost, finance.SAVING_CATEGORY,
                            f"Invested in {inv['symbol']} ({inv['quantity']} units)", source="invest",
                            goal_id=inv["goal_id"], commit=False)
    db.execute("UPDATE investments SET status='holding' WHERE id=?", (inv_id,))
    db.commit()
    return jsonify({"ok": True, "holdings": _holdings(u["id"])})


def _holdings(uid):
    rows = get_db().execute(
        "SELECT i.*, g.title AS goal FROM investments i LEFT JOIN goals g ON g.id = i.goal_id"
        " WHERE i.user_id=? AND i.status='holding' ORDER BY i.created_at DESC", (uid,)).fetchall()
    out = []
    for r in rows:
        live = market.price(r["symbol"])
        cost = r["quantity"] * r["price"]
        value = round(r["quantity"] * live * 100) if live else None
        out.append({
            "id": r["id"], "symbol": r["symbol"], "quantity": r["quantity"], "avg_price": rupees(r["price"]),
            "cost": rupees(cost), "value": rupees(value) if value is not None else None,
            "pnl": rupees(value - cost) if value is not None else None,
            "mode": r["mode"], "goal": r["goal"], "date": r["created_at"][:10],
        })
    return out


@bp.get("/holdings")
@login_required
def holdings():
    items = _holdings(current_user()["id"])
    cost = sum(h["cost"] for h in items)
    value = sum(h["value"] for h in items if h["value"] is not None) if all(h["value"] is not None for h in items) else None
    return jsonify({"items": items, "cost": round(cost, 2), "value": value})


@bp.post("/<int:inv_id>/sell")
@login_required
def sell(inv_id):
    """Practice: sell at today's price, proceeds go back to the goal.
    Real (Kite): the user sells in Zerodha; this marks it sold in Flux at the price they enter."""
    u = current_user()
    db = get_db()
    inv = db.execute("SELECT * FROM investments WHERE id=? AND user_id=? AND status='holding'", (inv_id, u["id"])).fetchone()
    if inv is None:
        raise ApiError("Holding not found.", 404)
    data = json_body()
    live = market.price(inv["symbol"])
    if data.get("price") is not None:
        price_paise = parse_amount(data["price"], "price")
    elif live:
        price_paise = round(live * 100)
    else:
        raise ApiError("Enter the price you sold at.")
    proceeds = inv["quantity"] * price_paise
    cost = inv["quantity"] * inv["price"]
    pnl = proceeds - cost
    today = clock.today().isoformat()
    db.execute("UPDATE investments SET status='sold', sold_price=? WHERE id=?", (price_paise, inv_id))
    # Releasing the holding frees its cost; the gain/loss is booked separately so the ledger stays exact.
    if pnl > 0:
        db.execute("INSERT INTO transactions (user_id, kind, amount, category, note, date, source)"
                   " VALUES (?, 'income', ?, 'Investment Returns', ?, ?, 'invest')",
                   (u["id"], pnl, f"Profit on {inv['symbol']}", today))
    elif pnl < 0:
        db.execute("INSERT INTO transactions (user_id, kind, amount, category, note, date, source)"
                   " VALUES (?, 'expense', ?, 'Other', ?, ?, 'invest')",
                   (u["id"], -pnl, f"Loss on {inv['symbol']}", today))
    goal_ok = inv["goal_id"] and db.execute("SELECT 1 FROM goals WHERE id=? AND user_id=?", (inv["goal_id"], u["id"])).fetchone()
    if goal_ok:  # proceeds go back into the goal; otherwise they return to the balance
        db.execute("INSERT INTO transactions (user_id, kind, amount, category, note, date, goal_id, source)"
                   " VALUES (?, 'saving', ?, ?, ?, ?, ?, 'invest')",
                   (u["id"], proceeds, finance.SAVING_CATEGORY, f"Sold {inv['quantity']} {inv['symbol']}", today, inv["goal_id"]))
    db.commit()
    return jsonify({"ok": True, "proceeds": rupees(proceeds), "profit": rupees(pnl)})
