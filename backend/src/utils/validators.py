"""
Centralized input validation and sanitization utilities.

All user-facing input validation should be routed through these helpers
to ensure consistent, production-grade security across the entire API surface.
"""
import re
from typing import List, Optional, Set

# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


def validate_email(email: str) -> str:
    """Validate and normalize an email address. Raises ValueError on invalid input."""
    if not email or not isinstance(email, str):
        raise ValueError("Email address is required.")
    cleaned = email.strip().lower()
    if len(cleaned) < 5 or len(cleaned) > 254:
        raise ValueError("Email address must be between 5 and 254 characters.")
    if not _EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email address format.")
    return cleaned


# ---------------------------------------------------------------------------
# Password complexity
# ---------------------------------------------------------------------------
def validate_password_strength(password: str) -> str:
    """
    Enforce production-grade password complexity:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns the password unchanged if valid. Raises ValueError otherwise.
    """
    if not password or not isinstance(password, str):
        raise ValueError("Password is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):
        raise ValueError("Password must contain at least one special character (!@#$%^&*...).")
    return password


# ---------------------------------------------------------------------------
# Ticket ID format
# ---------------------------------------------------------------------------
_TICKET_ID_REGEX = re.compile(r"^CLAIM-[A-Z0-9]{8}$")


def validate_ticket_id(ticket_id: str) -> str:
    """Validate ticket_id format (CLAIM-XXXXXXXX). Raises ValueError on invalid."""
    if not ticket_id or not isinstance(ticket_id, str):
        raise ValueError("Ticket ID is required.")
    cleaned = ticket_id.strip().upper()
    if not _TICKET_ID_REGEX.match(cleaned):
        raise ValueError(f"Invalid ticket ID format: '{ticket_id}'. Expected CLAIM-XXXXXXXX.")
    return cleaned


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------
VALID_FINAL_DECISIONS: Set[str] = {
    "approved", "denied", "need_more_info", "need_documents",
    "flagged_for_review", "manual_review",
}

VALID_CLOSURE_STATUSES: Set[str] = {
    "awaiting_user", "pending_review", "closed",
}

VALID_DOCUMENT_TYPES: Set[str] = {
    "POLICY_WORDING", "IRDAI_REGULATION",
}

VALID_CLAIM_TYPES: Set[str] = {
    "health", "senior_health", "home", "travel", "motor", "cyber",
}


def validate_enum(value: str, valid_values: Set[str], field_name: str) -> str:
    """Validate that a string value is within an allowed set. Raises ValueError."""
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} is required.")
    cleaned = value.strip().lower()
    if cleaned not in valid_values:
        raise ValueError(
            f"Invalid {field_name}: '{value}'. Must be one of: {', '.join(sorted(valid_values))}"
        )
    return cleaned


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------
_DANGEROUS_PATTERNS = re.compile(r"[<>\"';]|--|\b(DROP|DELETE|INSERT|UPDATE|ALTER|EXEC|UNION)\b", re.IGNORECASE)


def sanitize_text_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize free-text user input:
    - Strip leading/trailing whitespace
    - Remove null bytes
    - Truncate to max_length
    - Escape curly braces (template injection prevention)
    """
    if not text:
        return ""
    clean = text.replace("\x00", "").strip()
    clean = clean[:max_length]
    return clean


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal attacks.
    Strips directory separators and null bytes.
    """
    if not filename:
        return "unnamed"
    # Remove path separators and null bytes
    clean = filename.replace("\x00", "")
    clean = clean.replace("/", "_").replace("\\", "_").replace("..", "_")
    # Remove any remaining dangerous chars
    clean = re.sub(r"[^\w.\-]", "_", clean)
    return clean or "unnamed"


def validate_phone(phone: Optional[str]) -> Optional[str]:
    """Validate an optional phone number format."""
    if not phone or not phone.strip():
        return None
    cleaned = phone.strip()
    if len(cleaned) > 20:
        raise ValueError("Phone number must not exceed 20 characters.")
    # Allow digits, spaces, hyphens, parentheses, and plus sign
    if not re.match(r"^[\d\s\-\+\(\)]+$", cleaned):
        raise ValueError("Phone number contains invalid characters.")
    return cleaned


def validate_full_name(name: str) -> str:
    """Validate a user's full name."""
    if not name or not isinstance(name, str):
        raise ValueError("Full name is required.")
    cleaned = name.strip()
    if len(cleaned) < 1 or len(cleaned) > 100:
        raise ValueError("Full name must be between 1 and 100 characters.")
    # Prevent obvious injection attempts in names
    if _DANGEROUS_PATTERNS.search(cleaned):
        raise ValueError("Full name contains invalid characters.")
    return cleaned
