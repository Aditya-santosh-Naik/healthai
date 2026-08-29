from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import ConsultationStatus, SafetySeverity


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default=ConsultationStatus.IN_PROGRESS)
    # Ordinal band only. Never a number.
    outcome_band: Mapped[str | None] = mapped_column(String(32))
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    llm_raw_output: Mapped[str | None] = mapped_column(Text)
    questions_asked: Mapped[int] = mapped_column(Integer, default=0)
    # The two outputs the history rebuild cannot derive from the stored rows.
    # Both are computed from the patient's profile as it was at the time, so
    # recomputing them later would quietly answer a different question --
    # "what would we say now?" rather than "what did we say?". Storing them
    # keeps a reopened consultation an accurate record.
    doctor_summary: Mapped[str | None] = mapped_column(Text)
    guidance_json: Mapped[dict | None] = mapped_column(JSON)

    profile: Mapped["PatientProfile"] = relationship(back_populates="consultations")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    symptoms: Mapped[list["ConsultationSymptom"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["CandidateEvidence"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    safety_results: Mapped[list["MedicationSafetyResult"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    retrievals: Mapped[list["RagRetrieval"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    consultation: Mapped["Consultation"] = relationship(back_populates="messages")


class ConsultationSymptom(Base):
    """A symptom observation.

    present=False is a stated negative and counts as evidence. That is not the
    same as a symptom simply being absent from the transcript.
    """

    __tablename__ = "consultation_symptoms"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symptom_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Tri-state: True reported, False explicitly denied, NULL asked-but-unknown.
    #
    # No column default on purpose. SQLAlchemy applies a default when the value
    # is None, which silently turned every "Not sure" into a reported YES --
    # and a fabricated "yes" to a red-flag screening question escalated the
    # consultation. Presence is always passed explicitly.
    present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_hours: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[int | None] = mapped_column(Integer)
    # `onset` (spec section 6) is deliberately absent: nothing ever wrote it.
    # duration_hours already carries onset timing, parsed from "2 days" or
    # "since yesterday", and a second never-populated field only invites
    # someone to read it and get None.
    source: Mapped[str] = mapped_column(String(16), default="stated")

    consultation: Mapped["Consultation"] = relationship(back_populates="symptoms")


class CandidateEvidence(Base):
    """Full evidence breakdown per candidate condition.

    internal_score is persisted for audit and testing. It is never rendered.
    """

    __tablename__ = "candidate_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    condition_code: Mapped[str] = mapped_column(String(64), nullable=False)
    band: Mapped[str] = mapped_column(String(32), nullable=False)
    # SQLAlchemy's JSON type handles serialisation both ways, so callers pass
    # and receive real lists instead of json.dumps/loads at every site.
    supporting_json: Mapped[list] = mapped_column(JSON, default=list)
    missing_json: Mapped[list] = mapped_column(JSON, default=list)
    contradictory_json: Mapped[list] = mapped_column(JSON, default=list)
    hallmark_present: Mapped[bool] = mapped_column(Boolean, default=False)
    context_factors_json: Mapped[list] = mapped_column(JSON, default=list)
    internal_score: Mapped[float] = mapped_column(Float, default=0.0)
    # How the score was arrived at: the prevalence prior it started from, and
    # every weighted symptom contribution. internal_score alone says a
    # candidate ranked first but not why -- whether it led on specific evidence
    # or merely on being common. Never rendered; this is for audit and for
    # tests that assert the reason for a ranking rather than just its order.
    scoring_json: Mapped[dict] = mapped_column(JSON, default=dict)

    consultation: Mapped["Consultation"] = relationship(back_populates="evidence")


class MedicationSafetyResult(Base):
    __tablename__ = "medication_safety_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_drug: Mapped[str] = mapped_column(String(120), nullable=False)
    related_drug_or_condition: Mapped[str | None] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(16), default=SafetySeverity.NONE)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512))

    consultation: Mapped["Consultation"] = relationship(back_populates="safety_results")


class RagRetrieval(Base):
    __tablename__ = "rag_retrievals"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512))
    score: Mapped[float] = mapped_column(Float, default=0.0)

    consultation: Mapped["Consultation"] = relationship(back_populates="retrievals")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    consultation: Mapped["Consultation"] = relationship(back_populates="recommendations")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PdfReport(Base):
    __tablename__ = "pdf_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filepath: Mapped[str] = mapped_column(String(512), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
