"""Bank statement import: upload CSV -> preview with categories -> confirm import."""
import hashlib

from flask import Blueprint, jsonify, request

from .. import finance
from ..db import get_db
from ..security import ApiError, clean_text, current_user, json_body, login_required, parse_amount, parse_date, rate_limit

bp = Blueprint("statement", __name__, url_prefix="/api/import")

MAX_ROWS = 3000
def parse_statement(text):
    """CSV statement -> Flux rows, using the open-source upi-parse statement parser."""
    from upi_parse import StatementError, parse_statement_csv

    try:
        txs, skipped = parse_statement_csv(text, max_rows=MAX_ROWS)
    except StatementError as e:
        raise ApiError(str(e) + " Most banks export this as CSV from net banking.")
    rows = []
    for t in txs:
        rows.append({
            "date": t.txn_date.isoformat(), "kind": "expense" if t.is_debit else "income",
            "amount": float(t.amount), "category": t.category, "note": t.merchant or t.raw[:40],
            "raw": t.raw[:120], "auto": t.category_confidence >= 0.7,
            "balance": float(t.balance) if t.balance is not None else None, "ref": t.reference,
        })
    return rows, skipped


def _hash(uid, row):
    key = f"{uid}|{row['date']}|{row['kind']}|{row['amount']:.2f}|{row['raw']}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


@bp.post("/preview")
@login_required
@rate_limit(20, 600, scope="import_preview")
def preview():
    f = request.files.get("file")
    if f is None or not f.filename:
        raise ApiError("Choose a statement file to upload.")
    name = f.filename.lower()
    raw = f.read()
    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        from .. import pdf_statement

        try:
            rows, skipped = pdf_statement.to_rows(raw, request.form.get("password") or None, MAX_ROWS)
        except pdf_statement.NeedsPassword as e:
            return jsonify({"needs_password": True, "wrong": e.wrong, "message": e.message})
        fmt = "pdf"
    elif name.endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        rows, skipped = parse_statement(text)
        fmt = "csv"
    else:
        raise ApiError("Upload the PDF your bank emails you, or a CSV from net banking. "
                       "Excel file? Open it and “Save as” CSV first.")
    if not rows:
        raise ApiError("No transactions found in this file.")
    uid = current_user()["id"]
    existing = {r[0] for r in get_db().execute(
        "SELECT import_hash FROM transactions WHERE user_id = ? AND import_hash IS NOT NULL", (uid,))}
    for r in rows:
        r["duplicate"] = _hash(uid, r) in existing
    auto = sum(1 for r in rows if r["auto"])
    return jsonify({
        "rows": rows, "skipped": skipped, "format": fmt,
        "stats": {"total": len(rows), "auto_categorised": auto,
                  "auto_percent": round(auto / len(rows) * 100), "duplicates": sum(r["duplicate"] for r in rows)},
        "categories": {"expense": finance.EXPENSE_CATEGORIES, "income": finance.INCOME_CATEGORIES},
    })


@bp.post("/sms")
@login_required
@rate_limit(30, 600, scope="import_sms")
def sms_preview():
    """Parse pasted (or shared) bank SMS alerts into reviewable rows."""
    from ..sms import parse_sms, split_messages

    text = str(json_body().get("text") or "")  # newlines matter here, so no clean_text()
    if not text.strip():
        raise ApiError("Paste at least one bank SMS.")
    if len(text) > 20000:
        raise ApiError("That's too much text. Paste up to about 100 messages at a time.")
    uid = current_user()["id"]
    existing = {r[0] for r in get_db().execute(
        "SELECT import_hash FROM transactions WHERE user_id = ? AND import_hash IS NOT NULL", (uid,))}
    rows, ignored = [], 0
    for msg in split_messages(text):
        row = parse_sms(msg)
        if row is None:
            ignored += 1
            continue
        row["duplicate"] = _hash(uid, row) in existing
        rows.append(row)
    if not rows:
        raise ApiError("No bank transactions found. Paste debit/credit alert SMS (OTPs and offers are ignored).")
    return jsonify({"rows": rows, "ignored": ignored,
                    "categories": {"expense": finance.EXPENSE_CATEGORIES, "income": finance.INCOME_CATEGORIES}})


@bp.post("/commit")
@login_required
@rate_limit(20, 600, scope="import_commit")
def commit():
    body = json_body()
    items = body.get("rows")
    source = "sms" if body.get("source") == "sms" else "import"
    if not isinstance(items, list) or not items:
        raise ApiError("Nothing to import.")
    if len(items) > MAX_ROWS:
        raise ApiError(f"At most {MAX_ROWS} rows per import.")
    from .. import ledger

    u = current_user()
    db = get_db()
    imported = dupes = 0
    latest_balance = None  # (date, balance_paise, tx_id, account)
    try:
        for it in items:
            if not isinstance(it, dict):
                raise ApiError("Bad row.")
            kind = it.get("kind")
            if kind not in ("income", "expense"):
                raise ApiError("Bad row type.")
            row = {
                "date": parse_date(it.get("date")), "kind": kind,
                "amount": parse_amount(it.get("amount")) / 100,
                "raw": clean_text(it.get("raw"), "Description", 120),
            }
            ref = str(it.get("ref") or "")
            ref = ref if ref.isdigit() and 9 <= len(ref) <= 16 else None
            h = _hash(u["id"], row)
            amount = round(row["amount"] * 100)
            if db.execute("SELECT 1 FROM transactions WHERE user_id = ? AND import_hash = ?", (u["id"], h)).fetchone():
                dupes += 1
                continue
            dup = ledger.find_duplicate(u["id"], kind, amount, row["date"], ref, source, window_days=0 if source == "import" else 1)
            if dup:  # already logged via Scan & Pay / SMS / notification
                if ref:
                    db.execute("UPDATE transactions SET ref = COALESCE(ref, ?) WHERE id = ?", (ref, dup))
                dupes += 1
                tx_id = dup
            else:
                res = finance.add_transaction(
                    u, kind, amount, clean_text(it.get("category"), "Category", 40),
                    clean_text(it.get("note"), "Note", 140), row["date"], source=source, import_hash=h, ref=ref,
                    autosave=False, commit=False,  # past spending shouldn't trigger auto-saves today
                )
                imported += 1
                tx_id = res["id"]
            bal = it.get("balance")
            if isinstance(bal, (int, float)) and not isinstance(bal, bool) and 0 <= bal < 1e10:
                if latest_balance is None or row["date"] >= latest_balance[0]:
                    latest_balance = (row["date"], round(bal * 100), tx_id, it.get("account_last4"))
        if latest_balance:
            ledger.record_snapshot(u["id"], latest_balance[1], latest_balance[0], source,
                                   str(latest_balance[3])[:4] if latest_balance[3] else None, latest_balance[2])
        db.commit()
    except Exception:
        db.rollback()
        raise
    if source == "import" and imported:
        from .. import analytics

        analytics.track(u["id"], "statement_import", "pdf" if body.get("format") == "pdf" else "csv")
    return jsonify({"imported": imported, "duplicates_skipped": dupes, "balance": finance.rupees(finance.balance(u["id"]))})
