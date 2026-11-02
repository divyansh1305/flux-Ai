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
            '<div style="font-size:34px;font-weight:800;letter-spacing:8px;color:#e8491d;'
            'background:#1a1210;border:1px dashed #5a2a1a;border-radius:14px;padding:18px 24px;'
            f'display:inline-block;margin:8px 0 24px">{html.escape(code)}</div>'
        )
    return f"""<!doctype html><html><body style="margin:0;background:#0b0b12;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#f4f4f8">
<div style="max-width:480px;margin:0 auto;padding:40px 24px;text-align:center">
<div style="width:44px;height:44px;line-height:44px;border-radius:12px;background:#e8491d;color:#fff;font-weight:800;margin:0 auto 20px">F</div>
<h1 style="font-size:20px;margin:0 0 12px">{html.escape(title)}</h1>
{code_block}
<div style="font-size:14px;line-height:1.6;color:#a0a0b8">{body_html}</div>
<p style="font-size:11px;color:#60607a;margin-top:32px">Flux · Spend smarter, save automatically</p>
</div></body></html>"""


def send_email(to, subject, text, html_body):
    cfg = current_app.config
    if not (cfg["MAIL_SENDER"] and cfg["MAIL_PASSWORD"]):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Flux <{cfg['MAIL_SENDER']}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP_SSL(cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=15) as s:
            s.login(cfg["MAIL_SENDER"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception:  # never leak SMTP details to the user
        log.exception("Failed to send email to %s", to)
        return False


def send_otp(to, code, minutes):
    body = f"Enter this code to sign in. It expires in {minutes} minutes.<br>If you didn't ask for it, you can ignore this email."
    return send_email(to, "Your Flux sign-in code", f"Your Flux code is {code}. It expires in {minutes} minutes.",
                      _template("Your sign-in code", body, code))
