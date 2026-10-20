"""SMTP delivery for Owner verification and password notices."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

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


def _send(message: EmailMessage) -> None:
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

    try:
        if cfg.get("MAIL_USE_SSL"):
            with smtplib.SMTP_SSL(
                cfg["MAIL_HOST"],
                cfg["MAIL_PORT"],
                timeout=20,
                context=ssl.create_default_context(),
            ) as server:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
                server.send_message(message)
            return

        with smtplib.SMTP(cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=20) as server:
            if cfg.get("MAIL_USE_TLS", True):
                server.starttls(context=ssl.create_default_context())
            server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        logger.warning("Email could not be sent.")
        raise EmailDeliveryError("The email could not be sent.") from error


def send_verification_email(recipient: str, code: str, purpose: str = "password_reset") -> None:
    cfg = current_app.config
    minutes = max(1, int(cfg["EMAIL_VERIFICATION_EXPIRE_MINUTES"]))
    app_name = cfg["APP_NAME"]
    _, subject = _purpose_copy(purpose)
    message = EmailMessage()
    message["Subject"] = f"{app_name} {subject}"
    message["From"] = f"{cfg['MAIL_FROM_NAME']} <{cfg['MAIL_FROM_ADDRESS']}>"
    message["To"] = recipient
    message.set_content(
        f"Your {app_name} verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code. "
        "If you did not request it, ignore this email."
    )
    message.add_alternative(_html(app_name, code, purpose, minutes), subtype="html")
    _send(message)


def send_password_changed_email(recipient: str) -> None:
    cfg = current_app.config
    app_name = cfg["APP_NAME"]
    message = EmailMessage()
    message["Subject"] = f"{app_name} password changed"
    message["From"] = f"{cfg['MAIL_FROM_NAME']} <{cfg['MAIL_FROM_ADDRESS']}>"
    message["To"] = recipient
    message.set_content(
        f"Your {app_name} Owner Portal password was changed. "
        "If you did not do this, contact support immediately."
    )
    message.add_alternative(
        f"""<!DOCTYPE html><html><body style="font-family:Georgia,serif;color:#2C2A26;padding:24px;">
<p>Your <strong>{app_name}</strong> Owner Portal password was changed.</p>
<p>If you did not do this, contact support immediately.</p>
</body></html>""",
        subtype="html",
    )
    _send(message)
