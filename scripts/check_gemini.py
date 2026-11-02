"""Check that the Gemini key works on this server.   Run:  python scripts/check_gemini.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

for f in (".env", "flux.env", os.path.expanduser("~/.env"), os.path.expanduser("~/flux.env")):
    if os.path.exists(f):
        load_dotenv(f)
        print("settings file:", os.path.abspath(f))
        break

key = os.environ.get("GEMINI_API_KEY", "").strip()
model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
if not key:
    sys.exit("PROBLEM: GEMINI_API_KEY is empty or missing in your settings file.")
print("key found, starts with:", key[:3], "... length", len(key), "| model:", model)

from flux.ai import call  # noqa: E402

try:
    print("GEMINI OK ->", call(key, model, "Reply with the single word: working")[:80])
except Exception as e:
    print("PROBLEM calling Gemini:", str(e)[:500])
