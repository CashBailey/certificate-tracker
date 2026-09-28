"""
Shared email sending utility for the Certificate Management System.

Used by the scheduler worker (notifications) and extraction worker (rejection emails).
"""

import os
import ssl

import aiosmtplib
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

log = structlog.get_logger(__name__)


async def send_email(
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: str | None = None,
) -> bool:
    """
    Send an email via SMTP.

    SMTP configuration is read from environment variables:
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_FROM_EMAIL

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.
        reply_to_message_id: Optional Message-ID to thread this email as a reply.
            Sets In-Reply-To and References headers for email client threading.

    Returns:
        True if the email was sent successfully, False on failure.
    """
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "1025"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("NOTIFICATION_FROM_EMAIL", "noreply@ci.laredo.tx.us")

    # Env-var-driven STARTTLS control; auto-detect from port if unset
    use_starttls_env = os.getenv("SMTP_USE_STARTTLS", "").lower()
    if use_starttls_env == "true":
        start_tls = True
    elif use_starttls_env == "false":
        start_tls = False
    else:
        # Auto-detect: port 587 uses STARTTLS, dev ports (1025, 3025) do not
        start_tls = smtp_port == 587

    local_test_server = smtp_host.casefold() in {
        "localhost",
        "127.0.0.1",
        "::1",
        "greenmail",
    }
    if not start_tls and (smtp_user or smtp_password):
        log.error("Refusing SMTP delivery because credentials require STARTTLS")
        return False
    if not start_tls and not local_test_server:
        log.error("Refusing plaintext SMTP delivery to a non-local server")
        return False

    try:
        message = MIMEMultipart()
        message["From"] = from_email
        message["To"] = to
        message["Subject"] = subject

        if reply_to_message_id:
            message["In-Reply-To"] = reply_to_message_id
            message["References"] = reply_to_message_id

        message.attach(MIMEText(body, "plain"))

        tls_kwargs = {}
        if start_tls:
            tls_kwargs["tls_context"] = ssl.create_default_context()

        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user if smtp_user else None,
            password=smtp_password if smtp_password else None,
            start_tls=start_tls,
            **tls_kwargs,
        )

        return True

    except Exception as e:
        log.error("SMTP send failed", error_type=type(e).__name__)
        return False
