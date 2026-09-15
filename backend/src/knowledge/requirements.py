"""Dynamic claim-specific requirements resolver.

The resolver is deliberately independent from the conversational LLM. A production
deployment can replace/augment the seed catalogue with indexed policy/regulatory
documents without changing the LangGraph conversation contract.
"""
from __future__ import annotations
from .models import ClaimRequirement, RequirementSet

# These are product defaults, not policy/legal advice. Admin-managed knowledge should
# override them when authoritative documents are available.
DEFAULT_REQUIREMENTS: dict[str, list[ClaimRequirement]] = {
    "motor": [
        ClaimRequirement(key="vehicle_registration", label="Vehicle registration", description="Registration number/details of the insured vehicle.", evidence_type="registration"),
        ClaimRequirement(key="driver_details", label="Driver details", description="Who was driving at the time of the incident.", evidence_type="identity"),
        ClaimRequirement(key="third_party_involvement", label="Third-party involvement", description="Whether another person or vehicle was involved."),
        ClaimRequirement(key="damage_details", label="Damage details", description="What parts of the vehicle were damaged.", evidence_type="photos"),
        ClaimRequirement(key="repair_estimate", label="Repair estimate", description="Available repair estimate or assessment.", evidence_type="estimate"),
    ],
    "home": [
        ClaimRequirement(key="property_details", label="Property details", description="Details identifying the affected property."),
        ClaimRequirement(key="cause_of_loss", label="Cause of loss", description="Cause and circumstances of the property loss."),
        ClaimRequirement(key="damage_details", label="Damage details", description="Description and extent of damage.", evidence_type="photos"),
        ClaimRequirement(key="repair_estimate", label="Repair estimate", description="Available repair or replacement estimate.", evidence_type="estimate"),
    ],
    "health": [
        ClaimRequirement(key="treatment_details", label="Treatment details", description="Treatment, diagnosis, and care received."),
        ClaimRequirement(key="provider_details", label="Provider details", description="Hospital/doctor/provider details."),
        ClaimRequirement(key="admission_details", label="Admission details", description="Admission/discharge information when applicable.", evidence_type="medical_record"),
        ClaimRequirement(key="bills", label="Medical bills", description="Available treatment bills and invoices.", evidence_type="bill"),
    ],
    "senior_health": [
        ClaimRequirement(key="treatment_details", label="Treatment details", description="Treatment, diagnosis, and care received."),
        ClaimRequirement(key="provider_details", label="Provider details", description="Hospital/doctor/provider details."),
        ClaimRequirement(key="admission_details", label="Admission details", description="Admission/discharge information when applicable.", evidence_type="medical_record"),
        ClaimRequirement(key="bills", label="Medical bills", description="Available treatment bills and invoices.", evidence_type="bill"),
    ],
    "travel": [
        ClaimRequirement(key="trip_details", label="Trip details", description="Travel dates, destination, and booking context."),
        ClaimRequirement(key="incident_context", label="Incident context", description="Circumstances of the travel-related loss."),
        ClaimRequirement(key="carrier_reference", label="Carrier reference", description="Airline/carrier or booking reference when relevant."),
        ClaimRequirement(key="supporting_records", label="Supporting records", description="Receipts, tickets, reports, or other relevant records.", evidence_type="document"),
    ],
    "cyber": [
        ClaimRequirement(key="affected_system", label="Affected system", description="System, account, or service affected."),
        ClaimRequirement(key="incident_timeline", label="Incident timeline", description="When the compromise was detected and key events."),
        ClaimRequirement(key="containment_actions", label="Containment actions", description="Actions taken to contain or remediate the incident."),
        ClaimRequirement(key="technical_evidence", label="Technical evidence", description="Relevant logs, notices, or technical records.", evidence_type="technical_record"),
    ],
}

def get_requirement_set(insurance_type: str) -> RequirementSet:
    key = (insurance_type or "").strip().lower()
    return RequirementSet(insurance_type=key, requirements=list(DEFAULT_REQUIREMENTS.get(key, [])))
