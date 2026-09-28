export const title = (v?: string) =>
  (v || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const money = (v?: number) =>
  v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN");

export type AdjusterViewType = "queue" | "file" | "evidence" | "knowledge" | "copilot";

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
  summary?: string;
  coverage_observations?: string[];
  evidence_gaps?: string[];
  [key: string]: unknown;
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
  policy_verification: Record<string, unknown>;
  knowledge_sources: KnowledgeItem[];
  copilot: CopilotAnalysis;
  submission_package?: SubmissionPackage;
  conversation_phase?: string;
  gap_analysis?: Record<string, unknown>;
}

