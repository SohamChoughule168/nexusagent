"""Transactional email (Milestone B, Step 6).

When ``EMAIL_ENABLED`` is False (the default) sending is a no-op log line, so
the platform runs without an SMTP server. When configured, mail is sent over
SMTP using the project settings. Defensive by design: it never raises to the
caller (a failed email must not break the operation that triggered it).
"""
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str, *, html: bool = False) -> bool:
    """Send a transactional email. Returns True if sent, False otherwise.

    Returns False (and logs) when email is disabled or misconfigured, or when
    the SMTP transaction fails -- never raises.
    """
    if not settings.EMAIL_ENABLED:
        logger.info("email_skipped_disabled", to=to, subject=subject)
        return False
    if not settings.EMAIL_FROM or not settings.EMAIL_SMTP_HOST:
        logger.warning("email_skipped_misconfigured", to=to, subject=subject)
        return False
    try:
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject
        if html:
            msg.set_content("This message requires an HTML-capable mail client.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)
        with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, timeout=10) as server:
            if settings.EMAIL_USE_TLS:
                server.starttls()
            if settings.EMAIL_SMTP_USER:
                server.login(settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("email_sent", to=to, subject=subject)
        return True
    except Exception as exc:  # noqa: BLE001 -- email is best-effort
        logger.warning("email_send_failed", to=to, error=str(exc))
        return False


__all__ = ["send_email"]
