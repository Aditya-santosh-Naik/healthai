from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.enums import (
    ConditionStatus,
    DietType,
    MedicationStatus,
    Provenance,
    Sex,
)

# Age bounds are a data-integrity check, not the clinical one.
#
# 122 is the oldest verified human lifespan on record (Jeanne Calment,
# 1875-1997, 122 years 164 days). Anything above it is a typo or a probe, not a
# patient. The floor of 1 rejects 0 and negatives while still admitting a real
# person.
#
# **Under-18 is still refused**, at the scope guard, on every consultation --
# see core/scope_guard.MIN_ADULT_AGE. The refusal moved rather than
# disappeared: a 15-year-old can now hold a profile but gets a clear
# explanation and a paediatric referral when they try to consult, instead of an
# opaque 422 at signup that never says why. The clinical rule is enforced where
# clinical rules belong.
MIN_AGE = 1
MAX_AGE = 122

# Human range, generously bounded. A 0.4 kg patient is a decimal-point error,
# and letting it through skews any weight-based reasoning built on it later.
MIN_HEIGHT_CM = 30.0
MAX_HEIGHT_CM = 280.0
MIN_WEIGHT_KG = 2.0
MAX_WEIGHT_KG = 400.0

# The eight ABO/Rh groups. Free text here becomes free text on a document a
# doctor might read.
BLOOD_GROUP_PATTERN = r"^(?:A|B|AB|O)[+-]$"

# Nobody has 200 concurrent conditions. A cap keeps one request from writing
# unbounded rows.
MAX_LIST_ITEMS = 50


def _no_future_date(value: date | None) -> date | None:
    """Onset and start dates describe what has already happened."""
    if value is not None and value > date.today():
        raise ValueError("date cannot be in the future")
    return value


def _meaningful_text(value: str) -> str:
    """Reject whitespace-only input that min_length alone lets through."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


class ConditionIn(BaseModel):
    condition_name: str = Field(min_length=1, max_length=120)
    status: ConditionStatus = ConditionStatus.ACTIVE
    onset_date: date | None = None

    _clean_name = field_validator("condition_name")(_meaningful_text)
    _past_onset = field_validator("onset_date")(_no_future_date)


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

    _clean_allergen = field_validator("allergen")(_meaningful_text)


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

    _past_start = field_validator("start_date")(_no_future_date)

    @model_validator(mode="after")
    def _must_name_a_medicine(self):
        """A row with neither name cannot be resolved, checked or displayed.

        It would sit in the profile looking like a recorded medicine while
        contributing nothing to the interaction check -- worse than absent,
        because the safety block would claim to have checked it.
        """
        if not (self.brand_name or "").strip() and not (self.generic_name or "").strip():
            raise ValueError("give either a brand name or a generic name")
        return self


class MedicationOut(MedicationIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provenance: Provenance
    confirmed_at: datetime | None = None


class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=MIN_AGE, le=MAX_AGE)
    sex: Sex
    height_cm: float | None = Field(default=None, ge=MIN_HEIGHT_CM, le=MAX_HEIGHT_CM)
    weight_kg: float | None = Field(default=None, ge=MIN_WEIGHT_KG, le=MAX_WEIGHT_KG)
    blood_group: str | None = Field(default=None, pattern=BLOOD_GROUP_PATTERN)
    diet_type: DietType = DietType.VEG
    smoker: bool = False
    alcohol: bool = False

    _clean_name = field_validator("name")(_meaningful_text)

    @field_validator("blood_group", mode="before")
    @classmethod
    def _normalise_blood_group(cls, value):
        # mode="before" on purpose: the pattern constraint runs first
        # otherwise, and "b+" would be rejected before it could be upcased.
        # "b+" and "B+" are the same group; store one spelling.
        return value.strip().upper() if isinstance(value, str) else value


class ProfileCreate(ProfileBase):
    """Onboarding wizard payload: profile plus the three related lists."""

    conditions: list[ConditionIn] = Field(default=[], max_length=MAX_LIST_ITEMS)
    allergies: list[AllergyIn] = Field(default=[], max_length=MAX_LIST_ITEMS)
    medications: list[MedicationIn] = Field(default=[], max_length=MAX_LIST_ITEMS)


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
