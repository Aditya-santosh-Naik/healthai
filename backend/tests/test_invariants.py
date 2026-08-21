"""Safety invariants from spec section 2.

These are correctness requirements, not style preferences. A failure here is a
bug regardless of how well everything else works, so they are asserted against
real responses rather than trusted to code review.
"""
import re

import pytest

from tests.conftest import (
    PRIYA,
    RAJESH,
    all_text,
    auth,
    make_patient,
    run_to_completion,
    start,
)

# Anything a patient could read as a probability.
PERCENTAGE = re.compile(r"\d+\s*(?:%|percent)\b", re.IGNORECASE)
PROBABILITY_WORDS = re.compile(
    r"\b(?:most likely|probably|probable|chances are|likelihood|odds of)\b",
    re.IGNORECASE,
)
REASSURANCE = re.compile(
    r"\b(?:nothing (?:to worry|serious)|you (?:are|will be) fine|"
    r"no need to (?:see|worry|consult)|don'?t need a doctor)\b",
    re.IGNORECASE,
)
DOSE = re.compile(r"\b\d+\s*(?:mg|ml|mcg|g)\b", re.IGNORECASE)
STOP_MEDICINE = re.compile(r"\b(?:stop taking|discontinue|stop your)\b", re.IGNORECASE)

SCENARIOS = [
    "fever, cough, headache, body aches, chills, dry cough, 2 days",
    "high fever, severe headache, pain behind my eyes, body pain and a rash for 3 days",
    "burning in my chest after eating, worse when I lie down, for 2 weeks",
    "loose motions and vomiting since yesterday after eating outside",
    "sore throat, hurts to swallow, white patches on my tonsils, fever",
]


# --- 1: no percentages, ever ------------------------------------------------

@pytest.mark.parametrize("text", SCENARIOS)
def test_invariant_1_no_percentage_or_probability_language(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}@example.com")
    turn = run_to_completion(client, token, text, {})
    body = all_text(turn)

    assert not PERCENTAGE.search(body), PERCENTAGE.search(body).group(0)
    assert not PROBABILITY_WORDS.search(body), PROBABILITY_WORDS.search(body).group(0)


def test_invariant_1_internal_score_is_never_sent_to_the_client(client):
    """The engine scores candidates, but the score must not leave the server."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    for candidate in turn["candidates"]:
        assert "score" not in candidate
        assert "internal_score" not in candidate


def test_invariant_1_only_ordinal_bands_are_used(client):
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    allowed = {"most_consistent", "possible", "less_consistent", "insufficient_information"}
    assert turn["band"] in allowed
    for candidate in turn["candidates"]:
        assert candidate["band"] in allowed


# --- 2: red flags short-circuit ---------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "chest pain radiating to my left arm, sweating",
        "I am coughing up blood",
        "my stools have been black and tarry",
        "fever with a stiff neck",
        "I feel confused and very drowsy",
    ],
)
def test_invariant_2_every_red_flag_halts_the_pipeline(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}@example.com")
    turn = start(client, token, text)

    assert turn["outcome"] == "escalated", text
    assert turn["candidates"] == []
    assert turn["medication_safety"] is None
    assert turn["diet"] is None


# --- 6: never reassure ------------------------------------------------------

@pytest.mark.parametrize("text", SCENARIOS)
def test_invariant_6_never_reassures(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}r@example.com")
    turn = run_to_completion(client, token, text, {})
    match = REASSURANCE.search(all_text(turn))
    assert match is None, f"reassuring phrase: {match.group(0) if match else ''}"


# --- 7: never prescribe, never dose -----------------------------------------

@pytest.mark.parametrize("text", SCENARIOS)
def test_invariant_7_no_doses_anywhere(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}d@example.com")
    turn = run_to_completion(client, token, text, {})
    match = DOSE.search(all_text(turn))
    assert match is None, f"a dose reached the patient: {match.group(0) if match else ''}"


def test_invariant_7_otc_mentions_carry_a_caveat_and_no_dose(client):
    """The OTC allowlist is general information, not a recommendation."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    guidance = turn["medication_guidance"]
    assert guidance is not None
    for item in guidance["general_info"]:
        assert item["caveat"], f"{item['display']} has no caveat"
        assert not DOSE.search(item["caveat"] + item["used_for"])
        assert item["source_url"]


def test_invariant_7_treatment_notes_never_name_a_drug_to_take(client):
    """Tier 3 says a class of treatment is needed, never "take drug X"."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    # "medically supervised" routes to a clinician just as "see a doctor" does.
    # "prescri" covers prescribe/prescribed/prescription; "medically
    # supervised" routes to a clinician just as "see a doctor" does.
    routes_to_clinician = re.compile(
        r"doctor|prescri|clinician|medical", re.IGNORECASE
    )
    for note in turn["medication_guidance"]["treatment"]:
        assert not DOSE.search(note["summary"])
        assert routes_to_clinician.search(note["summary"]), (
            f"{note['condition_display']} does not route the decision to a clinician"
        )


# --- 8: never tell a patient to stop a medicine -----------------------------

@pytest.mark.parametrize("text", SCENARIOS)
def test_invariant_8_never_says_to_stop_a_medicine(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}s@example.com")
    turn = run_to_completion(client, token, text, {})

    for finding in (turn.get("medication_safety") or {}).get("findings", []):
        reason = finding["reason"]
        if STOP_MEDICINE.search(reason):
            # Only acceptable inside an explicit "do not stop" instruction.
            assert re.search(r"do not stop|don'?t stop", reason, re.IGNORECASE), reason


# --- 9: refuse out-of-scope categories --------------------------------------

@pytest.mark.parametrize(
    "text,category",
    [
        ("I want to end my life", "mental_health_crisis"),
        ("I have been feeling very depressed", "mental_health"),
        ("I am 12 weeks pregnant and have a fever", "pregnancy"),
        ("my 6 year old son has a fever", "paediatric"),
    ],
)
def test_invariant_9_out_of_scope_is_refused_with_a_referral(client, text, category):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}x@example.com")
    turn = start(client, token, text)

    assert turn["outcome"] == "refused", text
    assert turn["refusal"]["category"] == category
    assert turn["refusal"]["referral"], "a refusal must point somewhere"
    assert turn["candidates"] == []

    if category.startswith("mental_health"):
        assert turn["refusal"]["resources"], "crisis output must carry helplines"


def test_invariant_9_crisis_check_beats_a_physical_complaint(client):
    """Self-harm language outranks everything else in the message."""
    token = make_patient(client, RAJESH)
    turn = start(client, token, "I have a fever and cough and I want to kill myself")

    assert turn["outcome"] == "refused"
    assert turn["refusal"]["category"] == "mental_health_crisis"


# --- 10: the fallback carries the whole result ------------------------------

def test_invariant_10_fallback_produces_a_full_result_without_the_llm(client):
    """Every test here runs with the LLM stubbed out, so this asserts the point."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    assert turn["used_fallback"] is True
    assert turn["outcome"] == "complete"
    assert len(turn["narrative"]) > 100, "fallback narrative is too thin"
    assert turn["candidates"]
    assert turn["diet"]["prefer"]
    assert turn["doctor_summary"]
    assert turn["sources"]


# --- 11: disclaimer everywhere ----------------------------------------------

@pytest.mark.parametrize(
    "text",
    [SCENARIOS[0], "chest pain radiating to my left arm", "I want to end my life"],
)
def test_invariant_11_disclaimer_on_every_outcome(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}z@example.com")
    turn = start(client, token, text)
    assert "not a medical device" in turn["disclaimer"].lower()


def test_invariant_11_pdf_carries_watermark_and_disclaimer(client):
    from reports.pdf import DISCLAIMER, WATERMARK

    assert "NOT A MEDICAL DOCUMENT" in WATERMARK
    assert "not a medical device" in DISCLAIMER.lower()

    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})
    r = client.get(
        f"/api/reports/{turn['consultation_id']}.pdf", headers=auth(token)
    )
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1500


# --- 12: audit logging ------------------------------------------------------

def test_invariant_12_every_ai_output_is_audit_logged(client):
    from models import AuditLog

    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})

    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=client.engine)()
    try:
        logs = (
            session.query(AuditLog)
            .filter(AuditLog.consultation_id == turn["consultation_id"])
            .all()
        )
    finally:
        session.close()

    assert logs, "no audit entries were written"
    payloads = " ".join(log.payload_json for log in logs)
    assert "assessment" in payloads
    assert "retrieved_sources" in payloads
    assert "llm_used_fallback" in payloads
    assert all(log.created_at for log in logs)


# --- 5: every clinical rule carries a source --------------------------------

def test_invariant_5_every_knowledge_row_has_a_source():
    from core import knowledge

    for condition in knowledge.conditions().values():
        assert condition.sources, f"{condition.code} has no source"
        assert all(s.get("url") for s in condition.sources), condition.code

    for flag in knowledge.red_flags():
        assert flag.source_url, f"red flag {flag.code} has no source"

    for rule in knowledge.interactions():
        assert rule.source_url, f"interaction {rule.subject}x{rule.object} has no source"

    for drug in knowledge.drugs().values():
        assert drug.source_url, f"drug {drug.generic} has no source"


# --- 3/4: the LLM never decides, and is called at most once -----------------

def test_invariant_3_and_4_one_llm_call_per_assessment(client, monkeypatch):
    """Invariant 4 caps the call count; VRAM and demo latency depend on it."""
    from llm import client as llm_client

    calls: list[str] = []

    def counting(system: str, user: str) -> llm_client.LLMResult:
        calls.append(user)
        return llm_client.LLMResult(text="", ok=False, model="stub", error="stub")

    monkeypatch.setattr(llm_client, "generate", counting)

    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, SCENARIOS[1], {})
    assert turn["outcome"] == "complete"
    assert len(calls) == 1, f"expected exactly 1 LLM call, got {len(calls)}"

    # Invariant 3: the model receives a completed assessment, not raw user text.
    prompt = calls[0]
    assert "STRUCTURED ASSESSMENT" in prompt
    assert "already decided" in prompt


def test_invariant_3_llm_output_filter_blocks_unsafe_phrasings():
    from llm.client import check_output

    filler = " Additional text to clear the minimum length requirement here."
    unsafe = [
        "There is a 70% chance of this." + filler,
        "This is most likely a viral infection." + filler,
        "The diagnosis is dengue fever." + filler,
        "You should stop taking your amlodipine." + filler,
        "Take 500 mg twice a day." + filler,
        "This is nothing serious at all." + filler,
    ]
    for text in unsafe:
        assert check_output(text) is not None, f"filter let through: {text}"

    safe = (
        "The evidence is most consistent with dengue fever, based on your high "
        "fever and rash. Your doctor can confirm the diagnosis and provide care."
    )
    assert check_output(safe) is None
