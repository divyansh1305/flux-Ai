# upi-parse

**Turn messy Indian bank SMS, UPI app notifications, UPI QR codes and bank statements into clean, categorised transactions.** Zero dependencies, typed, ~0.3 ms per message.

```python
>>> from upi_parse import parse_sms
>>> t = parse_sms("Rs.250.00 debited from A/c XX1234 on 01-11-26 to VPA swiggy@icici "
...               "(UPI Ref No 512345678901). Avl Bal Rs 9,750.00")
>>> t.direction, t.amount, t.merchant, t.category, t.balance, t.reference
('debit', Decimal('250.00'), 'Swiggy', 'Food & Dining', Decimal('9750.00'), '512345678901')
```

## Why
Over 80% of Indian digital payments are UPI, but every bank and app words its alerts differently. Expense trackers, budgeting apps and lending tools all rewrite the same fragile regexes. `upi-parse` is one tested, open implementation.

## What it extracts
| Field | Example |
|---|---|
| `direction` | `debit` / `credit` (first verb wins: "debited … SWIGGY credited" is a debit; "Credit Card" isn't a credit) |
| `amount` | `Decimal('250.00')` (never the balance or credit limit) |
| `merchant` | `Swiggy` (cleaned from `UPI/DR/…/SWIGGY/YESB/…`; legal names mapped: `BUNDL TECHNOLOGIES` → Swiggy) |
| `vpa`, `reference` (UPI ref / UTR / RRN), `account_last4`, `channel` (UPI/NEFT/IMPS/POS/ATM/ACH/CARD) | |
| `balance` | the bank's "Avl Bal", for reconciling against your own ledger |
| `category` + `category_confidence` + `category_reason` | `Food & Dining`, `0.95`, `known merchant “swiggy”` |
| `is_cashback`, `is_refund` | |
| `fingerprint()` | the same payment from SMS, notification and statement gets the same key, so you can de-duplicate |

It ignores OTPs, offers, payment *requests*, failed or declined payments, upcoming autopay reminders and bill-due notices.

## API
```python
from upi_parse import (parse_sms, split_messages, parse_notification, parse_narration,
                       parse_statement_csv, parse_upi_uri, build_upi_uri, categorize, mask_text)

parse_notification("₹250 paid to Swiggy", "Paid from HDFC Bank •• 1234", package="com.google.android.apps.nbu.paisa.user")
parse_narration("UPI/DR/512345678901/SWIGGY/YESB/swiggy@ybl", 245, "debit")
txs, skipped = parse_statement_csv(open("statement.csv").read())
parse_upi_uri("upi://pay?pa=shop@okaxis&pn=Chai%20Point&am=60&mc=5812")   # NPCI linking spec
build_upi_uri("shop@okaxis", "Chai Point", "60.00", note="tea")
categorize("POS DECATHLON SPORTS", "debit")      # ('Shopping', 0.95, 'known merchant “decathlon”')
mask_text("Rs.500 sent to RAHUL KUMAR (9876543210@ybl) from A/c XX4321")
# 'Rs.500 sent to PERSON (user@ybl) from A/c XX0000' – share test cases without personal data
```
CLI: `upi-parse "Rs.250 debited from A/c XX1234 to VPA swiggy@icici"` (or pipe messages in).

## Accuracy: measured honestly
Measured with `python benchmarks/evaluate.py <file>`:

| Dataset | Detection P / R | Direction | Amount | Merchant | Category | Reference | Balance |
|---|---|---|---|---|---|---|---|
| **Held-out v1, first run** (38 hand-written messages in bank formats not used during development: Canara, IDFC, Yes, IndusInd, Union, Federal, BoI, Paytm Bank, CRED…) | **100% / 96.7%** | **96.6%** | **100%** | **79.2%** | **86.2%** | **91.7%** | **75.0%** |
| Held-out v1, after fixing the failures it revealed | 100% / 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Synthetic v1 (1,220 generated messages: 10 banks, 4 UPI apps, statements, 160 tricky negatives) | 100% / 100% | 100% | 100% | 100% | 100% | 100% | 100% |

**Read this table correctly:** the first-run held-out row is the only true out-of-sample number. Both sets have since influenced the rules, so they are now regression tests, not accuracy claims. Real-world accuracy has to be measured on real, consented messages; the Kitna app has a contribution tool for that, and its results will be published here.

## Development
```bash
pip install -e . pytest
pytest
python benchmarks/generate.py                  # rebuild the synthetic set
python benchmarks/evaluate.py benchmarks/heldout_v1.jsonl --errors 10
```
Contributions welcome. The most valuable is a new held-out sample from a bank format that isn't covered (with personal details removed).

MIT licence.
