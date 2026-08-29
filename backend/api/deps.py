"""Shared FastAPI dependencies."""
from typing import TypeVar

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import PatientProfile, User
from security import decode_access_token

T = TypeVar("T")

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, int(subject))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientProfile:
    """Require a completed profile. Consultations are meaningless without one."""
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No patient profile yet. Complete onboarding first.",
        )
    return profile


def owned_or_404(
    db: Session, model: type[T], row_id: int, profile: PatientProfile, label: str
) -> T:
    """Fetch a row that must belong to this patient, or 404.

    This ownership test is the only thing stopping one patient reading
    another's consultation, document or profile row by guessing an id. It was
    written out longhand at eight call sites, and a check that is copy-pasted
    is one that eventually gets missed on a new endpoint -- silently, because
    the endpoint still works, just for everybody.

    404 and not 403: 403 would confirm the row exists, which is the fact being
    protected.
    """
    row = db.get(model, row_id)
    if row is None or row.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found"
        )
    return row
