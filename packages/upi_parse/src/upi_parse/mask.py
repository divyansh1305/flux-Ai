"""Anonymise a bank SMS / UPI notification so it can be shared as a parser test case.

What is kept: the message *shape* (wording, amounts, balances, dates, bank, known merchant brands)
– that's what a parser needs. What is removed: anything that identifies a person or account.

    >>> mask_text("Rs.500 sent to RAHUL KUMAR (9876543210@ybl) from A/c XX4321. Ref 412345678901")
    'Rs.500 sent to PERSON (user@ybl) from A/c XX0000. Ref 000000000000'
    >>> mask_text("Rs.250 debited to VPA swiggy@icici")      # known brands survive
    'Rs.250 debited to VPA swiggy@icici'
"""
import re

from .categorize import categorize

_VPA = re.compile(r"\b([A-Za-z0-9._-]{2,256})@([A-Za-z][A-Za-z0-9.]{1,63})\b")
_ACCOUNT = re.compile(r"(?i)\b((?:a/?c|acct|account|card)(?:\s*no\.?)?\s*(?:ending\s*(?:with|in)?\s*)?[:\-]?\s*[xX*]*)(\d{3,})")
_LONG_DIGITS = re.compile(r"\d{6,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
# A run of 1–4 capitalised words after "to/from/by", e.g. "from RAHUL KUMAR", "to Priya Sharma"
_PERSON = re.compile(r"\b(to|from|by|frm)\s+([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,3})(?=[\s.(,]|$)")
_KEEP_WORDS = {"VPA", "UPI", "A", "AC", "IMPS", "NEFT", "RTGS", "ATM", "POS", "NACH", "ACH", "BANK", "YOUR", "YOU",
               "SAVINGS", "SB", "CARD", "ACCOUNT", "NET", "BANKING"}


def _is_brand(text: str) -> bool:
    _cat, confidence, reason = categorize(text, "debit")
    return confidence >= 0.9 and reason.startswith("known merchant")


def _vpa(m: "re.Match") -> str:
    local, handle = m.group(1), m.group(2)
    return m.group(0) if _is_brand(local) and not re.search(r"\d{4,}", local) else f"user@{handle}"


def _person(m: "re.Match") -> str:
    lead, name = m.group(1), m.group(2).strip()
    words = [w.strip(".").upper() for w in name.split()]
    if not words or all(w in _KEEP_WORDS for w in words) or _is_brand(name):
        return m.group(0)
    return f"{lead} PERSON"


def mask_text(text: str) -> str:
    out = _VPA.sub(_vpa, text)
    out = _ACCOUNT.sub(lambda m: m.group(1) + "0" * len(m.group(2)), out)
    out = _PHONE.sub(lambda m: re.sub(r"\d", "0", m.group(0)), out)
    out = _LONG_DIGITS.sub(lambda m: "0" * len(m.group(0)), out)
    out = _PERSON.sub(_person, out)
    return out
