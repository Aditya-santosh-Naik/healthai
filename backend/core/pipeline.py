"""The full assessment pipeline, steps 0 through 10.

One function, in spec order, with the short-circuits where the spec puts them.
Everything before the LLM call is deterministic; the LLM only rephrases what
this module has already decided.

Persistence and audit (step 11) belong to the API layer, not here, so this
stays testable without a database.
"""
from dataclasses import dataclass, field
from typing import Any

from core import diet_lifestyle, knowledge, medication_guidance, medication_safety
from core import red_flags as red_flag_check
from core import scope_guard
from core.evidence_engine import (
    Band,
    CandidateResult,
    evaluate,
    ruled_out as compute_ruled_out,
    top_candidates,
)
from core.followup_engine import Question, next_question
from core.patient_context import ProfileFacts
from core.sufficiency import assess as assess_sufficiency
from core.symptom_extraction import ExtractedSymptom, extract
from llm import client as llm_client
from llm import fallback, prompts
from rag import retriever


class Outcome:
    REFUSED = "refused"
    ESCALATED = "escalated"
    NEEDS_QUESTION = "needs_question"
    COMPLETE = "complete"


@dataclass
class PipelineResult:
    outcome: str
    band: str = Band.INSUFFICIENT

    # Refusal (step 0)
    refusal_category: str | None = None
    refusal_message: str = ""
    refusal_referral: str = ""
    refusal_resources: list[str] = field(default_factory=list)

    # Escalation (step 1)
    escalation_code: str | None = None
    escalation_urgency: str = ""
    escalation_reason: str = ""
    escalation_action: str = ""
    escalation_triggered_by: list[str] = field(default_factory=list)
    escalation_source_url: str = ""

    # Follow-up (step 6)
    question: Question | None = None
    questions_asked: int = 0
    sufficiency_reason: str = ""

    # Assessment (steps 2-9)
    symptoms: list[ExtractedSymptom] = field(default_factory=list)
    candidates: list[CandidateResult] = field(default_factory=list)
    all_candidates: list[CandidateResult] = field(default_factory=list)
    ruled_out: list[CandidateResult] = field(default_factory=list)
    safety: medication_safety.SafetyReport | None = None
    guidance: medication_guidance.MedicationGuidance | None = None
    diet: diet_lifestyle.GuidancePlan | None = None
    passages: list[retriever.RetrievedPassage] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)

    # Narration (step 10)
    narrative: str = ""
    used_fallback: bool = False
    llm_error: str | None = None
    llm_seconds: float = 0.0

    # For the audit log.
    assessment_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def doctor_summary(self) -> str:
        return ""


def visible_symptoms(symptoms: list[ExtractedSymptom]) -> list[ExtractedSymptom]:
    """Drop implied parents when the more specific symptom is also present.

    The evidence engine needs both "high fever" and the "fever" it entails, but
    showing a patient both reads as duplication.
    """
    present = {s.code for s in symptoms if s.present is True}
    implied_by_others = {
        parent
        for code in present
        for parent in knowledge.implications().get(code, ())
        if parent in present
    }
    return [s for s in symptoms if not (s.present is True and s.code in implied_by_others)]


def _duration_text(hours: float | None) -> str:
    if hours is None:
        return ""
    if hours < 24:
        return f"about {int(round(hours))} hour{'s' if round(hours) != 1 else ''}"
    days = hours / 24
    if days < 14:
        return f"about {days:.0f} day{'s' if round(days) != 1 else ''}"
    return f"about {days / 7:.0f} weeks"


def build_doctor_summary(
    facts: ProfileFacts,
    symptoms: list[ExtractedSymptom],
    candidates: list[CandidateResult],
    duration_hours: float | None,
) -> str:
    """The 'what to tell your doctor' block: a short clinical handover.

    Spec section 14 calls this the single most useful output in the product.
    """
    shown = visible_symptoms(symptoms)
    present = [knowledge.display_name(s.code) for s in shown if s.present is True]
    denied = [knowledge.display_name(s.code) for s in shown if s.present is False]

    lines = [f"{facts.age}-year-old {facts.sex}." if facts.age else ""]
    if present:
        line = f"Reports: {', '.join(present)}."
        if duration_hours:
            line = line[:-1] + f", for {_duration_text(duration_hours)}."
        lines.append(line)
    if denied:
        lines.append(f"Specifically denies: {', '.join(denied)}.")
    if facts.conditions:
        lines.append(f"Known conditions: {', '.join(facts.conditions)}.")
    if facts.allergens:
        lines.append(f"Allergies: {', '.join(facts.allergens)}.")
    if facts.medicine_labels:
        lines.append(f"Current medicines: {', '.join(facts.medicine_labels)}.")
    if candidates:
        names = ", ".join(c.display_name for c in candidates)
        lines.append(f"Self-assessment tool flagged for consideration: {names}.")
    lines.append(
        "This summary was generated by an educational AI tool and is not a "
        "clinical assessment."
    )
    return "\n".join(line for line in lines if line)


def _next_steps(
    band: str,
    candidates: list[CandidateResult],
    guidance: medication_guidance.MedicationGuidance,
) -> list[str]:
    """Deterministic next-step sentences. The LLM may only rephrase these."""
    steps: list[str] = []

    if guidance.needs_doctor_prescription:
        steps.append(
            "At least one of the conditions being considered normally needs "
            "treatment prescribed by a doctor, so please arrange to be seen "
            "rather than treating this yourself."
        )
    elif band == Band.INSUFFICIENT:
        steps.append(
            "Because the picture is not clear, the safest step is to have this "
            "looked at by a doctor or pharmacist."
        )
    else:
        steps.append(
            "Please see a doctor or pharmacist if this does not start to "
            "improve, or if it gets worse at any point."
        )

    if guidance.avoid:
        steps.append(
            "There are some medication points specific to you below. Do not "
            "change any prescribed medicine on your own; raise them with your "
            "doctor or pharmacist."
        )
    return steps


def _assessment_payload(
    band: str,
    candidates: list[CandidateResult],
    symptoms: list[ExtractedSymptom],
    duration_hours: float | None,
    steps: list[str],
) -> dict[str, Any]:
    return {
        "band": band,
        "candidates": [
            {
                "code": c.code,
                "display_name": c.display_name,
                "band": c.band,
                "supporting": [e.display for e in c.supporting],
                "missing": [e.display for e in c.missing],
                "contradictory": [e.display for e in c.contradictory],
            }
            for c in candidates
        ],
        "symptoms_present": [
            knowledge.display_name(s.code)
            for s in visible_symptoms(symptoms)
            if s.present is True
        ],
        "symptoms_denied": [
            knowledge.display_name(s.code) for s in symptoms if s.present is False
        ],
        "duration_text": _duration_text(duration_hours),
        "next_steps": steps,
    }


def run(
    text: str,
    facts: ProfileFacts,
    prior_symptoms: list[ExtractedSymptom] | None = None,
    questions_asked: int = 0,
    use_llm: bool = True,
) -> PipelineResult:
    """Run the pipeline for one turn of a consultation."""
    prior_symptoms = prior_symptoms or []

    # --- [0] scope guard ----------------------------------------------------
    refusal = scope_guard.check(text, facts.age)
    if refusal is not None:
        return PipelineResult(
            outcome=Outcome.REFUSED,
            refusal_category=refusal.category,
            refusal_message=refusal.message,
            refusal_referral=refusal.referral,
            refusal_resources=list(refusal.resources),
            narrative=f"{refusal.message}\n\n{refusal.referral}",
        )

    # --- [2] extraction, merged with everything already known ---------------
    merged: dict[str, ExtractedSymptom] = {s.code: s for s in prior_symptoms}
    for symptom in extract(text):
        existing = merged.get(symptom.code)
        # Take the new observation when nothing is known yet, when the stored
        # value is an unknown, or when a stated negative overrides a positive.
        if (
            existing is None
            or existing.present is None
            or (existing.present is True and symptom.present is False)
        ):
            merged[symptom.code] = symptom
    symptoms = list(merged.values())

    # --- [1] red flags, BEFORE any reasoning --------------------------------
    escalation = red_flag_check.check(symptoms)
    if escalation is not None:
        result = PipelineResult(
            outcome=Outcome.ESCALATED,
            escalation_code=escalation.code,
            escalation_urgency=escalation.urgency,
            escalation_reason=escalation.message,
            escalation_action=escalation.action,
            escalation_triggered_by=list(escalation.triggered_by),
            escalation_source_url=escalation.source_url,
            symptoms=symptoms,
            sources=[{"name": escalation.source_name, "url": escalation.source_url}],
        )
        text_out = fallback.narrate_escalation(
            escalation.message, escalation.action, escalation.triggered_by
        )
        if use_llm:
            llm = llm_client.generate(
                prompts.ESCALATION_SYSTEM_PROMPT,
                prompts.build_escalation_prompt(
                    escalation.message, escalation.action, escalation.triggered_by
                ),
            )
            result.llm_seconds = llm.duration_seconds
            if llm.ok:
                text_out = llm.text
            else:
                result.used_fallback = True
                result.llm_error = llm.error
        else:
            result.used_fallback = True
        result.narrative = text_out
        return result

    # --- [3][4] patient context + evidence ----------------------------------
    context = facts.to_evidence_context()
    all_candidates, band = evaluate(symptoms, context)
    positive_count = sum(1 for s in symptoms if s.present is True)

    # --- [5] sufficiency ----------------------------------------------------
    sufficiency = assess_sufficiency(all_candidates, band, positive_count, questions_asked)
    if not sufficiency.sufficient:
        question = next_question(
            all_candidates,
            present={s.code for s in symptoms if s.present is True},
            denied={s.code for s in symptoms if s.present is False},
            unknown={s.code for s in symptoms if s.present is None},
            questions_asked=questions_asked,
        )
        if question is not None:
            return PipelineResult(
                outcome=Outcome.NEEDS_QUESTION,
                band=Band.INSUFFICIENT,
                question=question,
                questions_asked=questions_asked,
                sufficiency_reason=sufficiency.detail,
                symptoms=symptoms,
                all_candidates=all_candidates,
            )
        # Nothing useful left to ask: assess with what we have.

    # --- [7] medication safety ----------------------------------------------
    shown = top_candidates(all_candidates)
    present_codes = {s.code for s in symptoms if s.present is True}
    safety = medication_safety.evaluate(
        # safety_conditions, not conditions: alcohol and smoking are booleans
        # on the profile, so drug-condition rules written against them were
        # unreachable. See ProfileFacts.safety_conditions.
        facts.medications, facts.allergies, facts.safety_conditions, present_codes
    )

    # --- medication guidance (three tiers, no prescribing) ------------------
    guidance = medication_guidance.build(
        [c.code for c in shown], safety, facts.allergies
    )

    # --- [8] RAG, filtered by the surviving candidates ----------------------
    passages = retriever.retrieve([c.code for c in shown])

    # --- [9] diet and lifestyle ---------------------------------------------
    # Only the leading candidate drives diet advice. Merging several produced
    # incoherent output -- a flu patient was told not to skip antimalarial
    # doses. Generic defaults still fill the gaps inside build().
    diet = diet_lifestyle.build(
        [shown[0].code] if shown else [],
        facts.diet_type,
        facts.conditions,
        facts.allergens,
    )

    durations = [
        s.duration_hours for s in symptoms if s.present is True and s.duration_hours
    ]
    duration_hours = max(durations) if durations else None

    steps = _next_steps(band, shown, guidance)
    payload = _assessment_payload(band, shown, symptoms, duration_hours, steps)

    result = PipelineResult(
        outcome=Outcome.COMPLETE,
        band=band,
        questions_asked=questions_asked,
        sufficiency_reason=sufficiency.detail,
        symptoms=symptoms,
        candidates=shown,
        all_candidates=all_candidates,
        ruled_out=compute_ruled_out(all_candidates),
        safety=safety,
        guidance=guidance,
        diet=diet,
        passages=passages,
        sources=retriever.unique_sources(passages),
        assessment_payload=payload,
    )

    # --- [10] the single LLM call -------------------------------------------
    result.narrative = fallback.narrate_assessment(payload)
    if use_llm:
        llm = llm_client.generate(
            prompts.SYSTEM_PROMPT,
            prompts.build_assessment_prompt(
                payload,
                [
                    {"source_name": p.source_name, "text": p.text}
                    for p in passages
                ],
            ),
        )
        result.llm_seconds = llm.duration_seconds
        if llm.ok:
            result.narrative = llm.text
        else:
            result.used_fallback = True
            result.llm_error = llm.error
    else:
        result.used_fallback = True

    return result
