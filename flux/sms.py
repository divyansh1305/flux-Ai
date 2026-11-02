"""Bank SMS -> Flux row, powered by the open-source `upi-parse` library."""
from upi_parse import parse_sms as _parse_sms
from upi_parse import split_messages  # noqa: F401  (re-exported)

from . import clock


def parse_sms(text):
    tx = _parse_sms(text, today=clock.today())
    if tx is None:
        return None
    day = tx.txn_date if tx.txn_date and tx.txn_date <= clock.today() else clock.today()
    label = tx.merchant or ("Bank credit" if tx.direction == "credit" else "Bank debit")
    return {
        "date": day.isoformat(), "kind": "expense" if tx.is_debit else "income", "amount": float(tx.amount),
        "category": tx.category, "note": label[:60], "raw": tx.raw[:120], "auto": tx.category_confidence >= 0.7,
        "ref": tx.reference, "balance": float(tx.balance) if tx.balance is not None else None,
        "is_cashback": tx.is_cashback, "account_last4": tx.account_last4, "fingerprint": tx.fingerprint(),
    }
