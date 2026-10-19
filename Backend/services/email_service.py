"""SMTP delivery for verification codes. Failures are reported, never treated as sent."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from config import settings

TEMPLATE = (
    Path(__file__).resolve().parents[1] / "templates" / "verification_email.html"
)


class EmailDeliveryError(RuntimeError):
    pass


def render_verification_email(code: str) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("{{app_name}}", settings.app_name)
        .replace("{{code}}", code)
        .replace("{{expires_in}}", f"{settings.email_verification_expire_minutes} minutes")
    )


def send_verification_email(recipient: str, code: str) -> None:
    missing = settings.missing_smtp()
    if missing:
        raise EmailDeliveryError("Email delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = f"{settings.app_name} verification code"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    minutes = settings.email_verification_expire_minutes
    message.set_content(
        f"Your {settings.app_name} verification code is {code}. "
        f"It expires in {minutes} minutes. Do not share this code. "
        "If you did not request it, you can ignore this email."
    )
    message.add_alternative(render_verification_email(code), subtype="html")

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
                context=ssl.create_default_context(),
            ) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("The verification email could not be sent.") from error
