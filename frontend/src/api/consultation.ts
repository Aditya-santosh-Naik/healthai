/** Shapes mirrored from backend/schemas/consultation.py */

export type Band =
  | "most_consistent"
  | "possible"
  | "less_consistent"
  | "insufficient_information";

export type Outcome =
  | "needs_question"
  | "complete"
  | "escalated"
  | "refused"
  | "in_progress";

export interface Question {
  symptom_code: string;
  text: string;
  options: string[];
  kind: "safety" | "discriminating";
  rationale: string;
}

export interface Escalation {
  urgency: string;
  reason: string;
  action: string;
  triggered_by: string[];
  source_url: string;
}

export interface Refusal {
  category: string;
  message: string;
  referral: string;
  resources: string[];
}

export interface Evidence {
  supporting: string[];
  missing: string[];
  contradictory: string[];
}

export interface Candidate {
  code: string;
  display_name: string;
  band: Band;
  evidence: Evidence;
  context_factors: string[];
  sources: { name?: string; url?: string }[];
}

export interface SafetyFinding {
  subject_drug: string;
  related: string | null;
  severity: "none" | "caution" | "avoid";
  reason: string;
  source_url: string;
  kind: string;
}

export interface MedicationSafety {
  overall: string;
  findings: SafetyFinding[];
  checked_medicines: string[];
  unrecognised: string[];
}

export interface TreatmentNote {
  condition_display: string;
  needs_prescription: boolean;
  self_limiting: boolean;
  summary: string;
  source_url: string;
}

export interface GeneralInfo {
  display: string;
  used_for: string;
  caveat: string;
  source_url: string;
}

export interface MedicationGuidance {
  avoid: string[];
  general_info: GeneralInfo[];
  treatment: TreatmentNote[];
  needs_doctor_prescription: boolean;
}

export interface Diet {
  prefer: string[];
  avoid: string[];
  hydration: string[];
  lifestyle: string[];
  monitor: string[];
  warning_signs: string[];
}

export interface Symptom {
  code: string;
  display: string;
  /** true reported, false explicitly denied, null asked but unknown. */
  present: boolean | null;
}

export interface Turn {
  consultation_id: number;
  status: string;
  outcome: Outcome;
  narrative: string;
  disclaimer: string;

  question: Question | null;
  questions_asked: number;
  sufficiency_reason: string;

  escalation: Escalation | null;
  refusal: Refusal | null;

  band: Band | null;
  symptoms: Symptom[];
  candidates: Candidate[];
  /** Considered and set aside, with the evidence that ruled them out. */
  ruled_out: Candidate[];
  medication_safety: MedicationSafety | null;
  medication_guidance: MedicationGuidance | null;
  diet: Diet | null;
  doctor_summary: string;
  sources: { name?: string; url?: string }[];

  used_fallback: boolean;
  llm_seconds: number;
}

export interface HistoryItem {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  outcome_band: Band | null;
  summary: string;
}

export interface HistoryDetail extends Turn {
  started_at: string | null;
  completed_at: string | null;
  messages: { role: string; content: string; created_at: string }[];
}

export const BAND_LABEL: Record<Band, string> = {
  most_consistent: "Most consistent with",
  possible: "Possible, not established",
  less_consistent: "Less consistent",
  insufficient_information: "Not enough information",
};
