"""Consultation endpoints. Pipeline step 11: persist, audit, render.

The reasoning lives in core.pipeline; this module only moves data between it
and the database.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_profile
from audit.logger import log_event
from core import diet_lifestyle, knowledge
from core.followup_engine import apply_answer
from core.patient_context import from_profile
from core.pipeline import Outcome, build_doctor_summary, run, visible_symptoms
from core.symptom_extraction import ExtractedSymptom
from database import get_db
from main import DISCLAIMER
from models import (
    CandidateEvidence,
    Consultation,
    ConsultationSymptom,
    Feedback,
    MedicationSafetyResult,
    Message,
    PatientProfile,
    RagRetrieval,
    Recommendation,
)
from models.enums import ConsultationStatus, MessageRole
from schemas.consultation import (
    AnswerIn,
    CandidateOut,
    DietOut,
    EscalationOut,
    EvidenceOut,
    FeedbackIn,
    GeneralInfoOut,
    MedicationGuidanceOut,
    MedicationSafetyOut,
    MessageIn,
    RefusalOut,
    QuestionOut,
    SafetyFindingOut,
    SymptomOut,
    TreatmentNoteOut,
    TurnOut,
)

router = APIRouter(prefix="/api/consultation", tags=["consultation"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_consultation(db: Session, profile: PatientProfile, consultation_id: int) -> Consultation:
    consultation = db.get(Consultation, consultation_id)
    if consultation is None or consultation.profile_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found"
        )
    return consultation


def _load_symptoms(db: Session, consultation_id: int) -> list[ExtractedSymptom]:
    rows = (
        db.query(ConsultationSymptom)
        .filter(ConsultationSymptom.consultation_id == consultation_id)
        .all()
    )
    return [
        ExtractedSymptom(
            code=r.symptom_code,
            # bool(None) is False, which would turn an unknown into a denial.
            present=None if r.present is None else bool(r.present),
            duration_hours=r.duration_hours,
            severity=r.severity,
            matched_text=r.source,
        )
        for r in rows
    ]


def _save_symptoms(
    db: Session, consultation_id: int, symptoms: list[ExtractedSymptom]
) -> None:
    """Replace the stored symptom set with the merged one."""
    db.query(ConsultationSymptom).filter(
        ConsultationSymptom.consultation_id == consultation_id
    ).delete()
    for s in symptoms:
        db.add(
            ConsultationSymptom(
                consultation_id=consultation_id,
                symptom_code=s.code,
                present=s.present,
                duration_hours=s.duration_hours,
                severity=s.severity,
                source="answered" if s.matched_text.startswith("answered") else "stated",
            )
        )


def _clear_derived(db: Session, consultation_id: int) -> None:
    """Derived rows are rebuilt every turn; stale ones must not survive."""
    for model in (CandidateEvidence, MedicationSafetyResult, RagRetrieval, Recommendation):
        db.query(model).filter(model.consultation_id == consultation_id).delete()


def _persist_result(db: Session, consultation: Consultation, result) -> None:
    """Write the full structured assessment for audit and history."""
    _clear_derived(db, consultation.id)

    for candidate in result.all_candidates:
        db.add(
            CandidateEvidence(
                consultation_id=consultation.id,
                condition_code=candidate.code,
                band=candidate.band,
                supporting_json=[e.display for e in candidate.supporting],
                missing_json=[e.display for e in candidate.missing],
                contradictory_json=[e.display for e in candidate.contradictory],
                hallmark_present=candidate.hallmark_present,
                context_factors_json=candidate.context_factors,
                internal_score=candidate.score,
            )
        )

    if result.safety:
        for finding in result.safety.findings:
            db.add(
                MedicationSafetyResult(
                    consultation_id=consultation.id,
                    subject_drug=finding.subject_drug,
                    related_drug_or_condition=finding.related,
                    severity=finding.severity,
                    reason=finding.reason,
                    source_url=finding.source_url,
                )
            )
        # Record that the check RAN and found nothing, so history can rebuild
        # the no-known-conflict state rather than showing an empty section.
        if not result.safety.findings and result.safety.checked_medicines:
            db.add(
                MedicationSafetyResult(
                    consultation_id=consultation.id,
                    subject_drug=", ".join(result.safety.checked_medicines),
                    related_drug_or_condition=None,
                    severity="none",
                    reason="No known conflict found for these medicines.",
                    source_url=None,
                )
            )

    for passage in result.passages:
        db.add(
            RagRetrieval(
                consultation_id=consultation.id,
                chunk_id=passage.chunk_id,
                source_name=passage.source_name,
                source_url=passage.source_url,
                score=passage.score,
            )
        )

    if result.diet:
        for rec in result.diet.recommendations:
            db.add(
                Recommendation(
                    consultation_id=consultation.id,
                    category=rec.category,
                    text=rec.text,
                )
            )


def _to_turn(consultation: Consultation, profile: PatientProfile, result) -> TurnOut:
    """Map a PipelineResult onto the wire format."""
    turn = TurnOut(
        consultation_id=consultation.id,
        status=consultation.status,
        outcome=result.outcome,
        narrative=result.narrative,
        disclaimer=DISCLAIMER,
        # The consultation row is authoritative: the pipeline's copy is the
        # pre-increment value, which rendered as "Question 0".
        questions_asked=consultation.questions_asked,
        sufficiency_reason=result.sufficiency_reason,
        used_fallback=result.used_fallback,
        llm_seconds=round(result.llm_seconds, 1),
        sources=result.sources,
    )

    if result.outcome == Outcome.REFUSED:
        turn.refusal = RefusalOut(
            category=result.refusal_category or "",
            message=result.refusal_message,
            referral=result.refusal_referral,
            resources=result.refusal_resources,
        )
        return turn

    turn.symptoms = [
        SymptomOut(
            code=s.code, display=knowledge.display_name(s.code), present=s.present
        )
        for s in visible_symptoms(result.symptoms)
    ]

    if result.outcome == Outcome.ESCALATED:
        turn.escalation = EscalationOut(
            urgency=result.escalation_urgency,
            reason=result.escalation_reason,
            action=result.escalation_action,
            triggered_by=result.escalation_triggered_by,
            source_url=result.escalation_source_url,
        )
        return turn

    if result.outcome == Outcome.NEEDS_QUESTION and result.question:
        q = result.question
        turn.question = QuestionOut(
            symptom_code=q.symptom_code,
            text=q.text,
            options=q.options,
            kind=q.kind,
            rationale=q.rationale,
        )
        return turn

    # Completed assessment.
    turn.band = result.band
    turn.candidates = [
        CandidateOut(
            code=c.code,
            display_name=c.display_name,
            band=c.band,
            evidence=EvidenceOut(
                supporting=[e.display for e in c.supporting],
                missing=[e.display for e in c.missing],
                contradictory=[e.display for e in c.contradictory],
            ),
            context_factors=c.context_factors,
            sources=c.sources,
        )
        for c in result.candidates
    ]

    turn.ruled_out = [
        CandidateOut(
            code=c.code,
            display_name=c.display_name,
            band=c.band,
            evidence=EvidenceOut(
                supporting=[e.display for e in c.supporting],
                missing=[e.display for e in c.missing],
                contradictory=[e.display for e in c.contradictory],
            ),
            context_factors=c.context_factors,
            sources=c.sources,
        )
        for c in result.ruled_out
    ]

    if result.safety:
        turn.medication_safety = MedicationSafetyOut(
            overall=result.safety.overall,
            findings=[
                SafetyFindingOut(
                    subject_drug=f.subject_drug,
                    related=f.related,
                    severity=f.severity,
                    reason=f.reason,
                    source_url=f.source_url,
                    kind=f.kind,
                )
                for f in result.safety.findings
            ],
            checked_medicines=result.safety.checked_medicines,
            unrecognised=result.safety.unrecognised,
        )

    if result.guidance:
        turn.medication_guidance = MedicationGuidanceOut(
            avoid=[a.text for a in result.guidance.avoid],
            general_info=[
                GeneralInfoOut(
                    display=g.display,
                    used_for=g.used_for,
                    caveat=g.caveat,
                    source_url=g.source_url,
                )
                for g in result.guidance.general_info
            ],
            treatment=[
                TreatmentNoteOut(
                    condition_display=t.condition_display,
                    needs_prescription=t.needs_prescription,
                    self_limiting=t.self_limiting,
                    summary=t.summary,
                    source_url=t.source_url,
                )
                for t in result.guidance.treatment
            ],
            needs_doctor_prescription=result.guidance.needs_doctor_prescription,
        )

    if result.diet:
        C = diet_lifestyle.Category
        turn.diet = DietOut(
            prefer=result.diet.by_category(C.DIET_PREFER),
            avoid=result.diet.by_category(C.DIET_AVOID),
            hydration=result.diet.by_category(C.HYDRATION),
            lifestyle=result.diet.by_category(C.LIFESTYLE),
            monitor=result.diet.by_category(C.MONITOR),
            warning_signs=result.diet.by_category(C.WARNING_SIGN),
        )

    durations = [
        s.duration_hours for s in result.symptoms if s.present and s.duration_hours
    ]
    turn.doctor_summary = build_doctor_summary(
        from_profile(profile),
        result.symptoms,
        result.candidates,
        max(durations) if durations else None,
    )
    return turn


def _advance(
    db: Session,
    consultation: Consultation,
    profile: PatientProfile,
    text: str,
    extra_symptoms: list[ExtractedSymptom] | None = None,
) -> TurnOut:
    """Run one turn and persist everything it produced."""
    facts = from_profile(profile)
    prior = _load_symptoms(db, consultation.id) + (extra_symptoms or [])

    result = run(
        text=text,
        facts=facts,
        prior_symptoms=prior,
        questions_asked=consultation.questions_asked,
    )

    if result.outcome == Outcome.REFUSED:
        consultation.status = ConsultationStatus.REFUSED
        consultation.completed_at = _now()
        consultation.escalation_reason = result.refusal_message
    elif result.outcome == Outcome.ESCALATED:
        consultation.status = ConsultationStatus.ESCALATED
        consultation.completed_at = _now()
        consultation.escalation_reason = result.escalation_reason
        _save_symptoms(db, consultation.id, result.symptoms)
    elif result.outcome == Outcome.NEEDS_QUESTION:
        consultation.status = ConsultationStatus.IN_PROGRESS
        consultation.questions_asked += 1
        _save_symptoms(db, consultation.id, result.symptoms)
    else:
        consultation.status = ConsultationStatus.COMPLETE
        consultation.completed_at = _now()
        consultation.outcome_band = result.band
        consultation.llm_raw_output = result.narrative
        _save_symptoms(db, consultation.id, result.symptoms)
        _persist_result(db, consultation, result)

    if result.narrative:
        db.add(
            Message(
                consultation_id=consultation.id,
                role=MessageRole.ASSISTANT,
                content=result.question.text if result.question else result.narrative,
            )
        )

    # Invariant 12: audit every AI-generated output with its inputs and sources.
    log_event(
        db,
        event_type=f"pipeline.{result.outcome}",
        consultation_id=consultation.id,
        payload={
            "input": text,
            "outcome": result.outcome,
            "band": result.band,
            "assessment": result.assessment_payload,
            "retrieved_sources": [
                {"chunk": p.chunk_id, "source": p.source_url, "score": round(p.score, 3)}
                for p in result.passages
            ],
            "llm_used_fallback": result.used_fallback,
            "llm_error": result.llm_error,
            "llm_seconds": round(result.llm_seconds, 2),
        },
        commit=False,
    )

    db.commit()
    db.refresh(consultation)
    return _to_turn(consultation, profile, result)


@router.post("/start", response_model=TurnOut, status_code=status.HTTP_201_CREATED)
def start(
    payload: MessageIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TurnOut:
    """Begin a consultation with the patient's opening description."""
    consultation = Consultation(
        profile_id=profile.id, status=ConsultationStatus.IN_PROGRESS
    )
    db.add(consultation)
    db.flush()
    db.add(
        Message(
            consultation_id=consultation.id,
            role=MessageRole.USER,
            content=payload.text,
        )
    )
    return _advance(db, consultation, profile, payload.text)


@router.post("/{consultation_id}/message", response_model=TurnOut)
def send_message(
    consultation_id: int,
    payload: MessageIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TurnOut:
    consultation = _get_consultation(db, profile, consultation_id)
    if consultation.status != ConsultationStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation has already finished. Start a new one.",
        )
    db.add(
        Message(
            consultation_id=consultation.id,
            role=MessageRole.USER,
            content=payload.text,
        )
    )
    return _advance(db, consultation, profile, payload.text)


@router.post("/{consultation_id}/answer", response_model=TurnOut)
def answer_question(
    consultation_id: int,
    payload: AnswerIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TurnOut:
    """Apply a tapped answer to a follow-up question.

    'Not sure' records nothing: an unknown is not a denial, and storing it as
    one would be a silent fabrication.
    """
    consultation = _get_consultation(db, profile, consultation_id)
    if consultation.status != ConsultationStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation has already finished. Start a new one.",
        )

    db.add(
        Message(
            consultation_id=consultation.id,
            role=MessageRole.USER,
            content=payload.answer,
        )
    )
    answered = apply_answer(payload.symptom_code, payload.answer)
    return _advance(
        db, consultation, profile, "", [answered] if answered else []
    )


@router.post("/{consultation_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def submit_feedback(
    consultation_id: int,
    payload: FeedbackIn,
    profile: PatientProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    consultation = _get_consultation(db, profile, consultation_id)
    db.add(Feedback(consultation_id=consultation.id, helpful=payload.helpful))
    db.commit()
