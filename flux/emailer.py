"""Outgoing email (OTP codes, login alerts). One template, no copy-paste."""
import html
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger("flux.mail")


def _template(title, body_html, code=None):
    code_block = ""
    if code:
        code_block = (
            '<div style="font-size:34px;font-weight:800;letter-spacing:8px;color:#1F5BD6;'
            'background:#ffffff;border:1px solid #e4e2dc;border-radius:14px;padding:18px 24px;'
            f'display:inline-block;margin:8px 0 24px">{html.escape(code)}</div>'
        )
    # Text logo, so it shows even when the email app blocks images.
    return f"""<!doctype html><html><body style="margin:0;background:#f6f4ef;font-family:Inter,-apple-system,Segoe UI,Roboto,sans-serif;color:#1c1b22">
<div style="max-width:480px;margin:0 auto;padding:40px 24px;text-align:center">
<div style="font-size:30px;font-weight:800;letter-spacing:-1px;color:#1c1b22;margin:0 0 4px">kitna<span style="color:#f2a93b">.</span></div>
<div style="font-size:13px;font-weight:700;color:#1F5BD6;margin:0 0 28px">Pehle Kitna, phir kharcha.</div>
<h1 style="font-size:20px;margin:0 0 12px">{html.escape(title)}</h1>
{code_block}
<div style="font-size:14px;line-height:1.6;color:#55545e">{body_html}</div>
<p style="font-size:11px;color:#8a8992;margin-top:32px">Kitna · Know before you spend. Kitna never asks for your bank password or UPI PIN.</p>
</div></body></html>"""


def _send_brevo(key, sender, to, subject, text, html_body):
    """Send through Brevo's HTTPS API (works from Vercel, where Gmail often refuses SMTP logins)."""
    import requests

    try:
        r = requests.post("https://api.brevo.com/v3/smtp/email", timeout=15,
                          headers={"api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
                          json={"sender": {"name": "Kitna", "email": sender}, "to": [{"email": to}],
                                "subject": subject, "htmlContent": html_body, "textContent": text})
        if r.status_code in (200, 201, 202):
            return True
        log.error("Brevo refused the email to %s: HTTP %s %s (key starts like a Brevo API key: %s, %d chars)", to,
                  r.status_code, r.text[:200], key.startswith("xkeysib-"), len(key))
    except Exception:  # noqa: BLE001
        log.exception("Brevo request failed for %s", to)
    return False


def send_email(to, subject, text, html_body):
    cfg = current_app.config
    if cfg.get("BREVO_API_KEY") and cfg["MAIL_SENDER"]:
        return _send_brevo(cfg["BREVO_API_KEY"], cfg["MAIL_SENDER"], to, subject, text, html_body)
    if not (cfg["MAIL_SENDER"] and cfg["MAIL_PASSWORD"]):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Kitna <{cfg['MAIL_SENDER']}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP_SSL(cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=15) as s:
            s.login(cfg["MAIL_SENDER"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("Email login refused: check EMAIL_SENDER and that EMAIL_PASSWORD is a Gmail App Password for it")
        return False
    except Exception:  # noqa: BLE001  try the other Gmail port once (some networks drop 465)
        log.exception("Sending on port %s failed; trying 587 with STARTTLS", cfg["MAIL_PORT"])
    try:
        with smtplib.SMTP(cfg["MAIL_HOST"], 587, timeout=15) as s:
            s.starttls()
            s.login(cfg["MAIL_SENDER"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception:  # never leak SMTP details to the user
        pw, sender = cfg["MAIL_PASSWORD"], cfg["MAIL_SENDER"]
        # Shape only, never the value: tells the owner whether the pasted settings look right.
        log.exception("Failed to send email to %s (sender looks like a Gmail address: %s; password is %d chars, "
                      "16 letters like a Gmail App Password: %s)", to, sender.lower().endswith("@gmail.com"), len(pw),
                      len(pw) == 16 and pw.isalpha())
        return False


def send_otp(to, code, minutes):
    body = f"Enter this code to sign in. It expires in {minutes} minutes.<br>If you didn't ask for it, you can ignore this email."
    return send_email(to, "Your Kitna sign-in code", f"Your Kitna code is {code}. It expires in {minutes} minutes.",
                      _template("Your sign-in code", body, code))
