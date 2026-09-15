"""Claim-type-specific requirement catalogue.

The catalogue is a safe baseline. In production, admin-ingested policy/regulatory
documents should provide the authoritative wording and may add/override requirements.
"""
from pydantic import BaseModel, Field

class Requirement(BaseModel):
    key: str
    label: str
    question_hint: str
    required: bool = True
    evidence_type: str | None = None

REQUIREMENTS = {
    "motor": [
        Requirement(key="vehicle_registration", label="Vehicle registration", question_hint="Ask for the vehicle registration details if not already known.", evidence_type="registration"),
        Requirement(key="driver_details", label="Driver details", question_hint="Clarify who was driving at the time of the incident."),
        Requirement(key="third_party_involvement", label="Third-party involvement", question_hint="Clarify whether another person or vehicle was involved."),
        Requirement(key="damage_details", label="Damage details", question_hint="Clarify which parts of the vehicle were damaged.", evidence_type="photos"),
        Requirement(key="repair_estimate", label="Repair estimate", question_hint="Ask whether a repair estimate is available.", evidence_type="estimate"),
    ],
    "home": [
        Requirement(key="property_details", label="Property details", question_hint="Clarify the affected property."),
        Requirement(key="cause_of_loss", label="Cause of loss", question_hint="Clarify the cause and circumstances of the loss."),
        Requirement(key="damage_details", label="Damage details", question_hint="Clarify the extent of damage.", evidence_type="photos"),
        Requirement(key="repair_estimate", label="Repair estimate", question_hint="Ask whether a repair estimate is available.", evidence_type="estimate"),
    ],
    "health": [
        Requirement(key="treatment_details", label="Treatment details", question_hint="Clarify the treatment received and why it was needed."),
        Requirement(key="provider_details", label="Provider details", question_hint="Clarify the hospital, clinic or doctor."),
        Requirement(key="admission_details", label="Admission details", question_hint="Ask for admission/discharge details when applicable.", evidence_type="medical_record"),
        Requirement(key="bills", label="Medical bills", question_hint="Ask whether treatment bills are available.", evidence_type="bill"),
    ],
    "senior_health": [
        Requirement(key="treatment_details", label="Treatment details", question_hint="Clarify the treatment received and why it was needed."),
        Requirement(key="provider_details", label="Provider details", question_hint="Clarify the hospital, clinic or doctor."),
        Requirement(key="admission_details", label="Admission details", question_hint="Ask for admission/discharge details when applicable.", evidence_type="medical_record"),
        Requirement(key="bills", label="Medical bills", question_hint="Ask whether treatment bills are available.", evidence_type="bill"),
    ],
    "travel": [
        Requirement(key="trip_details", label="Trip details", question_hint="Clarify the relevant trip dates, destination and booking."),
        Requirement(key="incident_context", label="Incident context", question_hint="Clarify what happened during the trip."),
        Requirement(key="carrier_reference", label="Carrier reference", question_hint="Ask for the airline/carrier or booking reference when relevant."),
        Requirement(key="supporting_records", label="Supporting records", question_hint="Ask which tickets, receipts or reports are available.", evidence_type="document"),
    ],
    "cyber": [
        Requirement(key="affected_system", label="Affected system", question_hint="Clarify which system, account or service was affected."),
        Requirement(key="incident_timeline", label="Incident timeline", question_hint="Clarify when the incident was detected and key events."),
        Requirement(key="containment_actions", label="Containment actions", question_hint="Clarify what containment or remediation was performed."),
        Requirement(key="technical_evidence", label="Technical evidence", question_hint="Ask whether relevant logs, notices or technical records are available.", evidence_type="technical_record"),
    ],
}

def get_requirements(insurance_type: str) -> list[Requirement]:
    return list(REQUIREMENTS.get((insurance_type or "").lower(), []))
