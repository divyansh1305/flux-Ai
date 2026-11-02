"""upi-parse: understand Indian bank SMS, UPI notifications, UPI QR codes and statements.

    >>> from upi_parse import parse_sms
    >>> t = parse_sms("Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici (UPI Ref No 512345678901). Avl Bal Rs 9,750.00")
    >>> t.direction, t.amount, t.merchant, t.category, t.balance, t.reference
    ('debit', Decimal('250.00'), 'Swiggy', 'Food & Dining', Decimal('9750.00'), '512345678901')
"""
from .categorize import EXPENSE_CATEGORIES, INCOME_CATEGORIES, MCC_CATEGORIES, categorize
from .mask import mask_text
from .model import Transaction
from .narration import StatementError, parse_narration, parse_statement_csv
from .notification import PACKAGES as NOTIFICATION_PACKAGES
from .notification import parse_notification
from .qr import UPIError, UPIRequest, build_upi_uri, parse_upi_uri, valid_vpa
from .sms import parse_sms, split_messages

__version__ = "0.1.0"
__all__ = [
    "Transaction", "mask_text", "parse_sms", "split_messages", "parse_notification", "parse_narration", "parse_statement_csv",
    "parse_upi_uri", "build_upi_uri", "valid_vpa", "categorize", "UPIRequest", "UPIError", "StatementError",
    "EXPENSE_CATEGORIES", "INCOME_CATEGORIES", "MCC_CATEGORIES", "NOTIFICATION_PACKAGES",
]
