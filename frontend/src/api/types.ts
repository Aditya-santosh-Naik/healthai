/** Shapes mirrored from the backend Pydantic schemas. */

export type Sex = "male" | "female" | "other";
export type DietType = "veg" | "non_veg" | "vegan" | "jain";
export type ConditionStatus = "active" | "resolved";
export type MedicationStatus =
  | "prescribed_taking"
  | "prescribed_not_taking"
  | "self_medicating";
export type Provenance =
  | "user_entered"
  | "document_extracted_confirmed"
  | "ai_inferred";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  has_profile: boolean;
}

export interface ConditionIn {
  condition_name: string;
  status: ConditionStatus;
  onset_date?: string | null;
}

export interface ConditionOut extends ConditionIn {
  id: number;
  provenance: Provenance;
  confirmed_at: string | null;
}

export interface AllergyIn {
  allergen: string;
  allergen_class?: string | null;
  reaction?: string | null;
  severity?: string | null;
}

export interface AllergyOut extends AllergyIn {
  id: number;
  provenance: Provenance;
  confirmed_at: string | null;
}

export interface MedicationIn {
  brand_name?: string | null;
  generic_name?: string | null;
  dose?: string | null;
  frequency?: string | null;
  route?: string | null;
  reason?: string | null;
  start_date?: string | null;
  status: MedicationStatus;
}

export interface MedicationOut extends MedicationIn {
  id: number;
  provenance: Provenance;
  confirmed_at: string | null;
}

export interface ProfileBase {
  name: string;
  age: number;
  sex: Sex;
  height_cm?: number | null;
  weight_kg?: number | null;
  blood_group?: string | null;
  diet_type: DietType;
  smoker: boolean;
  alcohol: boolean;
}

export interface ProfileCreate extends ProfileBase {
  conditions: ConditionIn[];
  allergies: AllergyIn[];
  medications: MedicationIn[];
}

export interface ProfileOut extends ProfileBase {
  id: number;
  created_at: string;
  updated_at: string;
  conditions: ConditionOut[];
  allergies: AllergyOut[];
  medications: MedicationOut[];
}
