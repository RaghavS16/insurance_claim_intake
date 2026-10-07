export type UserRole = 'CLAIMANT' | 'ADJUSTER' | 'ADMIN';

export interface User {
  id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  role: UserRole;
  status: string;
}

export interface Policy {
  id: string;
  policy_number: string;
  customer_id?: string | null;
  policy_type: string;
  coverage_amount: number;
  deductible: number;
  effective_date: string;
  expiry_date: string;
  is_active: boolean;
  policyholder_name?: string | null;
  policyholder_dob?: string | null;
  policyholder_phone?: string | null;
  policyholder_phone_last4?: string | null;
  linked_at?: string | null;
}

export type ClaimStatus = 
  | 'draft' 
  | 'submitted' 
  | 'under_review' 
  | 'pending_evidence' 
  | 'approved' 
  | 'rejected' 
  | 'escalated';

export interface ConversationTurn {
  id?: string;
  turn_number: number;
  speaker: 'user' | 'assistant' | 'system';
  text: string;
  audio_url?: string | null;
  attachment?: any;
  created_at?: string;
}

export interface Claim {
  id: string;
  ticket_id: string;
  claimant_id?: string | null;
  customer_id?: string | null;
  policy_id?: string | null;
  insurance_type?: string | null;
  claim_date?: string | null;
  event_date?: string | null;
  event_description?: string | null;
  event_location?: string | null;
  estimated_claim_amount?: number | null;
  extraction_confidence?: number | null;
  validation_status?: string | null;
  status: ClaimStatus;
  conversation_status?: string;
  pipeline_state?: Record<string, any>;
  assigned_adjuster_name?: string | null;
  turns?: ConversationTurn[];
  created_at?: string;
  updated_at?: string;
}

export interface Adjuster {
  id: string;
  user_id?: string | null;
  name: string;
  email: string;
  phone?: string | null;
  specialization: string;
  claims_assigned: number;
  is_active: boolean;
}

export interface KnowledgeDocument {
  id: string;
  source_name: string;
  source_uri?: string;
  document_type: string;
  insurance_type?: string | null;
  jurisdiction?: string | null;
  document_version?: string | null;
  policy_version?: string | null;
  created_at?: string;
  chunk_count?: number;
  chunks?: number;
  is_published?: boolean;
  publication_status?: string;
}

export interface AuditEvent {
  id: string;
  action: string;
  actor_email: string;
  actor_role: string;
  ticket_id?: string | null;
  ip_address?: string | null;
  timestamp: string;
  details?: Record<string, any>;
}
