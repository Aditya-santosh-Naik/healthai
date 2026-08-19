"""SQLAlchemy models. Importing this package registers every table."""
from models.audit import AuditLog
from models.consultation import (
    CandidateEvidence,
    Consultation,
    ConsultationSymptom,
    Feedback,
    MedicationSafetyResult,
    Message,
    PdfReport,
    RagRetrieval,
    Recommendation,
)
from models.document import ExtractedFact, MedicalDocument
from models.profile import (
    PatientAllergy,
    PatientCondition,
    PatientMedication,
    PatientProfile,
)
from models.user import User

__all__ = [
    "AuditLog",
    "CandidateEvidence",
    "Consultation",
    "ConsultationSymptom",
    "ExtractedFact",
    "Feedback",
    "MedicalDocument",
    "MedicationSafetyResult",
    "Message",
    "PatientAllergy",
    "PatientCondition",
    "PatientMedication",
    "PatientProfile",
    "PdfReport",
    "RagRetrieval",
    "Recommendation",
    "User",
]
