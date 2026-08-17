"""
Structured application logger with sensitive information masking.
"""
import logging
import re
import sys
from typing import Any

# Sensitive field patterns to redact in logs
_SENSITIVE_PATTERNS = [
    re.compile(r"(password\s*[:=]\s*)(['\"]?[^'\",\s]+['\"]?)", re.IGNORECASE),
    re.compile(r"(secret\s*[:=]\s*)(['\"]?[^'\",\s]+['\"]?)", re.IGNORECASE),
    re.compile(r"(authorization\s*[:=]\s*Bearer\s+)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[:=]\s*)(['\"]?[^'\",\s]+['\"]?)", re.IGNORECASE),
]


class SanitizedFormatter(logging.Formatter):
    """Logging formatter that redacts sensitive keys and secrets."""

    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        sanitized = orig
        for pattern in _SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
        return sanitized


def setup_logger(name: str = "insurance_claim_intake", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a structured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = SanitizedFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


# Default application logger
app_logger = setup_logger()
