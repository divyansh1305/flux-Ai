"""Web Push without a third-party push library: VAPID (RFC 8292) + message encryption (RFC 8291 / RFC 8188).

Phones receive these through their own push service: Chrome/Android via fcm.googleapis.com, iPhone (Kitna added to
the Home Screen, iOS 16.4+) via web.push.apple.com, Firefox via push.services.mozilla.com. The message is
encrypted for that one browser, so the push service can't read it.

Keys: one P-256 key pair for the whole server. Set VAPID_PRIVATE_KEY (base64url, 32 bytes) or let Kitna create
instance/vapid_private.key on first use. Changing the key means every phone has to turn reminders on again.
"""
import base64
import json
import logging
import os
import struct
import threading
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger("flux.push")

# Only real push services. Stops anyone using "subscribe" to make the server call an address of their choice.
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", ".push.apple.com", ".push.services.mozilla.com",
              ".notify.windows.com")
RECORD_SIZE = 4096
_lock = threading.Lock()
_key_cache = {}


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text):
    text = str(text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _point(public_key):
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def allowed_endpoint(url):
    try:
        p = urlparse(str(url))
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.port not in (None, 443):
        return False
    return any((host.endswith(h) or host == h[1:]) if h.startswith(".") else host == h for h in PUSH_HOSTS)


# ─── Server key (VAPID) ───────────────────────────────────────
def server_key(instance_dir):
    """The server's private key, from VAPID_PRIVATE_KEY or a file it creates once."""
    env = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    cache_key = env or instance_dir
    if cache_key in _key_cache:
        return _key_cache[cache_key]
    with _lock:
        if env:
            key = ec.derive_private_key(int.from_bytes(unb64u(env), "big"), ec.SECP256R1())
        else:
            path = os.path.join(instance_dir, "vapid_private.key")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    key = serialization.load_pem_private_key(f.read(), password=None)
            else:
                os.makedirs(instance_dir, exist_ok=True)
                key = ec.generate_private_key(ec.SECP256R1())
                pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(pem)
        _key_cache[cache_key] = key
        return key


def public_key_b64(key):
    """What the browser needs as applicationServerKey."""
    return b64u(_point(key.public_key()))


def vapid_headers(endpoint, key, contact="mailto:hello@flux.app", now=None):
    """Authorization header: a short-lived ES256 JWT that proves this server sent the message."""
    p = urlparse(endpoint)
    now = int(now or time.time())
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{p.scheme}://{p.netloc}", "exp": now + 12 * 3600, "sub": contact},
                             separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    token = f"{header}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return {"Authorization": f"vapid t={token}, k={public_key_b64(key)}"}


# ─── Message encryption (aes128gcm) ───────────────────────────
def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(plaintext, p256dh, auth, salt=None, sender_key=None):
    """Encrypt one message for one browser (RFC 8291). Returns the request body."""
    ua_public = unb64u(p256dh) if isinstance(p256dh, str) else p256dh
    auth_secret = unb64u(auth) if isinstance(auth, str) else auth
    if len(ua_public) != 65 or ua_public[0] != 4 or len(auth_secret) != 16:
        raise ValueError("bad subscription keys")
    if len(plaintext) > RECORD_SIZE - 17 - 86:
        raise ValueError("message too long")
    salt = salt or os.urandom(16)
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _point(sender_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)  # 0x02 = last (only) record
    return salt + struct.pack("!IB", RECORD_SIZE, len(as_public)) + as_public + ciphertext


def send(subscription, payload, key, ttl=12 * 3600, urgency="normal", timeout=10, post=None, contact="mailto:hello@flux.app"):
    """POST one encrypted message. Returns the HTTP status (0 = network error). 404/410 = phone unsubscribed."""
    endpoint = subscription["endpoint"]
    if not allowed_endpoint(endpoint):
        return 0
    body = encrypt(json.dumps(payload, ensure_ascii=False).encode(), subscription["p256dh"], subscription["auth"])
    headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(ttl),
               "Urgency": urgency, **vapid_headers(endpoint, key, contact)}
    if post is None:
        import requests

        post = requests.post
    try:
        res = post(endpoint, data=body, headers=headers, timeout=timeout)
        return res.status_code
    except Exception as e:  # noqa: BLE001 - one phone failing must never stop the others
        log.warning("push failed: %s", type(e).__name__)
        return 0
