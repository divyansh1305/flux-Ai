"""Command line:  upi-parse "Rs.250 debited from A/c XX1234 to VPA swiggy@icici"   (or pipe text in)."""
import json
import sys

from . import parse_sms, split_messages


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = " ".join(argv) if argv else sys.stdin.read()
    results = []
    for msg in split_messages(text):
        tx = parse_sms(msg)
        results.append(tx.to_dict() if tx else {"ignored": msg[:80]})
    json.dump(results if len(results) != 1 else results[0], sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
