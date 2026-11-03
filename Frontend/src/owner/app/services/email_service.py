"""Email delivery for Owner verification and password notices (Resend or SMTP)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx
from flask import current_app

logger = logging.getLogger("owner.email")


class EmailDeliveryError(RuntimeError):
    pass


def _purpose_copy(purpose: str) -> tuple[str, str]:
    if purpose == "password_reset":
        return (
            "reset your Owner Portal password",
            "Owner password reset code",
        )
    return ("verify your Owner Portal request", "Owner verification code")


def _html(app_name: str, code: str, purpose: str, minutes: int) -> str:
    reason, _ = _purpose_copy(purpose)
    return f"""<!DOCTYPE html>
<html lang="en"><body style="margin:0;padding:0;background:#F4F1EA;font-family:Georgia,serif;color:#2C2A26;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" style="max-width:520px;background:#fff;border-radius:16px;padding:32px 28px;border:1px solid #E0D8C8;">
<tr><td>
<p style="margin:0 0 8px;letter-spacing:.08em;font-size:13px;color:#9A7B4F;">{app_name} Owner</p>
<h1 style="margin:0 0 12px;font-size:28px;">Verification code</h1>
<p style="margin:0 0 20px;font-size:16px;line-height:1.5;">Use this code to {reason}. It expires in {minutes} minutes.</p>
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
        raise EmailDeliveryError("The email could not be sent.") from error

    if response.status_code >= 400:
        logger.warning("Resend rejected email status=%s body=%s", response.status_code, response.text[:300])
        raise EmailDeliveryError("The email could not be sent.")


def _send_via_smtp(message: EmailMessage) -> None:
    cfg = current_app.config
    password = str(cfg.get("MAIL_PASSWORD") or "").strip().strip("\"'").replace(" ", "")
    username = str(cfg.get("MAIL_USERNAME") or "").strip()
    host = str(cfg.get("MAIL_HOST") or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
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
            "Email could not be sent (%s): %s",
            type(error).__name__,
            error,
        )
        raise EmailDeliveryError("The email could not be sent.") from error


def _dispatch(message: EmailMessage, *, text_body: str, html_body: str) -> None:
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

    if resend_key:
        _send_via_resend(
            api_key=resend_key,
            from_addr=from_addr,
            from_name=from_name,
            recipient=str(message["To"]),
            subject=str(message["Subject"]),
            text_body=text_body,
            html_body=html_body,
        )
        return

    _send_via_smtp(message)


def send_verification_email(recipient: str, code: str, purpose: str = "password_reset") -> None:
    cfg = current_app.config
    minutes = max(1, int(cfg["EMAIL_VERIFICATION_EXPIRE_MINUTES"]))
    app_name = cfg["APP_NAME"]
    _, subject_tail = _purpose_copy(purpose)
    subject = f"{app_name} {subject_tail}"
    text_body = (
        f"Your {app_name} verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code. "
        "If you did not request it, ignore this email."
    )
    html_body = _html(app_name, code, purpose, minutes)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{cfg['MAIL_FROM_NAME']} <{cfg['MAIL_FROM_ADDRESS']}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    _dispatch(message, text_body=text_body, html_body=html_body)


def send_password_changed_email(recipient: str) -> None:
    cfg = current_app.config
    app_name = cfg["APP_NAME"]
    subject = f"{app_name} password changed"
    text_body = (
        f"Your {app_name} Owner Portal password was changed. "
        "If you did not do this, contact support immediately."
    )
    html_body = f"""<!DOCTYPE html><html><body style="font-family:Georgia,serif;color:#2C2A26;padding:24px;">
<p>Your <strong>{app_name}</strong> Owner Portal password was changed.</p>
<p>If you did not do this, contact support immediately.</p>
</body></html>"""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{cfg['MAIL_FROM_NAME']} <{cfg['MAIL_FROM_ADDRESS']}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    _dispatch(message, text_body=text_body, html_body=html_body)
