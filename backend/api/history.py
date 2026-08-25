"""Consultation history.

Past consultations are history, never auto-promoted to medical fact
(spec section 15).
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_profile
from core import knowledge
from database import get_db
from main import DISCLAIMER
from models import (
    CandidateEvidence,
    Consultation,
    ConsultationSymptom,
    MedicationSafetyResult,
    Message,
    PatientProfile,
    RagRetrieval,
    Recommendation,
)
from models.enums import ConsultationStatus
from schemas.consultation import (
    CandidateOut,
    DietOut,
    EvidenceOut,
    HistoryDetail,
    HistoryItem,
    MedicationSafetyOut,
    MessageOut,
    SafetyFindingOut,
    SymptomOut,
)

router = APIRouter(prefix="/api/history", tags=["history"])

STATUS_SUMMARY = {
    ConsultationStatus.ESCALATED: "Urgent care advised",
    ConsultationStatus.REFUSED: "Out of scope - referred elsewhere",
    ConsultationStatus.IN_PROGRESS: "Not finished",
}

BAND_SUMMARY = {
    "most_consistent": "Most consistent with {name}",
    "possible": "{name} considered possible",
    "less_consistent": "No strong match",
    "insufficient_information": "Not enough information to assess",
}


def _summary(db: Session, consultation: Consultation) -> str:
    if consultation.status in STATUS_SUMMARY:
        return STATUS_SUMMARY[consultation.status]

    top = (
        db.query(CandidateEvidence)
        .filter(CandidateEvidence.consultation_id == consultation.id)
        .order_by(CandidateEvidence.internal_score.desc())
        .first()
    )
    band = consultation.outcome_band or "insufficient_information"
    template = BAND_SUMMARY.get(band, "Assessment complete")
    if top is None:
        return template.replace("{name}", "").strip() or "Assessment complete"
    condition = knowledge.conditions().get(top.condition_code)
    name = condition.display_name if condition else top.condition_code
    return template.format(name=name)


@router.get("", response_model=list[HistoryItem])
def list_history(
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    rows = (
        db.query(Consultation)
        .filter(Consultation.profile_id == profile.id)
        .order_by(Consultation.started_at.desc())
        .all()
    )
    return [
        HistoryItem(
            id=c.id,
            started_at=c.started_at,
            completed_at=c.completed_at,
            status=c.status,
            outcome_band=c.outcome_band,
            summary=_summary(db, c),
        )
        for c in rows
    ]


@router.get("/{consultation_id}", response_model=HistoryDetail)
def get_detail(
    consultation_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> HistoryDetail:
    """Rebuild a past consultation from the stored structured rows.

    Nothing is recomputed and the LLM is not called again; this is what was
    actually decided at the time.
    """
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found"
        )

    evidence = (
        db.query(CandidateEvidence)
        .filter(CandidateEvidence.consultation_id == consultation.id)
        .order_by(CandidateEvidence.internal_score.desc())
        .all()
    )
    shown = [e for e in evidence if e.band in ("most_consistent", "possible")][:3]

    candidates = []
    for row in shown:
        condition = knowledge.conditions().get(row.condition_code)
        candidates.append(
            CandidateOut(
                code=row.condition_code,
                display_name=condition.display_name if condition else row.condition_code,
                band=row.band,
                evidence=EvidenceOut(
                    supporting=json.loads(row.supporting_json),
                    missing=json.loads(row.missing_json),
                    contradictory=json.loads(row.contradictory_json),
                ),
                context_factors=json.loads(row.context_factors_json),
                sources=[dict(s) for s in condition.sources] if condition else [],
            )
        )

    safety_rows = (
        db.query(MedicationSafetyResult)
        .filter(MedicationSafetyResult.consultation_id == consultation.id)
        .all()
    )
    safety = None
    if safety_rows:
        order = {"avoid": 2, "caution": 1, "none": 0}
        overall = max((r.severity for r in safety_rows), key=lambda s: order.get(s, 0))
        # A "none" row is the record that the check ran and found nothing; it
        # names the medicines checked rather than describing a problem.
        real = [r for r in safety_rows if r.severity != "none"]
        checked = [
            m.strip()
            for r in safety_rows
            if r.severity == "none"
            for m in r.subject_drug.split(",")
        ]
        safety = MedicationSafetyOut(
            overall=overall,
            checked_medicines=checked,
            findings=[
                SafetyFindingOut(
                    subject_drug=r.subject_drug,
                    related=r.related_drug_or_condition,
                    severity=r.severity,
                    reason=r.reason,
                    source_url=r.source_url or "",
                    kind="stored",
                )
                for r in real
            ],
        )

    recs = (
        db.query(Recommendation)
        .filter(Recommendation.consultation_id == consultation.id)
        .all()
    )

    def by_category(category: str) -> list[str]:
        return [r.text for r in recs if r.category == category]

    diet = (
        DietOut(
            prefer=by_category("diet_prefer"),
            avoid=by_category("diet_avoid"),
            hydration=by_category("hydration"),
            lifestyle=by_category("lifestyle"),
            monitor=by_category("monitor"),
            warning_signs=by_category("warning_sign"),
        )
        if recs
        else None
    )

    symptoms = (
        db.query(ConsultationSymptom)
        .filter(ConsultationSymptom.consultation_id == consultation.id)
        .all()
    )
    messages = (
        db.query(Message)
        .filter(Message.consultation_id == consultation.id)
        .order_by(Message.created_at)
        .all()
    )
    retrievals = (
        db.query(RagRetrieval)
        .filter(RagRetrieval.consultation_id == consultation.id)
        .all()
    )

    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    for r in retrievals:
        key = r.source_url or r.source_name
        if key not in seen:
            seen.add(key)
            sources.append({"name": r.source_name, "url": r.source_url or ""})

    return HistoryDetail(
        consultation_id=consultation.id,
        status=consultation.status,
        outcome=consultation.status,
        narrative=consultation.llm_raw_output or consultation.escalation_reason or "",
        disclaimer=DISCLAIMER,
        band=consultation.outcome_band,
        started_at=consultation.started_at,
        completed_at=consultation.completed_at,
        questions_asked=consultation.questions_asked,
        symptoms=[
            SymptomOut(
                code=s.symptom_code,
                display=knowledge.display_name(s.symptom_code),
                present=bool(s.present),
            )
            for s in symptoms
        ],
        candidates=candidates,
        medication_safety=safety,
        diet=diet,
        sources=sources,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.delete("/{consultation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_consultation(
    consultation_id: int,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found"
        )
    db.delete(consultation)
    db.commit()
