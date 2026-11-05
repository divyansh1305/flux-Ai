"""Thin adapter over the open-source `upi-parse` library (packages/upi_parse)."""
from upi_parse import categorize as _categorize
from upi_parse._common import clean_merchant


def categorize(description, kind):
    """Kitna kinds ('expense'/'income') -> (category, matched_reason or None if it was a guess)."""
    cat, conf, reason = _categorize(description, "credit" if kind == "income" else "debit")
    return cat, (reason if conf >= 0.7 else None)


def merchant_name(description):
    return clean_merchant(description) or (description or "")[:40]
