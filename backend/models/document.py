from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import ExtractionStatus, ReviewStatus


class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filepath: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    extraction_status: Mapped[str] = mapped_column(
        String(32), default=ExtractionStatus.PENDING
    )
    page_count: Mapped[int | None] = mapped_column(Integer)

    profile: Mapped["PatientProfile"] = relationship(back_populates="documents")  # noqa: F821
    facts: Mapped[list["ExtractedFact"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ExtractedFact(Base):
    """A candidate profile fact pulled from a PDF.

    Nothing here reaches the profile until review_status == confirmed.
    """

    __tablename__ = "extracted_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("medical_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fact_type: Mapped[str] = mapped_column(String(32), nullable=False)  # condition|allergy|medication
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    page_ref: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.PENDING)

    document: Mapped["MedicalDocument"] = relationship(back_populates="facts")
