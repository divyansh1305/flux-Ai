"""Bank statement PDFs (the ones banks email every month), including password-protected ones.

Most Indian bank PDFs have no real table lines, so Kitna reads where each word sits on the page:
  1. find the header row (Date … Narration … Withdrawal … Deposit … Balance) and remember each column's position;
  2. every line that starts with a date is a new payment; lines without a date continue its description;
  3. an amount under "Withdrawal/Debit" is money out, under "Deposit/Credit" is money in, under "Balance" is the
     balance. With no usable header, the change in balance decides; failing that, words like "CR"/"DR".
The file is read in memory and never stored. Rows then go through the same preview → confirm as CSV imports.
"""
import io
import re
from decimal import Decimal

from .security import ApiError

MAX_PAGES = 60
MONEY = re.compile(r"^\(?-?(?:₹|INR|Rs\.?)?\s?(?:\d{1,3}(?:,\d{2,3})+|\d+)\.\d{1,2}\)?(?:\s?(?:cr|dr))?$", re.I)
DATE_START = re.compile(r"^\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3})[-/.]\d{2,4}$|^\d{4}-\d{2}-\d{2}$")
DESC_WORDS = {"narration", "description", "particulars", "details", "remarks", "transaction"}
DEBIT_WORDS = {"withdrawal", "withdrawals", "debit", "debits", "dr", "withdrawalamt", "paid"}
CREDIT_WORDS = {"deposit", "deposits", "credit", "credits", "cr", "depositamt", "received"}
BAL_WORDS = {"balance", "closing", "bal"}


class NeedsPassword(ApiError):
    def __init__(self, wrong=False):
        super().__init__("That password didn't open the PDF. Banks usually use part of your name and date of birth, "
                         "or your customer ID: check the email the statement came with." if wrong else
                         "This PDF is password-protected. Enter the password from your bank's email.", 400)
        self.wrong = wrong


def _suffix(text):
    m = re.search(r"(cr|dr)\.?$", text.strip(), re.I)
    return m.group(1).lower() if m else None


def _num(text):
    text = re.sub(r"\s?(cr|dr)\.?$", "", text.strip(), flags=re.I)
    t = text.replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").replace("Rs", "").strip()
    neg = t.startswith("(") and t.endswith(")")
    try:
        n = Decimal(t.strip("()"))
    except Exception:
        return None
    return -n if neg else n


def _key(w):
    return re.sub(r"[^a-z]", "", w.lower())


def _lines(page):
    words = page.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2)
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1]["top"] - w["top"]) <= 3:
            rows[-1]["words"].append(w)
        else:
            rows.append({"top": w["top"], "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda w: w["x0"])
    return rows


def _header(line):
    keys = [_key(w["text"]) for w in line["words"]]
    if "date" not in " ".join(keys) or not any(k in DESC_WORDS for k in keys):
        return None
    cols = {}
    for w, k in zip(line["words"], keys):
        if k in DEBIT_WORDS or k.startswith("withdraw") or k.startswith("debit"):
            cols.setdefault("debit", (w["x0"], w["x1"]))
        elif k in CREDIT_WORDS or k.startswith("deposit") or k.startswith("credit"):
            cols.setdefault("credit", (w["x0"], w["x1"]))
        elif k in BAL_WORDS or k.startswith("balance"):
            cols["balance"] = (w["x0"], w["x1"])
    return cols


def _closest(cols, w):
    mid_r = w["x1"]  # amounts are right-aligned: compare right edges first
    best, dist = None, None
    for name, (x0, x1) in cols.items():
        d = min(abs(mid_r - x1), abs((w["x0"] + w["x1"]) / 2 - (x0 + x1) / 2))
        if dist is None or d < dist:
            best, dist = name, d
    return best


def extract(data, password=None):
    """PDF bytes -> (list of (date, description, debit, credit, balance), skipped). Raises ApiError."""
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from upi_parse.narration import _to_date

    try:
        pdf = pdfplumber.open(io.BytesIO(data), password=password or "")
    except PDFPasswordIncorrect:
        raise NeedsPassword(wrong=bool(password))
    except Exception as e:  # noqa: BLE001 - pdfplumber wraps pdfminer's errors
        inner = e.args[0] if e.args else None
        if isinstance(inner, PDFPasswordIncorrect) or "password" in (str(e) + repr(inner)).lower():
            raise NeedsPassword(wrong=bool(password))
        raise ApiError("Couldn't read this PDF. If it's a scan or photo, download the statement again from net banking.")
    out, skip = [], [0]
    cols, last_balance = None, None
    with pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise ApiError(f"That statement has more than {MAX_PAGES} pages. Download a shorter period.")
        try:
            pages = [_lines(p) for p in pdf.pages]
        except PDFPasswordIncorrect:
            raise NeedsPassword(wrong=bool(password))
    current = None

    def finish():
        nonlocal current, last_balance
        if current is None:
            return
        d, desc, amounts = current
        debit = credit = balance = None
        unknown = []
        for w in amounts:
            n = _num(w["text"])
            if n is None:
                continue
            side = _closest(cols, w) if cols else None
            if side == "balance":
                balance = n
            elif side == "debit":
                debit = abs(n)
            elif side == "credit":
                credit = abs(n)
            else:
                unknown.append((w, n))
        if unknown and not cols:
            if len(unknown) >= 2:  # usual layout without a header we understood: …, amount, balance
                balance = unknown[-1][1]
                unknown = unknown[:-1]
            amt = abs(unknown[-1][1]) if unknown else None
            if amt is not None:
                tail = " ".join(desc).upper()
                hint = _suffix(unknown[-1][0]["text"])
                if hint:
                    is_credit = hint == "cr"
                elif last_balance is not None and balance is not None:
                    is_credit = balance > last_balance
                elif re.search(r"\b(CR|CREDIT|DEPOSIT|RECEIVED|REFUND|SALARY|REVERSAL)\b", tail):
                    is_credit = True
                else:
                    is_credit = False
                credit, debit = (amt, None) if is_credit else (None, amt)
        amt = debit or credit
        if amt and balance is not None and last_balance is not None and abs(abs(balance - last_balance) - amt) < Decimal("0.01"):
            # The balance moved by exactly this amount: its direction is the truth, whatever the columns suggested.
            debit, credit = (None, amt) if balance > last_balance else (amt, None)
        if balance is not None:
            last_balance = balance
        text = re.sub(r"\s+", " ", " ".join(desc)).strip()
        if (debit or credit) and text:
            out.append((d, text, debit or Decimal("0"), credit or Decimal("0"), balance))
        else:
            skip[0] += 1
        current = None

    for lines in pages:
        for line in lines:
            ws = line["words"]
            h = _header(line)
            if h is not None:
                finish()
                if h.get("debit") or h.get("credit"):
                    cols = h
                continue
            lead = 0
            while lead < min(2, len(ws) - 1) and re.fullmatch(r"\d{1,4}\.?", ws[lead]["text"]) and not DATE_START.match(ws[lead]["text"]):
                lead += 1  # "1  01/11/2026 …": a serial number before the date
            ws = ws[lead:] if lead and DATE_START.match(ws[lead]["text"]) else ws
            first = ws[0]["text"]
            d = _to_date(first) if DATE_START.match(first) else None
            if d is None and len(ws) >= 3 and re.match(r"^\d{1,2}$", first):  # "01 Nov 2026" split into words
                d = _to_date(" ".join(w["text"] for w in ws[:3]).replace(" ", "-"))
                if d is not None:
                    ws = [dict(ws[0], text="x")] + ws[3:]
            low = " ".join(w["text"] for w in ws).lower()
            if d is not None:
                finish()
                rest = ws[1:]
                desc = [w["text"] for w in rest if not MONEY.match(w["text"]) and not DATE_START.match(w["text"])
                        and w["text"].lower() not in ("cr", "dr")]
                amounts = [w for w in rest if MONEY.match(w["text"])]
                current = [d, desc, amounts]
            elif current is not None:
                if any(k in low for k in ("opening balance", "closing balance", "page ", "statement summary", "total")):
                    finish()
                    continue
                current[1].extend(w["text"] for w in ws if not MONEY.match(w["text"]))
                current[2].extend(w for w in ws if MONEY.match(w["text"]))
            elif "opening balance" in low:
                nums = [_num(w["text"]) for w in ws if MONEY.match(w["text"])]
                if nums and nums[-1] is not None:
                    last_balance = nums[-1]
    finish()
    skipped = skip[0]
    if not out:
        raise ApiError("No payments found in this PDF. If it's a scan or a credit card statement, try the CSV/Excel "
                       "download from net banking instead.")
    return out, skipped


def to_rows(data, password=None, max_rows=3000):
    """Same row format as the CSV import preview."""
    from upi_parse import parse_narration

    items, skipped = extract(data, password)
    rows = []
    for d, text, debit, credit, balance in items[:max_rows]:
        direction = "debit" if debit > 0 else "credit"
        t = parse_narration(text, debit if debit > 0 else credit, direction, d)
        rows.append({
            "date": d.isoformat(), "kind": "expense" if direction == "debit" else "income",
            "amount": float(t.amount), "category": t.category, "note": t.merchant or text[:40],
            "raw": text[:120], "auto": t.category_confidence >= 0.7,
            "balance": float(balance) if balance is not None else None, "ref": t.reference,
        })
    return rows, skipped
