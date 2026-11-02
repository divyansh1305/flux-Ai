"""Bank statement rows (narration + debit/credit) → Transaction, and whole CSV statements."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from . import _common as c
from .categorize import categorize
from .model import Transaction

DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y",
                "%d %b %y", "%d/%b/%Y", "%d.%m.%Y", "%d %B %Y", "%b %d, %Y"]
DESC_TOKENS = {"narration", "description", "particulars", "remarks", "details", "merchant"}
UTR_IN_NARRATION = re.compile(r"(?<!\d)(\d{12})(?!\d)")


def parse_narration(narration: str, amount, direction: str, txn_date: Optional[date] = None) -> Transaction:
    text = re.sub(r"\s+", " ", narration or "").strip()
    amt = c.to_decimal(str(amount)) or Decimal("0.00")
    vpa = c.find_vpa(text)
    merchant = c.clean_merchant(text) or (c.clean_merchant(vpa) if vpa else "")
    ref = c.find_reference(text)
    if not ref and re.search(r"\bupi\b", text, re.I):
        m = UTR_IN_NARRATION.search(text)  # UPI narrations embed the 12-digit RRN
        ref = m.group(1) if m else None
    category, conf, reason = categorize(f"{merchant} {vpa or ''} {text}", direction)
    return Transaction(
        direction=direction, amount=amt, source="narration", raw=text[:500], merchant=merchant, vpa=vpa,
        channel=c.find_channel(text), reference=ref, txn_date=txn_date,
        is_cashback=direction == "credit" and bool(c.CASHBACK_RE.search(text)),
        is_refund=direction == "credit" and bool(c.REFUND_RE.search(text)),
        category=category, category_confidence=conf, category_reason=reason,
    )


def _tokens(h: str) -> set:
    return set(re.findall(r"[a-z]+", h.lower()))


def _find(headers, *sets):
    for i, h in enumerate(headers):
        toks = _tokens(h)
        if any(s <= toks for s in sets):
            return i
    return None


def _to_date(value: str) -> Optional[date]:
    v = value.strip()
    if re.match(r"^\d{1,4}[-/.]\d", v):
        v = v.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _num(value: str) -> Optional[Decimal]:
    v = (value or "").strip().replace(",", "").replace("₹", "").replace("INR", "").strip()
    if not v or v in {"-", "--"}:
        return Decimal("0")
    neg = v.startswith("(") and v.endswith(")")
    try:
        n = Decimal(v.strip("()"))
    except Exception:
        return None
    return -n if neg else n


class StatementError(ValueError):
    pass


def parse_statement_csv(text: str, max_rows: int = 5000) -> Tuple[List[Transaction], int]:
    """Parse a bank statement CSV (HDFC, SBI, ICICI, Axis, Kotak… or Date/Description/Amount/Type).
    Returns (transactions, skipped_row_count). Raises StatementError if the format isn't recognised."""
    lines = (text or "").splitlines()
    header_idx = None
    for i, line in enumerate(lines[:60]):
        low = line.lower()
        if "date" in low and any(w in low for w in DESC_TOKENS):
            header_idx = i
            break
    if header_idx is None:
        raise StatementError("Couldn't find a header row with Date and Description/Narration columns.")
    try:
        dialect = csv.Sniffer().sniff(lines[header_idx], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])), dialect)
    headers = [h.strip() for h in next(reader)]
    i_date = _find(headers, {"date"})
    i_desc = next((i for i, h in enumerate(headers) if _tokens(h) & DESC_TOKENS), None)
    i_debit = _find(headers, {"withdrawal"}, {"withdrawals"}, {"debit"}, {"dr"})
    i_credit = _find(headers, {"deposit"}, {"deposits"}, {"credit"}, {"cr"})
    i_amount = _find(headers, {"amount"})
    i_type = _find(headers, {"type"}, {"dr", "cr"})
    i_bal = _find(headers, {"balance"})
    if i_date is None or i_desc is None or (i_debit is None and i_credit is None and i_amount is None):
        raise StatementError("Unsupported CSV: needs Date, Description and Debit/Credit (or Amount) columns.")

    out, skipped = [], 0
    for rec in reader:
        if len(out) >= max_rows:
            break
        get = lambda i: rec[i] if i is not None and i < len(rec) else ""  # noqa: E731
        d = _to_date(get(i_date))
        desc = get(i_desc).strip()
        if d is None or not desc:
            skipped += 1
            continue
        debit, credit = _num(get(i_debit)), _num(get(i_credit))
        if (not debit and not credit) and i_amount is not None:
            amt = _num(get(i_amount))
            if amt is None:
                skipped += 1
                continue
            kind = get(i_type).strip().lower()
            if kind.startswith(("dr", "debit")) or (not kind and amt < 0):
                debit, credit = abs(amt), Decimal("0")
            else:
                debit, credit = Decimal("0"), abs(amt)
        debit, credit = debit or Decimal("0"), credit or Decimal("0")
        if debit <= 0 and credit <= 0:
            skipped += 1
            continue
        direction = "debit" if debit > 0 else "credit"
        tx = parse_narration(desc, debit if debit > 0 else credit, direction, d)
        bal = _num(get(i_bal)) if i_bal is not None else None
        if bal:
            tx.balance = bal.quantize(Decimal("0.01"))
        out.append(tx)
    return out, skipped
