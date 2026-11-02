import json
from decimal import Decimal

from upi_parse import parse_narration, parse_notification, parse_sms


def evaluate_file(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    tp = fp = fn = 0
    amt_ok = cat_ok = n = 0
    for r in rows:
        if r["kind"] == "sms":
            p = parse_sms(r["text"])
        elif r["kind"] == "notification":
            p = parse_notification(r.get("title", ""), r.get("body", ""), r.get("package", ""))
        else:
            p = parse_narration(r["narration"], r["amount"], r["direction"])
        lab = r["label"]
        if lab["is_txn"] and p:
            tp += 1
            n += 1
            amt_ok += p.amount == Decimal(str(lab["amount"])).quantize(Decimal("0.01"))
            cat_ok += p.category == lab["category"]
        elif lab["is_txn"]:
            fn += 1
        elif p:
            fp += 1
    return {"precision": tp / (tp + fp), "recall": tp / (tp + fn), "amount": amt_ok / n, "category": cat_ok / n}
