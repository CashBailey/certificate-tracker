"""
Secure logging utilities with automatic redaction.

Provides redaction of sensitive data (emails, storage keys, UUIDs) in log output.
"""

import logging
import re


# Redaction patterns for sensitive data
REDACTION_PATTERNS = {
    # Email addresses: preserve domain structure but redact local part
    r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})": r"[REDACTED]@\2",
    # Storage keys: email-intake/{date}/{uuid}.ext
    r"(email-intake/\d+/)([a-f0-9]{32})": r"\1[REDACTED]",
    # Employee storage paths: {employee_id}/{uuid}/{filename}
    r"(\d+/)([a-f0-9-]{36})(/.+)": r"\1[REDACTED]\3",
    # UUIDs in any context
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}": "[UUID-REDACTED]",
    # 32-char hex strings (potential API keys, tokens)
    r"\b[a-f0-9]{32}\b": "[HEX-REDACTED]",
}


class RedactingFormatter(logging.Formatter):
    """
    A logging formatter that automatically redacts sensitive data.

    Applies redaction patterns to log messages to prevent PII and
    sensitive identifiers from appearing in logs.
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = "%",
        validate: bool = True,
    ):
        """
        Initialize the redacting formatter.

        Args:
            fmt: Log message format string
            datefmt: Date format string
            style: Format style ('%', '{', or '$')
            validate: Whether to validate the format string
        """
        super().__init__(fmt, datefmt, style, validate)
        # Pre-compile patterns for performance
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in REDACTION_PATTERNS.items()
        ]

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with redaction applied.

        Args:
            record: The log record to format

        Returns:
            Formatted and redacted log message
        """
        # First, format the message normally
        msg = super().format(record)

        # Then apply all redaction patterns
        for pattern, replacement in self._compiled_patterns:
            msg = pattern.sub(replacement, msg)

        return msg


def configure_secure_logging(
    level: str = "INFO",
    format_string: str | None = None,
) -> None:
    """
    Configure secure logging with automatic redaction for the application.

    Sets up a stream handler with the RedactingFormatter as the root logger's
    handler. This ensures all log output is automatically redacted.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string. If None, uses a sensible default.

    Example:
        >>> configure_secure_logging(level="DEBUG")
        >>> logging.info("User email: user@example.com")
        # Output: ... User email: [REDACTED]@example.com
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create handler with redacting formatter
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(format_string))

    # Get the root logger and configure it
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_secure_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with secure configuration.

    If configure_secure_logging() hasn't been called, this ensures
    the returned logger will at least have redaction applied.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # If root logger doesn't have a redacting handler, add one to this logger
    root_logger = logging.getLogger()
    has_redacting_handler = any(
        isinstance(h.formatter, RedactingFormatter) for h in root_logger.handlers
    )

    if not has_redacting_handler and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            RedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
        logger.propagate = False

    return logger
