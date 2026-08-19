from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    ConditionStatus,
    DietType,
    MedicationStatus,
    Provenance,
    Sex,
)

# Under-18 is refused at the scope guard; the profile itself also rejects it
# so the state can never exist in the database.
MIN_AGE = 18
MAX_AGE = 120


class ConditionIn(BaseModel):
    condition_name: str = Field(min_length=1, max_length=120)
    status: ConditionStatus = ConditionStatus.ACTIVE
    onset_date: date | None = None


class ConditionOut(ConditionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provenance: Provenance
    confirmed_at: datetime | None = None


class AllergyIn(BaseModel):
    allergen: str = Field(min_length=1, max_length=120)
    allergen_class: str | None = Field(default=None, max_length=64)
    reaction: str | None = Field(default=None, max_length=255)
    severity: str | None = Field(default=None, max_length=32)


class AllergyOut(AllergyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provenance: Provenance
    confirmed_at: datetime | None = None


class MedicationIn(BaseModel):
    brand_name: str | None = Field(default=None, max_length=120)
    generic_name: str | None = Field(default=None, max_length=120)
    dose: str | None = Field(default=None, max_length=64)
    frequency: str | None = Field(default=None, max_length=64)
    route: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    status: MedicationStatus = MedicationStatus.PRESCRIBED_TAKING


class MedicationOut(MedicationIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provenance: Provenance
    confirmed_at: datetime | None = None


class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=MIN_AGE, le=MAX_AGE)
    sex: Sex
    height_cm: float | None = Field(default=None, gt=0, le=280)
    weight_kg: float | None = Field(default=None, gt=0, le=400)
    blood_group: str | None = Field(default=None, max_length=8)
    diet_type: DietType = DietType.VEG
    smoker: bool = False
    alcohol: bool = False


class ProfileCreate(ProfileBase):
    """Onboarding wizard payload: profile plus the three related lists."""

    conditions: list[ConditionIn] = []
    allergies: list[AllergyIn] = []
    medications: list[MedicationIn] = []


class ProfileUpdate(ProfileBase):
    pass


class ProfileOut(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    conditions: list[ConditionOut] = []
    allergies: list[AllergyOut] = []
    medications: list[MedicationOut] = []
