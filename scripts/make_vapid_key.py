"""Print a new VAPID_PRIVATE_KEY for reminders (Web Push). Run once, put the value in Vercel's
Environment Variables, and never change it (changing it means everyone has to turn reminders on again)."""
import base64

from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP256R1())
raw = key.private_numbers().private_value.to_bytes(32, "big")
print(base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
