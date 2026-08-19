from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import ConditionStatus, MedicationStatus, Provenance


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    blood_group: Mapped[str | None] = mapped_column(String(8))
    diet_type: Mapped[str] = mapped_column(String(16), default="veg", nullable=False)
    smoker: Mapped[bool] = mapped_column(Boolean, default=False)
    alcohol: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile")  # noqa: F821
    conditions: Mapped[list["PatientCondition"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    allergies: Mapped[list["PatientAllergy"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    medications: Mapped[list["PatientMedication"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    documents: Mapped[list["MedicalDocument"]] = relationship(  # noqa: F821
        back_populates="profile", cascade="all, delete-orphan"
    )
    consultations: Mapped[list["Consultation"]] = relationship(  # noqa: F821
        back_populates="profile", cascade="all, delete-orphan"
    )


class PatientCondition(Base):
    __tablename__ = "patient_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    condition_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ConditionStatus.ACTIVE)
    onset_date: Mapped[date | None] = mapped_column(Date)
    provenance: Mapped[str] = mapped_column(String(32), default=Provenance.USER_ENTERED)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("medical_documents.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile: Mapped["PatientProfile"] = relationship(back_populates="conditions")


class PatientAllergy(Base):
    __tablename__ = "patient_allergies"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen: Mapped[str] = mapped_column(String(120), nullable=False)
    # Drives cross-reactivity: a penicillin allergy must flag amoxicillin.
    allergen_class: Mapped[str | None] = mapped_column(String(64), index=True)
    reaction: Mapped[str | None] = mapped_column(String(255))
    severity: Mapped[str | None] = mapped_column(String(32))
    provenance: Mapped[str] = mapped_column(String(32), default=Provenance.USER_ENTERED)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile: Mapped["PatientProfile"] = relationship(back_populates="allergies")


class PatientMedication(Base):
    __tablename__ = "patient_medications"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_name: Mapped[str | None] = mapped_column(String(120))
    # Resolved from brand via data/drugs.yaml; the safety engine keys on this.
    generic_name: Mapped[str | None] = mapped_column(String(120), index=True)
    dose: Mapped[str | None] = mapped_column(String(64))
    frequency: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default=MedicationStatus.PRESCRIBED_TAKING)
    provenance: Mapped[str] = mapped_column(String(32), default=Provenance.USER_ENTERED)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile: Mapped["PatientProfile"] = relationship(back_populates="medications")
