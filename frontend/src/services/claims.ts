import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Response from POST /api/v1/claims/intake
export interface IntakeResponse {
    ticket_id: string;
    extracted_data: Record<string, unknown>;
    missing_fields: string[];
    awaiting_confirmation: boolean;
    message: string;
}

// Response from POST /api/v1/claims/{ticket_id}/confirm
export interface ConfirmResponse {
    ticket_id: string;
    final_decision: string;
    closure_status: string;
    response_message: string;
    spoken_response?: string;
    extracted_data?: Record<string, unknown>;
    coverage_eligible?: boolean;
    deductible_amount?: number;
    payout_amount?: number;
    fraud_score?: number;
    fraud_flags?: string[];
    assigned_adjuster?: Record<string, unknown>;
    missing_documents?: string[];
    audit_log?: string[];
}

// Document upload response
export interface DocumentUploadResponse {
    document_id: string;
    document_type: string;
    filename: string;
    status: string;
}

export async function submitIntake(
    claimText: string,
    inputMode: string = "text",
    ticketId?: string
): Promise<IntakeResponse> {
    const payload: Record<string, string> = { claim_text: claimText, input_mode: inputMode };
    if (ticketId) payload.ticket_id = ticketId;
    const response = await axios.post(`${API_URL}/api/v1/claims/intake`, payload);
    return response.data;
}

export async function confirmClaim(ticketId: string, confirmed: boolean = true): Promise<ConfirmResponse> {
    const response = await axios.post(`${API_URL}/api/v1/claims/${ticketId}/confirm`, { confirmed });
    return response.data;
}

export async function uploadDocument(
    ticketId: string,
    documentType: string,
    file: File
): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("document_type", documentType);
    formData.append("file", file);
    const response = await axios.post(`${API_URL}/api/v1/claims/${ticketId}/documents`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
}

export async function getDocumentRequirements(claimType: string): Promise<{ required_documents: string[] }> {
    const response = await axios.get(`${API_URL}/api/v1/document-requirements/${claimType}`);
    return response.data;
}

// Legacy alias kept so any existing imports don't break immediately
export type ClaimResult = ConfirmResponse;