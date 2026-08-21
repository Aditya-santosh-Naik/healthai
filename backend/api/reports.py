"""PDF export."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.deps import get_current_profile
from api.history import get_detail
from audit.logger import log_event
from database import get_db
from models import Consultation, PatientProfile, PdfReport
from reports.pdf import build_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{consultation_id}.pdf")
def download_report(
    consultation_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Render a consultation as a PDF.

    Built from the stored structured rows, so the PDF matches what was decided
    at the time. The LLM is not called again.
    """
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found"
        )

    detail = get_detail(consultation_id, profile, db)
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    data = build_report(
        detail.model_dump(), patient_name=profile.name, generated_at=generated_at
    )

    db.add(
        PdfReport(
            consultation_id=consultation.id,
            filepath=f"healthai_consultation_{consultation.id}.pdf",
        )
    )
    log_event(
        db,
        event_type="report.generated",
        consultation_id=consultation.id,
        payload={"bytes": len(data), "generated_at": generated_at},
        commit=False,
    )
    db.commit()

    filename = f"healthai_consultation_{consultation.id}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
