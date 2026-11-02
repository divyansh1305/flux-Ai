"""Measure upi-parse on a labelled JSONL file.

    python benchmarks/evaluate.py benchmarks/synthetic_v1.jsonl
    python benchmarks/evaluate.py my_real_labelled.jsonl --errors 20

Reports detection precision/recall (is it a transaction?), and field accuracy on true
transactions: direction, amount, merchant, category, reference, balance; plus throughput.
"""
import argparse
import json
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from upi_parse import parse_narration, parse_notification, parse_sms  # noqa: E402


def run(row):
    k = row["kind"]
    if k == "sms":
        return parse_sms(row["text"])
    if k == "notification":
        return parse_notification(row.get("title", ""), row.get("body", ""), row.get("package", ""))
    return parse_narration(row["narration"], row["amount"], row["direction"])


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--errors", type=int, default=0, help="print N example mistakes per field")
    args = ap.parse_args()
    rows = [json.loads(l) for l in Path(args.path).read_text(encoding="utf-8").splitlines() if l.strip()]

    t0 = time.perf_counter()
    preds = [run(r) for r in rows]
    elapsed = time.perf_counter() - t0

    tp = fp = fn = tn = 0
    fields = Counter()
    totals = Counter()
    errors = {k: [] for k in ("detect", "direction", "amount", "merchant", "category", "reference", "balance")}
    by_kind = Counter()
    for r, p in zip(rows, preds):
        lab = r["label"]
        is_txn = lab["is_txn"]
        if is_txn and p:
            tp += 1
        elif is_txn and not p:
            fn += 1
            errors["detect"].append(("missed", r))
        elif not is_txn and p:
            fp += 1
            errors["detect"].append(("false alarm", r))
        else:
            tn += 1
        if not (is_txn and p):
            continue
        by_kind[r["kind"]] += 1
        checks = {
            "direction": p.direction == lab["direction"],
            "amount": p.amount == Decimal(str(lab["amount"])).quantize(Decimal("0.01")),
            "category": p.category == lab["category"],
        }
        if lab.get("merchant"):
            checks["merchant"] = norm(lab["merchant"]) in norm(p.merchant) or norm(p.merchant) in norm(lab["merchant"]) and len(norm(p.merchant)) >= 3
        if lab.get("reference"):
            checks["reference"] = p.reference == lab["reference"]
        if lab.get("balance") is not None:
            checks["balance"] = p.balance == Decimal(str(lab["balance"])).quantize(Decimal("0.01"))
        for k, ok in checks.items():
            totals[k] += 1
            fields[k] += ok
            if not ok:
                errors[k].append((getattr(p, k, None), r))

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    print(f"Dataset: {args.path}  ({len(rows)} rows)")
    print(f"Detection   precision {precision:.1%}  recall {recall:.1%}   (tp={tp} fp={fp} fn={fn} tn={tn})")
    for k in ("direction", "amount", "merchant", "category", "reference", "balance"):
        if totals[k]:
            print(f"{k:<11} {fields[k] / totals[k]:.1%}  ({fields[k]}/{totals[k]})")
    print(f"Throughput  {len(rows) / elapsed:,.0f} messages/sec  ({elapsed * 1000 / len(rows):.3f} ms each)")
    if args.errors:
        for k, errs in errors.items():
            for got, r in errs[: args.errors]:
                print(f"\n[{k}] got={got!r}\n  label={r['label']}\n  input={r.get('text') or r.get('title', '') + ' | ' + r.get('body', '') or r.get('narration')}")


if __name__ == "__main__":
    main()
