import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ClaimResult {
    claim_text: string;
    input_mode: string;
    extracted_data?: Record<string, any>;
    policy_data?: Record<string, any>;
    coverage_eligible?: boolean;
    fraud_score?: number;
    fraud_flags?: string[];
    assigned_adjuster?: Record<string, any>;
    ticket_id?: string;
    validation_status?: string;
    final_decision?: string;
    response_message?: string;
    audit_log?: string[];
}

export async function processClaim(claimText: string): Promise<ClaimResult> {
    const response = await axios.post(`${API_URL}/api/v1/claims/process`, {
        claim_text: claimText,
        input_mode: "text",
    });
    return response.data;
}