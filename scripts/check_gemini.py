"""Check that the Gemini key works on this server.   Run:  python scripts/check_gemini.py"""
import os
import sys

from dotenv import load_dotenv

for f in (".env", "flux.env", os.path.expanduser("~/.env"), os.path.expanduser("~/flux.env")):
    if os.path.exists(f):
        load_dotenv(f)
        print("settings file:", os.path.abspath(f))
        break

key = os.environ.get("GEMINI_API_KEY", "").strip()
model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
if not key:
    sys.exit("PROBLEM: GEMINI_API_KEY is empty or missing in your settings file.")
print("key found, starts with:", key[:3], "... length", len(key))
try:
    from google import genai
except Exception as e:
    sys.exit(f"PROBLEM: google-genai library not installed in this virtualenv: {e}")
try:
    r = genai.Client(api_key=key).models.generate_content(model=model, contents="Reply with the single word: working")
    print("GEMINI OK ->", (r.text or "").strip()[:80])
except Exception as e:
    print("PROBLEM calling Gemini:", type(e).__name__, str(e)[:400])
