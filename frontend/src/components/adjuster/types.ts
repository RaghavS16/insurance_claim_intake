export const title = (v?: string) =>
  (v || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const money = (v?: number) =>
  v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN");

export type AdjusterViewType = "queue" | "knowledge" | "file" | "evidence" | "copilot";

export interface AdjusterUser {
  id?: string;
  email?: string;
  full_name?: string;
  role?: string;
  specialization?: string;
  [key: string]: unknown;
}

export interface Claim {
  ticket_id: string;
  status: string;
  insurance_type?: string;
  event_date?: string;
  event_location?: string;
  estimated_claim_amount?: number;
  event_description?: string;
  priority?: string;
  assigned_adjuster_id?: string;
  assigned_adjuster_name?: string;
  claimant_confirmed?: boolean;
  policy_verified?: boolean;
  dynamic_requirements_complete?: boolean;
  updated_at?: string;
}

export interface KnowledgeItem {
  source_name?: string;
  document_type?: string;
  text?: string;
  score?: number;
  [key: string]: unknown;
}

export interface EvidenceItem {
  id?: string;
  evidence_id?: string;
  name?: string;
  type?: string;
  status?: string;
  url?: string;
  [key: string]: unknown;
}

export interface RequirementItem {
  label?: string;
  key?: string;
  evidence_type?: string;
  description?: string;
  [key: string]: unknown;
}

export interface CopilotAnalysis {
  executive_summary?: string;
  summary?: string;
  decision_recommendation?: string;
  recommended_payout_amount?: number | null;
  confidence_score?: number;
  decision_rationale?: string;
  actionable_suggestions?: string[];
  coverage_observations?: string[];
  mandatory_requirements?: Array<{ label?: string; status?: string; condition?: string }>;
  evidence_assessment?: string[];
  evidence_gaps?: string[];
  risk_flags?: string[];
  regulatory_considerations?: string[];
  decision_considerations?: string[];
  recommended_next_steps?: string[];
  uncertainties?: string[];
  [key: string]: unknown;
}

export interface EvidenceRequest {
  id: string;
  request_text: string;
  status: string;
  response_note?: string | null;
  requested_at?: string | null;
  responded_at?: string | null;
  response_evidence?: { id?: string; name?: string; verification_status?: string } | null;
}

export interface SubmissionPackage {
  ticket_id?: string;
  compiled_at?: string;
  status?: string;
  executive_summary?: string;
  chronological_narrative?: Array<{ timestamp?: string; event?: string; details?: string }>;
  verified_policyholder_details?: {
    claimant_name?: string;
    contact_info?: string;
    policy_number?: string;
    insurance_type?: string;
    policy_status?: string;
    effective_date?: string;
    expiry_date?: string;
    coverage_limit?: number;
    standard_deductible?: number;
    verification_protocol?: Array<{ step: string; status: string }>;
  };
  qa_transcript?: Array<{ turn: number; speaker: string; text: string; timestamp?: string }>;
  evidence_index?: Array<{
    id?: string;
    label?: string;
    document_type?: string;
    verification_status?: string;
    confidence?: number;
    s3_key?: string;
    sha256?: string;
  }>;
  risk_assessment_flags?: string[];
  recommended_next_steps?: string[];
}

export interface FileData {
  claim: Claim;
  extracted_data: Record<string, unknown>;
  conversation: { speaker: string; text: string; turn: number; timestamp?: string }[];
  requirements: RequirementItem[];
  missing_requirements: RequirementItem[];
  missing_evidence: RequirementItem[];
  evidence: EvidenceItem[];
  evidence_requests?: EvidenceRequest[];
  policy_verification: Record<string, unknown>;
  knowledge_sources: KnowledgeItem[];
  copilot: CopilotAnalysis;
  copilot_chat?: Array<{ speaker: string; message: string; created_at?: string }>;
  submission_package?: SubmissionPackage;
  conversation_phase?: string;
  gap_analysis?: Record<string, unknown>;
}

