"""SMTP delivery for verification codes."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

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


def send_verification_email(recipient: str, code: str, purpose: str = "registration") -> None:
    cfg = current_app.config
    missing = [
        name
        for name, value in {
            "MAIL_HOST": cfg.get("MAIL_HOST"),
            "MAIL_USERNAME": cfg.get("MAIL_USERNAME"),
            "MAIL_PASSWORD": cfg.get("MAIL_PASSWORD"),
            "MAIL_FROM_ADDRESS": cfg.get("MAIL_FROM_ADDRESS"),
        }.items()
        if not value
    ]
    if missing:
        raise EmailDeliveryError("Email delivery is not configured.")

    hours = max(1, int(cfg["EMAIL_VERIFICATION_EXPIRE_MINUTES"]) // 60)
    app_name = cfg["APP_NAME"]
    message = EmailMessage()
    message["Subject"] = f"{app_name} verification code"
    message["From"] = f"{cfg['MAIL_FROM_NAME']} <{cfg['MAIL_FROM_ADDRESS']}>"
    message["To"] = recipient
    message.set_content(
        f"Your {app_name} verification code is {code}. "
        f"It expires in {hours} hours. Do not share this code. "
        "If you did not request it, ignore this email."
    )
    message.add_alternative(_html(app_name, code, purpose, hours), subtype="html")

    password = str(cfg.get("MAIL_PASSWORD") or "").strip().strip("\"'").replace(" ", "")
    username = str(cfg.get("MAIL_USERNAME") or "").strip()
    host = str(cfg.get("MAIL_HOST") or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)

    try:
        if cfg.get("MAIL_USE_SSL"):
            with smtplib.SMTP_SSL(
                host,
                port,
                timeout=30,
                context=ssl.create_default_context(),
            ) as server:
                server.login(username, password)
                server.send_message(message)
            return

        with smtplib.SMTP(host, port, timeout=30) as server:
            if cfg.get("MAIL_USE_TLS", True):
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        logger.warning(
            "Verification email could not be sent (%s): %s",
            type(error).__name__,
            error,
        )
        raise EmailDeliveryError("The verification email could not be sent.") from error
