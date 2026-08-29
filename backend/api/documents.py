"""Document upload and the confirm-before-store flow.

Acceptance test 6: a PDF is uploaded, facts are extracted, they are shown for
confirmation, and ONLY THEN are they written to the profile with provenance
document_extracted_confirmed. AI-inferred data never silently becomes profile
truth.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from api.deps import get_current_profile, owned_or_404
from audit.logger import log_event
from config import UPLOAD_DIR
from core import knowledge
from database import get_db
from documents.extractor import extract_text
from documents.medical_parser import parse
from models import (
    ExtractedFact,
    MedicalDocument,
    PatientAllergy,
    PatientCondition,
    PatientMedication,
    PatientProfile,
)
from models.enums import ExtractionStatus, Provenance, ReviewStatus

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_PAGES = 30


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fact_type: str
    fact_value: str
    confidence: float | None
    page_ref: int | None
    review_status: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_at: datetime
    extraction_status: str
    page_count: int | None
    message: str = ""
    facts: list[FactOut] = []


class ConfirmIn(BaseModel):
    fact_ids: list[int] = []
    rejected_ids: list[int] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> DocumentOut:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported.",
        )

    # Read in chunks and stop at the limit. `await file.read()` with no
    # argument buffers the WHOLE upload into memory before the size is
    # checked, so the 10 MB limit only ever applied after the damage was done
    # -- a single multi-gigabyte POST could exhaust RAM and take the process
    # down, without needing to authenticate as anyone in particular.
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="That file is larger than 10 MB.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    stored_name = f"{uuid.uuid4().hex}.pdf"
    path: Path = UPLOAD_DIR / stored_name
    path.write_bytes(data)

    document = MedicalDocument(
        profile_id=profile.id,
        filename=file.filename or stored_name,
        filepath=str(path),
        extraction_status=ExtractionStatus.PENDING,
    )
    db.add(document)
    db.flush()

    outcome = extract_text(path)
    document.page_count = outcome.page_count

    message = outcome.message
    facts: list[ExtractedFact] = []

    if outcome.status == "complete":
        if outcome.page_count > MAX_PAGES:
            document.extraction_status = ExtractionStatus.FAILED
            message = f"This document has more than {MAX_PAGES} pages."
        else:
            document.extraction_status = ExtractionStatus.COMPLETE
            for candidate in parse(outcome.pages or []):
                row = ExtractedFact(
                    document_id=document.id,
                    fact_type=candidate.fact_type,
                    fact_value=candidate.fact_value,
                    confidence=candidate.confidence,
                    page_ref=candidate.page_ref,
                    review_status=ReviewStatus.PENDING,
                )
                db.add(row)
                facts.append(row)
            if not facts:
                message = (
                    "No recognisable conditions, allergies or medicines were "
                    "found. You can still add them manually on your profile."
                )
    elif outcome.status == "no_text_layer":
        document.extraction_status = ExtractionStatus.NO_TEXT_LAYER
    else:
        document.extraction_status = ExtractionStatus.FAILED

    log_event(
        db,
        event_type="document.extracted",
        payload={
            "document_id": document.id,
            "status": document.extraction_status,
            "pages": document.page_count,
            "candidate_facts": len(facts),
        },
        commit=False,
    )
    db.commit()
    db.refresh(document)

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        uploaded_at=document.uploaded_at,
        extraction_status=document.extraction_status,
        page_count=document.page_count,
        message=message,
        facts=[FactOut.model_validate(f) for f in document.facts],
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    documents = (
        db.query(MedicalDocument)
        .filter(MedicalDocument.profile_id == profile.id)
        .order_by(MedicalDocument.uploaded_at.desc())
        .all()
    )
    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            uploaded_at=d.uploaded_at,
            extraction_status=d.extraction_status,
            page_count=d.page_count,
            facts=[FactOut.model_validate(f) for f in d.facts],
        )
        for d in documents
    ]


@router.post("/{document_id}/confirm", response_model=DocumentOut)
def confirm_facts(
    document_id: int,
    payload: ConfirmIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """Write confirmed facts to the profile. This is the only path in."""
    document = owned_or_404(db, MedicalDocument, document_id, profile, "Document")

    owned = {f.id: f for f in document.facts}
    unknown = (set(payload.fact_ids) | set(payload.rejected_ids)) - set(owned)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown fact ids: {sorted(unknown)}",
        )

    for fact_id in payload.rejected_ids:
        owned[fact_id].review_status = ReviewStatus.REJECTED

    for fact_id in payload.fact_ids:
        fact = owned[fact_id]
        if fact.review_status == ReviewStatus.CONFIRMED:
            continue
        fact.review_status = ReviewStatus.CONFIRMED

        if fact.fact_type == "condition":
            db.add(
                PatientCondition(
                    profile_id=profile.id,
                    condition_name=fact.fact_value,
                    status="active",
                    provenance=Provenance.DOCUMENT_EXTRACTED_CONFIRMED,
                    source_document_id=document.id,
                    confirmed_at=_now(),
                )
            )
        elif fact.fact_type == "allergy":
            drug = knowledge.resolve_drug(fact.fact_value)
            db.add(
                PatientAllergy(
                    profile_id=profile.id,
                    allergen=fact.fact_value,
                    allergen_class=drug.drug_class if drug else None,
                    provenance=Provenance.DOCUMENT_EXTRACTED_CONFIRMED,
                    confirmed_at=_now(),
                )
            )
        elif fact.fact_type == "medication":
            drug = knowledge.resolve_drug(fact.fact_value.split()[0])
            db.add(
                PatientMedication(
                    profile_id=profile.id,
                    brand_name=fact.fact_value,
                    generic_name=drug.generic if drug else None,
                    status="prescribed_taking",
                    provenance=Provenance.DOCUMENT_EXTRACTED_CONFIRMED,
                    confirmed_at=_now(),
                )
            )

    log_event(
        db,
        event_type="document.facts_confirmed",
        payload={
            "document_id": document.id,
            "confirmed": payload.fact_ids,
            "rejected": payload.rejected_ids,
        },
        commit=False,
    )
    db.commit()
    db.refresh(document)

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        uploaded_at=document.uploaded_at,
        extraction_status=document.extraction_status,
        page_count=document.page_count,
        facts=[FactOut.model_validate(f) for f in document.facts],
    )
