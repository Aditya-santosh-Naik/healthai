"""Response shapes for the consultation flow.

One unified turn object, so the frontend has a single thing to render whatever
the pipeline decided.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QuestionOut(BaseModel):
    # Mirrors the core dataclass field for field, so responses are
    # validated straight off it instead of copied attribute by attribute.
    model_config = ConfigDict(from_attributes=True)

    symptom_code: str
    text: str
    options: list[str]
    kind: str
    rationale: str


class EscalationOut(BaseModel):
    urgency: str
    reason: str
    action: str
    triggered_by: list[str]
    source_url: str = ""


class RefusalOut(BaseModel):
    category: str
    message: str
    referral: str
    resources: list[str] = []


class EvidenceOut(BaseModel):
    supporting: list[str] = []
    missing: list[str] = []
    contradictory: list[str] = []


class CandidateOut(BaseModel):
    code: str
    display_name: str
    band: str
    evidence: EvidenceOut
    context_factors: list[str] = []
    sources: list[dict[str, str]] = []


class SafetyFindingOut(BaseModel):
    # Mirrors the core dataclass field for field, so responses are
    # validated straight off it instead of copied attribute by attribute.
    model_config = ConfigDict(from_attributes=True)

    subject_drug: str
    related: str | None = None
    severity: str
    reason: str
    source_url: str = ""
    kind: str


class MedicationSafetyOut(BaseModel):
    overall: str
    findings: list[SafetyFindingOut] = []
    checked_medicines: list[str] = []
    unrecognised: list[str] = []


class TreatmentNoteOut(BaseModel):
    # Mirrors the core dataclass field for field, so responses are
    # validated straight off it instead of copied attribute by attribute.
    model_config = ConfigDict(from_attributes=True)

    condition_display: str
    needs_prescription: bool
    self_limiting: bool
    summary: str
    source_url: str = ""


class GeneralInfoOut(BaseModel):
    # Mirrors the core dataclass field for field, so responses are
    # validated straight off it instead of copied attribute by attribute.
    model_config = ConfigDict(from_attributes=True)

    display: str
    used_for: str
    caveat: str
    source_url: str = ""


class MedicationGuidanceOut(BaseModel):
    """Three tiers. Never a prescription, never a dose."""

    avoid: list[str] = []
    general_info: list[GeneralInfoOut] = []
    treatment: list[TreatmentNoteOut] = []
    needs_doctor_prescription: bool = False


class DietOut(BaseModel):
    prefer: list[str] = []
    avoid: list[str] = []
    hydration: list[str] = []
    lifestyle: list[str] = []
    monitor: list[str] = []
    warning_signs: list[str] = []


class SymptomOut(BaseModel):
    code: str
    display: str
    # Tri-state: True reported, False explicitly denied, None asked-but-unknown
    # ("Not sure"). None must never be rendered as a denial.
    present: bool | None


class TurnOut(BaseModel):
    """Everything the UI needs for one turn of a consultation."""

    consultation_id: int
    status: str
    outcome: str
    narrative: str = ""
    disclaimer: str

    question: QuestionOut | None = None
    questions_asked: int = 0
    sufficiency_reason: str = ""

    escalation: EscalationOut | None = None
    refusal: RefusalOut | None = None

    band: str | None = None
    symptoms: list[SymptomOut] = []
    candidates: list[CandidateOut] = []
    # Considered and set aside, with the evidence that ruled them out.
    ruled_out: list[CandidateOut] = []
    medication_safety: MedicationSafetyOut | None = None
    medication_guidance: MedicationGuidanceOut | None = None
    diet: DietOut | None = None
    doctor_summary: str = ""
    sources: list[dict[str, str]] = []

    used_fallback: bool = False
    llm_seconds: float = 0.0


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AnswerIn(BaseModel):
    symptom_code: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=64)


class FeedbackIn(BaseModel):
    helpful: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime


class HistoryItem(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    outcome_band: str | None
    summary: str


class HistoryDetail(TurnOut):
    started_at: datetime | None = None
    completed_at: datetime | None = None
    messages: list[MessageOut] = []
