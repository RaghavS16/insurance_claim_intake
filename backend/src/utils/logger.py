"""
Structured application logger with sensitive information masking and correlation ID tracing.
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
    re.compile(r"(otp(_hash)?\s*[:=]\s*)(['\"]?[^'\",\s]+['\"]?)", re.IGNORECASE),
]

# PII Patterns for data protection and compliance
_PII_PATTERNS = [
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[CARD_REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE_REDACTED]"),
]


def mask_pii(text: str) -> str:
    """
    Mask personally identifiable information (PII) in text strings.
    Protects logs, external exports, and debug contexts.
    """
    if not text:
        return text
    sanitized = text
    for pattern, replacement in _PII_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    return sanitized


def mask_pii_for_llm(text: str) -> str:
    """
    Sanitize text prior to transmitting into external LLM prompts.
    Redacts credentials and high-risk financial identifiers while preserving context.
    """
    if not text:
        return text
    sanitized = text
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    # Redact credit cards and SSNs specifically
    sanitized = re.sub(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b", "[CARD_REDACTED]", sanitized)
    sanitized = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]", sanitized)
    return sanitized


class SanitizedFormatter(logging.Formatter):
    """Logging formatter that redacts sensitive keys, PII, and includes Correlation ID."""

    def format(self, record: logging.LogRecord) -> str:
        from src.utils.tracing import get_correlation_id

        cid = get_correlation_id()
        cid_tag = f" [CID:{cid}]" if cid else ""

        # Format record
        orig = super().format(record)
        sanitized = orig

        for pattern in _SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)

        for pattern, replacement in _PII_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)

        if cid_tag and "[CID:" not in sanitized:
            # Insert CID after level tag
            sanitized = re.sub(r"(\[\w+\])", r"\1" + cid_tag, sanitized, count=1)

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
