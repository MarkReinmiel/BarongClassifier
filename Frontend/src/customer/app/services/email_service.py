"""Email delivery for verification codes (Resend HTTP API or SMTP)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx
from flask import current_app

logger = logging.getLogger("customer.email")


class EmailDeliveryError(RuntimeError):
    pass


def _html(app_name: str, code: str, purpose: str, hours: int) -> str:
    reason = (
        "finish creating your BarongClassifier account"
        if purpose == "registration"
        else "confirm a sign-in from a new browser"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><body style="margin:0;padding:0;background:#E5DED4;font-family:Georgia,serif;color:#2F323A;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;background:#fff;border-radius:16px;padding:32px 28px;border:1px solid #D5CBD2;">
<tr><td>
<p style="margin:0 0 8px;letter-spacing:.08em;font-size:13px;color:#77567A;">{app_name}</p>
<h1 style="margin:0 0 12px;font-size:28px;">Verify your email</h1>
<p style="margin:0 0 20px;font-size:16px;line-height:1.5;">Use this code to {reason}. It expires in {hours} hours.</p>
<p style="margin:0 0 20px;font-size:32px;letter-spacing:8px;font-weight:700;">{code}</p>
<p style="margin:0 0 8px;font-size:14px;">Do not share this code with anyone.</p>
<p style="margin:0;font-size:14px;">If you did not request this email, you can ignore it.</p>
</td></tr></table>
</td></tr></table>
</body></html>"""


def _send_via_resend(
    *,
    api_key: str,
    from_addr: str,
    from_name: str,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    payload = {
        "from": f"{from_name} <{from_addr}>",
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except Exception as error:
        logger.warning("Resend request failed (%s): %s", type(error).__name__, error)
        raise EmailDeliveryError(
            "Verification email could not be sent via Resend. Check RESEND_API_KEY."
        ) from error

    if response.status_code >= 400:
        logger.warning("Resend rejected email status=%s body=%s", response.status_code, response.text[:300])
        raise EmailDeliveryError(
            "Verification email could not be sent via Resend. Check RESEND_API_KEY and MAIL_FROM_ADDRESS."
        )


def _send_via_smtp(message: EmailMessage) -> None:
    cfg = current_app.config
    password = str(cfg.get("MAIL_PASSWORD") or "").strip().strip("\"'").replace(" ", "")
    username = str(cfg.get("MAIL_USERNAME") or "").strip()
    host = str(cfg.get("MAIL_HOST") or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
    # Keep well under gunicorn's default 30s worker timeout so SMTP hangs
    # become a friendly flash instead of Render's bare "Internal Server Error".
    timeout = int(cfg.get("MAIL_TIMEOUT_SECONDS") or 12)

    try:
        if cfg.get("MAIL_USE_SSL") or port == 465:
            with smtplib.SMTP_SSL(
                host,
                port,
                timeout=timeout,
                context=ssl.create_default_context(),
            ) as server:
                server.login(username, password)
                server.send_message(message)
            return

        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if cfg.get("MAIL_USE_TLS", True):
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException, TimeoutError) as error:
        logger.warning(
            "Verification email could not be sent (%s): %s",
            type(error).__name__,
            error,
        )
        raise EmailDeliveryError(
            "Verification email could not be sent. Render free plans block Gmail SMTP — "
            "add RESEND_API_KEY in Render (https://resend.com), or set "
            "EMAIL_VERIFICATION_ENABLED=false temporarily."
        ) from error


def send_verification_email(recipient: str, code: str, purpose: str = "registration") -> None:
    cfg = current_app.config
    resend_key = str(cfg.get("RESEND_API_KEY") or "").strip()
    from_addr = str(cfg.get("MAIL_FROM_ADDRESS") or cfg.get("MAIL_USERNAME") or "").strip()
    from_name = str(cfg.get("MAIL_FROM_NAME") or cfg.get("APP_NAME") or "BarongClassifier").strip()

    if not resend_key:
        missing = [
            name
            for name, value in {
                "MAIL_HOST": cfg.get("MAIL_HOST"),
                "MAIL_USERNAME": cfg.get("MAIL_USERNAME"),
                "MAIL_PASSWORD": cfg.get("MAIL_PASSWORD"),
                "MAIL_FROM_ADDRESS": from_addr,
            }.items()
            if not value
        ]
        if missing:
            raise EmailDeliveryError("Email delivery is not configured.")

    if not from_addr:
        raise EmailDeliveryError("Email delivery is not configured.")

    hours = max(1, int(cfg["EMAIL_VERIFICATION_EXPIRE_MINUTES"]) // 60)
    app_name = cfg["APP_NAME"]
    subject = f"{app_name} verification code"
    text_body = (
        f"Your {app_name} verification code is {code}. "
        f"It expires in {hours} hours. Do not share this code. "
        "If you did not request it, ignore this email."
    )
    html_body = _html(app_name, code, purpose, hours)

    # Prefer Resend HTTPS on hosts that block outbound SMTP (common on Render).
    if resend_key:
        _send_via_resend(
            api_key=resend_key,
            from_addr=from_addr,
            from_name=from_name,
            recipient=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_addr}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    _send_via_smtp(message)
