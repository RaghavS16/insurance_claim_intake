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

export interface FileData {
  claim: Claim;
  extracted_data: Record<string, unknown>;
  conversation: { speaker: string; text: string; turn: number }[];
  requirements: RequirementItem[];
  missing_requirements: RequirementItem[];
  missing_evidence: RequirementItem[];
  evidence: EvidenceItem[];
  policy_verification: Record<string, unknown>;
  knowledge_sources: KnowledgeItem[];
  copilot: CopilotAnalysis;
}
