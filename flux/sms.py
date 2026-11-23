"""Bank SMS -> Kitna row, powered by the open-source `upi-parse` library."""
from upi_parse import parse_sms as _parse_sms
from upi_parse import split_messages  # noqa: F401  (re-exported)

from . import clock


def friendly_note(note, kind="expense"):
    """Older rows saved the bank's masked payee as-is; show them the same way new ones are saved."""
    tail = _masked_tail(note)
    if tail is None:
        return note
    who = "UPI payment" if kind == "expense" else "UPI received"
    return f"{who} ••{tail}" if tail else who


def _masked_tail(label):
    """'******3484' -> '3484'; 'XXXX12' -> '12'; a real name -> None."""
    t = (label or "").strip()
    stars = sum(ch in "*xX•" for ch in t)
    if len(t) >= 4 and stars >= 3 and stars >= len(t) / 2 and " " not in t:
        tail = "".join(ch for ch in t if ch not in "*xX•")
        return tail[-4:]
    return None


def parse_sms(text, received_on=None):
    """`received_on` = when the message arrived (e.g. an email's date), used when the text has no date."""
    today = clock.today()
    tx = _parse_sms(text, today=received_on or today)
    if tx is None:
        return None
    fallback = received_on or today
    day = tx.txn_date if tx.txn_date and tx.txn_date <= today else fallback
    label = tx.merchant or ("Bank credit" if tx.direction == "credit" else "Bank debit")
    category, auto = tx.category, tx.category_confidence >= 0.7
    masked = _masked_tail(label)
    if masked is not None:
        # Banks often hide the payee ("******3484"). Say so plainly, and don't guess a category from it.
        who = "UPI payment" if tx.is_debit else "UPI received"
        label = f"{who} ••{masked}" if masked else who
        category, auto = ("Other" if tx.is_debit else "Other Income"), False
    return {
        "date": day.isoformat(), "kind": "expense" if tx.is_debit else "income", "amount": float(tx.amount),
        "category": category, "note": label[:60], "raw": tx.raw[:120], "auto": auto,
        "ref": tx.reference, "balance": float(tx.balance) if tx.balance is not None else None,
        "is_cashback": tx.is_cashback, "account_last4": tx.account_last4, "fingerprint": tx.fingerprint(),
    }
