"""The Transaction type every parser returns."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    direction: str                      # "debit" (money out) or "credit" (money in)
    amount: Decimal                     # rupees, 2 decimal places
    source: str                         # "sms" | "notification" | "narration" | "qr"
    raw: str
    merchant: str = ""                  # human-readable payee/payer, e.g. "Swiggy"
    vpa: Optional[str] = None           # UPI ID, e.g. "swiggy@icici"
    channel: Optional[str] = None       # UPI | NEFT | IMPS | RTGS | POS | ATM | CARD | ACH
    account_last4: Optional[str] = None
    reference: Optional[str] = None     # UPI ref / UTR / RRN (best key for de-duplication)
    balance: Optional[Decimal] = None   # "Avl Bal" reported by the bank after this transaction
    txn_date: Optional[date] = None
    is_cashback: bool = False
    is_refund: bool = False
    category: str = "Other"
    category_confidence: float = 0.0
    category_reason: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def is_debit(self) -> bool:
        return self.direction == "debit"

    def fingerprint(self) -> str:
        """Stable key to recognise the same payment arriving from different sources
        (bank SMS, UPI app notification, bank statement).

        With a UPI reference/UTR it is exact. Without one it falls back to
        direction + amount + date, which callers should combine with a time window.
        """
        if self.reference:
            basis = f"ref|{self.reference}"
        else:
            basis = f"amt|{self.direction}|{self.amount}|{self.txn_date or ''}"
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["amount"] = str(self.amount)
        d["balance"] = str(self.balance) if self.balance is not None else None
        d["txn_date"] = self.txn_date.isoformat() if self.txn_date else None
        d["fingerprint"] = self.fingerprint()
        return d
