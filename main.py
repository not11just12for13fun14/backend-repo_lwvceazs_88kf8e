from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone

app = FastAPI(title="Blovi API")

# CORS: allow frontend origin if provided; otherwise allow all for dev
frontend_url = os.getenv("FRONTEND_URL")
origins = [frontend_url] if frontend_url else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
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


def send_email(subject: str, html_body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_name = os.getenv("FROM_NAME", "Blovi Site")
    from_email = os.getenv("FROM_EMAIL", smtp_user or "no-reply@blovi.ai")

    if not smtp_host or not smtp_user or not smtp_pass:
        # If SMTP not configured, we silently skip actual sending in this environment
        # but do not error to keep UX smooth. In prod, set SMTP_* env vars.
        return

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = TARGET_EMAIL

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [TARGET_EMAIL], msg.as_string())


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
