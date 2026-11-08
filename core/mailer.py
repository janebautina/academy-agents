"""Send an email. Resend (HTTPS API) when RESEND_API_KEY is set, otherwise plain SMTP.

.env:
    MAIL_FROM=Alesha AI Academy <support@aleshaai.com>
    RESEND_API_KEY=re_...                      # or SMTP_HOST / SMTP_USER / SMTP_PASSWORD (port 465)
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from core import env


class MailError(RuntimeError):
    pass


def send(to: str, subject: str, text: str, html: str = "", reply_to: str = "") -> str:
    sender = env.need("MAIL_FROM")
    if env.get("RESEND_API_KEY"):
        body = {"from": sender, "to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        if reply_to:
            body["reply_to"] = reply_to
        request = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {env.get('RESEND_API_KEY')}", "Content-Type": "application/json",
            "User-Agent": "academy-agents"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response).get("id", "")
        except urllib.error.HTTPError as e:
            raise MailError(f"Resend {e.code}: {e.read().decode()[:200]}") from None
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(env.need("SMTP_HOST"), int(env.get("SMTP_PORT", "465")), context=ssl.create_default_context()) as s:
        s.login(env.need("SMTP_USER"), env.need("SMTP_PASSWORD"))
        s.send_message(msg)
    return "smtp"
