from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone

app = FastAPI(title="Blovi API")

# CORS: prefer explicit production domains but allow all in dev/previews
allowed_origins: List[str] = [
    os.getenv("FRONTEND_URL") or "",
    "https://blovi.ai",
    "https://www.blovi.ai",
]
# Always include wildcard for previews/dev unless explicitly disabled
if os.getenv("ALLOW_ALL_CORS", "1") == "1":
    allowed_origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in allowed_origins if o],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TARGET_EMAIL = "juliustuokila649@gmail.com"

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


def send_email(subject: str, html_body: str) -> None:
    cfg = resolve_smtp_config()
    if not cfg:
        raise RuntimeError("Email service not configured: set SMTP_HOST, SMTP_USER, SMTP_PASS (or GMAIL_USER + GMAIL_APP_PASSWORD)")

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = TARGET_EMAIL

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
        server.starttls()
        server.login(cfg["user"], cfg["pass"])
        server.sendmail(cfg["from_email"], [TARGET_EMAIL], msg.as_string())


@app.get("/test")
async def test():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.post("/contact/email")
async def contact_email(payload: ContactEmailRequest):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    subject = "New Blovi contact request"

    details = []
    if payload.name: details.append(f"<b>Name:</b> {payload.name}")
    if payload.company: details.append(f"<b>Company:</b> {payload.company}")
    if payload.email: details.append(f"<b>Email:</b> {payload.email}")
    if payload.phone: details.append(f"<b>Phone:</b> {payload.phone}")
    if payload.source: details.append(f"<b>Source:</b> {payload.source}")

    message_html = payload.message or ""

    html_body = f"""
    <div style='font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5;'>
      <h2 style='margin:0 0 8px'>New contact from Blovi site</h2>
      <p style='margin:0 0 12px;color:#334155'>Received at {ts}</p>
      {'<p style="margin:0 0 12px">' + '<br/>'.join(details) + '</p>' if details else ''}
      {'<div style="padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0"><b>Message</b><br/>' + message_html + '</div>' if message_html else ''}
    </div>
    """

    try:
      send_email(subject, html_body)
      return {"ok": True}
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
