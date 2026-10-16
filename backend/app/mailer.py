"""
Email notifications for contact-form leads.

When a visitor submits the contact form, two emails are sent:

    1. A confirmation to the visitor (their reference number + what happens next)
    2. A notification to Terragni's team (all details + the Solution Mapper context)

Settings come from backend/.env. If SMTP_HOST is empty, nothing is sent and the
lead is still saved in backend/data/leads/leads.jsonl.

    SMTP_HOST=smtp.office365.com      (or smtp.gmail.com, etc.)
    SMTP_PORT=587
    SMTP_USER=engage@terragni.co
    SMTP_PASSWORD=app-password
    SMTP_FROM=Terragni Consulting <engage@terragni.co>
    LEAD_NOTIFY_TO=engage@terragni.co
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

logger = logging.getLogger(__name__)


def _setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def email_enabled() -> bool:
    return bool(_setting("SMTP_HOST"))


def _send(message: EmailMessage) -> None:
    host = _setting("SMTP_HOST")
    port = int(_setting("SMTP_PORT", "587") or 587)
    user = _setting("SMTP_USER")
    password = _setting("SMTP_PASSWORD")
    context = ssl.create_default_context()

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.starttls(context=context)

    with server:
        if user:
            server.login(user, password)
        server.send_message(message)


def _wrap(title: str, body_html: str) -> str:
    return f"""\
<!doctype html>
<html><body style="margin:0;background:#f7f2e9;font-family:Montserrat,Segoe UI,Arial,sans-serif;color:#261c3b">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 12px">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border-radius:18px;overflow:hidden">
        <tr><td style="background:#2f2557;padding:28px 32px;color:#ffffff">
          <div style="font-size:12px;letter-spacing:3px;color:#c69b45;font-weight:700">TERRAGNI CONSULTING</div>
          <div style="font-size:22px;font-weight:700;margin-top:8px">{html.escape(title)}</div>
        </td></tr>
        <tr><td style="padding:28px 32px;font-size:15px;line-height:1.65">{body_html}</td></tr>
        <tr><td style="padding:18px 32px;background:#f4effb;font-size:12px;color:#6b6680">
          Terragni Consulting &middot; the Human Engagement company &middot;
          engage@terragni.co &middot; +91 895 698 2522
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _visitor_email(lead: dict[str, Any]) -> EmailMessage:
    name = lead.get("name") or "there"
    reference = lead["reference"]
    question = (lead.get("context") or {}).get("question", "")

    question_html = (
        f'<p style="margin:18px 0;padding:14px 16px;border-left:4px solid #c69b45;'
        f'background:#f4effb;border-radius:0 10px 10px 0">'
        f"<b>What you shared:</b><br>{html.escape(question)}</p>"
        if question else ""
    )

    body = f"""
      <p>Hi {html.escape(name)},</p>
      <p>Thank you for reaching out to Terragni. We have received your enquiry.</p>
      <p style="font-size:13px;color:#6b6680;margin-bottom:4px">YOUR REFERENCE</p>
      <p style="font-size:22px;font-weight:700;color:#5f4a9e;margin-top:0">{html.escape(reference)}</p>
      {question_html}
      <p><b>What happens next</b></p>
      <ol style="padding-left:18px">
        <li>We read your context, including anything you explored in the Solution Mapper.</li>
        <li>A Terragni consultant contacts you, usually within 2 working days.</li>
        <li>We explore together where behaviour can shift and how business can move.</li>
      </ol>
      <p>If you want to add anything, just reply to this email and quote your reference.</p>
      <p>Warm regards,<br><b>Team Terragni</b></p>
    """

    message = EmailMessage()
    message["Subject"] = f"We received your enquiry ({reference}) | Terragni Consulting"
    message["From"] = _setting("SMTP_FROM") or _setting("SMTP_USER")
    message["To"] = lead["email"]
    reply_to = _setting("LEAD_NOTIFY_TO")
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(
        f"Hi {name},\n\nThank you for reaching out to Terragni. Your reference is "
        f"{reference}.\nA Terragni consultant will contact you, usually within 2 "
        "working days.\n\nTeam Terragni\nengage@terragni.co"
    )
    message.add_alternative(_wrap("We received your enquiry", body), subtype="html")
    return message


def _team_email(lead: dict[str, Any]) -> EmailMessage:
    context = lead.get("context") or {}
    rows = [
        ("Reference", lead.get("reference")),
        ("Name", lead.get("name")),
        ("Email", lead.get("email")),
        ("Organisation", lead.get("organisation")),
        ("Phone", lead.get("phone")),
        ("Message", lead.get("message")),
        ("Role", context.get("role")),
        ("Industry", context.get("industry")),
        ("Path", context.get("path")),
        ("Question", context.get("question")),
        ("Diagnosed problem", context.get("summary")),
        ("Suggested services", ", ".join(context.get("suggested_services") or [])),
    ]
    table = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#6b6680;vertical-align:top;white-space:nowrap">{html.escape(k)}</td>'
        f'<td style="padding:6px 0">{html.escape(str(v))}</td></tr>'
        for k, v in rows if v
    )

    message = EmailMessage()
    message["Subject"] = f"New Solution Mapper lead {lead.get('reference')}: {lead.get('name')}"
    message["From"] = _setting("SMTP_FROM") or _setting("SMTP_USER")
    message["To"] = _setting("LEAD_NOTIFY_TO")
    message["Reply-To"] = lead["email"]
    message.set_content("\n".join(f"{k}: {v}" for k, v in rows if v))
    message.add_alternative(
        _wrap("New lead from the Solution Mapper", f'<table style="font-size:14px">{table}</table>'),
        subtype="html",
    )
    return message


def _deliver(lead: dict[str, Any]) -> None:
    try:
        _send(_visitor_email(lead))
    except Exception:
        logger.exception("Could not send confirmation email for %s", lead.get("reference"))

    if parseaddr(_setting("LEAD_NOTIFY_TO"))[1]:
        try:
            _send(_team_email(lead))
        except Exception:
            logger.exception("Could not send team notification for %s", lead.get("reference"))


def send_lead_emails(lead: dict[str, Any]) -> bool:
    """Send both emails in the background. Returns True when email is set up."""
    if not email_enabled():
        return False
    threading.Thread(target=_deliver, args=(lead,), daemon=True).start()
    return True
