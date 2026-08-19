from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_profile, get_current_user
from database import get_db
from models import (
    PatientAllergy,
    PatientCondition,
    PatientMedication,
    PatientProfile,
    User,
)
from models.enums import Provenance
from schemas.profile import (
    AllergyIn,
    AllergyOut,
    ConditionIn,
    ConditionOut,
    MedicationIn,
    MedicationOut,
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_condition(profile_id: int, item: ConditionIn) -> PatientCondition:
    return PatientCondition(
        profile_id=profile_id,
        condition_name=item.condition_name.strip(),
        status=item.status,
        onset_date=item.onset_date,
        provenance=Provenance.USER_ENTERED,
        confirmed_at=_now(),
    )


def _new_allergy(profile_id: int, item: AllergyIn) -> PatientAllergy:
    return PatientAllergy(
        profile_id=profile_id,
        allergen=item.allergen.strip(),
        allergen_class=item.allergen_class,
        reaction=item.reaction,
        severity=item.severity,
        provenance=Provenance.USER_ENTERED,
        confirmed_at=_now(),
    )


def _new_medication(profile_id: int, item: MedicationIn) -> PatientMedication:
    if not (item.brand_name or item.generic_name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A medication needs at least a brand name or a generic name",
        )
    return PatientMedication(
        profile_id=profile_id,
        brand_name=item.brand_name,
        generic_name=item.generic_name,
        dose=item.dose,
        frequency=item.frequency,
        route=item.route,
        reason=item.reason,
        start_date=item.start_date,
        status=item.status,
        provenance=Provenance.USER_ENTERED,
        confirmed_at=_now(),
    )


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientProfile:
    """Onboarding wizard submit. One user, one profile."""
    if db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Profile already exists"
        )

    profile = PatientProfile(
        user_id=user.id,
        **payload.model_dump(exclude={"conditions", "allergies", "medications"}),
    )
    db.add(profile)
    db.flush()

    for c in payload.conditions:
        db.add(_new_condition(profile.id, c))
    for a in payload.allergies:
        db.add(_new_allergy(profile.id, a))
    for m in payload.medications:
        db.add(_new_medication(profile.id, m))

    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=ProfileOut)
def read_profile(profile: PatientProfile = Depends(get_current_profile)) -> PatientProfile:
    return profile


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PatientProfile:
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


# --- conditions -------------------------------------------------------------

@router.post("/conditions", response_model=ConditionOut, status_code=status.HTTP_201_CREATED)
def add_condition(
    payload: ConditionIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PatientCondition:
    row = _new_condition(profile.id, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/conditions/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_condition(
    item_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PatientCondition, item_id)
    if row is None or row.profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")
    db.delete(row)
    db.commit()


# --- allergies --------------------------------------------------------------

@router.post("/allergies", response_model=AllergyOut, status_code=status.HTTP_201_CREATED)
def add_allergy(
    payload: AllergyIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PatientAllergy:
    row = _new_allergy(profile.id, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/allergies/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_allergy(
    item_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PatientAllergy, item_id)
    if row is None or row.profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allergy not found")
    db.delete(row)
    db.commit()


# --- medications ------------------------------------------------------------

@router.post("/medications", response_model=MedicationOut, status_code=status.HTTP_201_CREATED)
def add_medication(
    payload: MedicationIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> PatientMedication:
    row = _new_medication(profile.id, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/medications/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(
    item_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PatientMedication, item_id)
    if row is None or row.profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")
    db.delete(row)
    db.commit()
