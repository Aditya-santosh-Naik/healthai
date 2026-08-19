"""Controlled vocabularies used across the schema.

Stored as plain strings in SQLite; validated at the Pydantic boundary.
"""
from enum import StrEnum


class Provenance(StrEnum):
    """Where a profile fact came from.

    Invariant: AI-inferred data never silently becomes profile truth.
    """

    USER_ENTERED = "user_entered"
    DOCUMENT_EXTRACTED_CONFIRMED = "document_extracted_confirmed"
    AI_INFERRED = "ai_inferred"


class ConditionStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class MedicationStatus(StrEnum):
    PRESCRIBED_TAKING = "prescribed_taking"
    PRESCRIBED_NOT_TAKING = "prescribed_not_taking"
    SELF_MEDICATING = "self_medicating"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class DietType(StrEnum):
    VEG = "veg"
    NON_VEG = "non_veg"
    VEGAN = "vegan"
    JAIN = "jain"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    NO_TEXT_LAYER = "no_text_layer"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EDITED = "edited"


class ConsultationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    ESCALATED = "escalated"
    REFUSED = "refused"


class OutcomeBand(StrEnum):
    """Ordinal evidence bands. Never a percentage, never a score."""

    MOST_CONSISTENT = "most_consistent"
    POSSIBLE = "possible"
    LESS_CONSISTENT = "less_consistent"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class SymptomSource(StrEnum):
    STATED = "stated"
    ANSWERED = "answered"


class SafetySeverity(StrEnum):
    NONE = "none"
    CAUTION = "caution"
    AVOID = "avoid"


class RecommendationCategory(StrEnum):
    DIET_PREFER = "diet_prefer"
    DIET_AVOID = "diet_avoid"
    HYDRATION = "hydration"
    LIFESTYLE = "lifestyle"
    MONITOR = "monitor"
    WARNING_SIGN = "warning_sign"
