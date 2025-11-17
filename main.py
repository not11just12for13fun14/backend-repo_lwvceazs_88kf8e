from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests
import re

# Load environment variables from a local .env file (dev/previews)
load_dotenv()

app = FastAPI(title="Blovi API")

# CORS: be permissive to avoid frontend preview issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Target email can be configured via env
TARGET_EMAIL = (
    os.getenv("CONTACT_TARGET_EMAIL")
    or os.getenv("RECEIVER_EMAIL")
    or os.getenv("TARGET_EMAIL")
    or "founders@blovi.ai"
)

class ContactEmailRequest(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None  # where it came from (e.g., button or modal)


def resolve_smtp_config():
    # Primary: explicit SMTP_* envs
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # Fallback: Gmail specific envs
    if not (smtp_host and smtp_user and smtp_pass):
        gmail_user = os.getenv("GMAIL_USER") or os.getenv("GOOGLE_GMAIL_USER")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GOOGLE_GMAIL_APP_PASSWORD")
        if gmail_user and gmail_pass:
            # Normalize Gmail app password (Google shows it with spaces)
            gmail_pass = re.sub(r"\s+", "", gmail_pass)
            smtp_host = "smtp.gmail.com"
            smtp_port = 587
            smtp_user = gmail_user
            smtp_pass = gmail_pass

    if not (smtp_host and smtp_user and smtp_pass):
        return None

    from_name = os.getenv("FROM_NAME", "Blovi Site")
    from_email = os.getenv("FROM_EMAIL", smtp_user if smtp_user else "no-reply@blovi.ai")
    return {
        "host": smtp_host,
        "port": smtp_port,
        "user": smtp_user,
        "pass": smtp_pass,
        "from_name": from_name,
        "from_email": from_email,
    }


def send_via_smtp(subject: str, html_body: str) -> None:
    cfg = resolve_smtp_config()
    if not cfg:
        raise RuntimeError(
            "Email service not configured: set SMTP_HOST, SMTP_USER, SMTP_PASS (or GMAIL_USER + GMAIL_APP_PASSWORD)"
        )

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = TARGET_EMAIL

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
        server.starttls()
        server.login(cfg["user"], cfg["pass"])
        server.sendmail(cfg["from_email"], [TARGET_EMAIL], msg.as_string())


def send_via_mailgun(subject: str, html_body: str) -> bool:
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    from_name = os.getenv("FROM_NAME", "Blovi Site")
    from_email = os.getenv("FROM_EMAIL") or f"no-reply@{domain}" if domain else None

    if not (api_key and domain and from_email):
        return False

    url = f"https://api.mailgun.net/v3/{domain}/messages"
    data = {
        "from": f"{from_name} <{from_email}>",
        "to": [TARGET_EMAIL],
        "subject": subject,
        "html": html_body,
    }
    try:
        r = requests.post(url, auth=("api", api_key), data=data, timeout=20)
        r.raise_for_status()
        return True
    except Exception:
        return False


@app.get("/test")
async def test():
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "target_email": TARGET_EMAIL,
    }


@app.post("/contact/email")
async def contact_email(payload: ContactEmailRequest):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    subject = "New Blovi contact request"

    details = []
    if payload.name:
        details.append(f"<b>Name:</b> {payload.name}")
    if payload.company:
        details.append(f"<b>Company:</b> {payload.company}")
    if payload.email:
        details.append(f"<b>Email:</b> {payload.email}")
    if payload.phone:
        details.append(f"<b>Phone:</b> {payload.phone}")
    if payload.source:
        details.append(f"<b>Source:</b> {payload.source}")

    message_html = payload.message or ""

    html_body = f"""
    <div style='font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5;'>
      <h2 style='margin:0 0 8px'>New contact from Blovi site</h2>
      <p style='margin:0 0 12px;color:#334155'>Received at {ts}</p>
      {'<p style="margin:0 0 12px">' + '<br/>'.join(details) + '</p>' if details else ''}
      {'<div style="padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0"><b>Message</b><br/>' + message_html + '</div>' if message_html else ''}
    </div>
    """

    # Try SMTP first, then Mailgun as fallback if configured
    try:
        send_via_smtp(subject, html_body)
        return {"ok": True}
    except Exception as smtp_err:
        # Attempt Mailgun if available
        if send_via_mailgun(subject, html_body):
            return {"ok": True, "via": "mailgun"}
        # As a last resort in dev, fail clearly
        raise HTTPException(status_code=500, detail=f"Email send failed: {smtp_err}")
