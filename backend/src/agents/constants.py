"""Single source of truth for supported insurance types and the common claim schema."""

SUPPORTED_INSURANCE_TYPES = {
    "health": "Health",
    "senior_health": "Senior Health",
    "home": "Home",
    "travel": "Travel",
    "motor": "Motor",
    "cyber": "Cyber",
}

INSURANCE_TYPE_KEYS = set(SUPPORTED_INSURANCE_TYPES.keys())

COMMON_REQUIRED_FIELDS = ["policy_id", "event_date", "insurance_type", "event_description", "estimated_claim_amount"]
