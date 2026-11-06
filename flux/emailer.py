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
            '<div style="font-size:34px;font-weight:800;letter-spacing:8px;color:#245C43;'
            'background:#ffffff;border:1px solid #e4e2dc;border-radius:14px;padding:18px 24px;'
            f'display:inline-block;margin:8px 0 24px">{html.escape(code)}</div>'
        )
    # Text logo, so it shows even when the email app blocks images.
    return f"""<!doctype html><html><body style="margin:0;background:#f6f4ef;font-family:Inter,-apple-system,Segoe UI,Roboto,sans-serif;color:#1c1b22">
<div style="max-width:480px;margin:0 auto;padding:40px 24px;text-align:center">
<div style="font-size:30px;font-weight:800;letter-spacing:-1px;color:#1c1b22;margin:0 0 4px">kitna<span style="color:#f2a93b">.</span></div>
<div style="font-size:13px;font-weight:700;color:#245C43;margin:0 0 28px">Pehle Kitna, phir kharcha.</div>
<h1 style="font-size:20px;margin:0 0 12px">{html.escape(title)}</h1>
{code_block}
<div style="font-size:14px;line-height:1.6;color:#55545e">{body_html}</div>
<p style="font-size:11px;color:#8a8992;margin-top:32px">Kitna · Know before you spend. Kitna never asks for your bank password or UPI PIN.</p>
</div></body></html>"""


def send_email(to, subject, text, html_body):
    cfg = current_app.config
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
    except Exception:  # never leak SMTP details to the user
        log.exception("Failed to send email to %s", to)
        return False


def send_otp(to, code, minutes):
    body = f"Enter this code to sign in. It expires in {minutes} minutes.<br>If you didn't ask for it, you can ignore this email."
    return send_email(to, "Your Kitna sign-in code", f"Your Kitna code is {code}. It expires in {minutes} minutes.",
                      _template("Your sign-in code", body, code))
