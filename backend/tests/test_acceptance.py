"""The 10 acceptance tests from spec section 17.

Each test names the spec item it covers. These are the claims the project is
graded on, so they assert behaviour a user would see, not internals.

Run:  .venv/Scripts/python.exe -m pytest tests/test_acceptance.py -v
"""
import re

import pytest

from tests.conftest import (
    NSAID_USER,
    answer,
    PRIYA,
    RAJESH,
    all_text,
    auth,
    make_patient,
    run_to_completion,
    start,
)

CLASSIC_FLU = "fever, cough, headache, body aches, chills, dry cough, 2 days"
RESPIRATORY = {"influenza", "covid19", "common_cold", "acute_bronchitis", "pneumonia"}


# --- 1 ----------------------------------------------------------------------

def test_1_sparse_input_asks_questions_and_names_no_condition(client):
    """"fever, cough, headache" -> follow-up questions, no diagnosis."""
    token = make_patient(client, RAJESH)
    turn = start(client, token, "fever, cough, headache")

    assert turn["outcome"] == "needs_question"
    assert turn["question"] is not None
    assert turn["question"]["options"], "questions must offer tappable options"
    # Nothing resembling an assessment may be produced yet.
    assert turn["candidates"] == []
    assert turn["band"] is None
    assert turn["medication_guidance"] is None


# --- 2 ----------------------------------------------------------------------

def test_2_rich_input_ranks_respiratory_candidates_sensibly(client):
    """A classic flu presentation should surface respiratory candidates."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(
        client, token, CLASSIC_FLU, {"loss_of_smell": "No", "productive_cough": "No"}
    )

    assert turn["outcome"] == "complete"
    codes = [c["code"] for c in turn["candidates"]]
    assert codes, "expected at least one candidate"
    assert codes[0] in RESPIRATORY, f"top candidate {codes[0]} is not respiratory"
    # Every candidate must show the evidence behind it.
    for candidate in turn["candidates"]:
        assert candidate["evidence"]["supporting"], candidate["display_name"]


# --- 3 (showcase) -----------------------------------------------------------

def test_3_negation_is_recorded_and_never_surfaces_as_a_symptom(client):
    """Stated negatives are evidence, not noise. Ear symptoms must not appear."""
    token = make_patient(client, RAJESH)
    turn = start(
        client, token, "fever, headache, cough, no ear pain, no hearing problems"
    )

    symptoms = {s["code"]: s["present"] for s in turn["symptoms"]}
    assert symptoms.get("ear_pain") is False, "negated ear pain must be stored as denied"
    assert symptoms.get("hearing_problems") is False
    assert symptoms.get("fever") is True
    assert symptoms.get("headache") is True
    assert symptoms.get("cough") is True

    # No candidate may claim a denied symptom as supporting evidence.
    for candidate in turn["candidates"]:
        supporting = " ".join(candidate["evidence"]["supporting"]).lower()
        assert "ear" not in supporting
        assert "hearing" not in supporting


# --- 4 ----------------------------------------------------------------------

def test_4_penicillin_allergy_flags_amoxicillin_by_class(client):
    """Cross-reactivity is by class. The names share no substring."""
    from core import medication_safety

    report = medication_safety.evaluate(
        medications=[{"brand_name": "Augmentin", "generic_name": None}],
        allergies=[{"allergen": "Penicillin", "allergen_class": "penicillin"}],
        conditions=[],
        present_symptoms=set(),
    )

    allergy_findings = [f for f in report.findings if f.kind == "drug_allergy"]
    assert allergy_findings, "penicillin allergy did not flag Augmentin"
    finding = allergy_findings[0]
    assert finding.severity == "avoid"
    assert "Augmentin" in finding.reason and "Penicillin" in finding.reason
    assert finding.source_url


def test_4b_nsaid_allergy_flags_every_member_of_the_class(client):
    from core import medication_safety

    for brand in ["Brufen", "Voveran", "Naprosyn", "Disprin", "Combiflam"]:
        report = medication_safety.evaluate(
            medications=[{"brand_name": brand, "generic_name": None}],
            allergies=[{"allergen": "Ibuprofen", "allergen_class": "nsaid"}],
            conditions=[],
            present_symptoms=set(),
        )
        assert any(f.kind == "drug_allergy" for f in report.findings), brand


# --- 5 ----------------------------------------------------------------------

def test_5_interacting_medication_is_flagged_with_a_reason(client):
    """The flag must name the patient's actual medicines and say why."""
    token = make_patient(client, NSAID_USER)
    turn = run_to_completion(
        client, token, "burning in my chest after eating for two weeks", {}
    )

    safety = turn["medication_safety"]
    assert safety is not None and safety["findings"], "expected safety findings"

    reasons = " ".join(f["reason"] for f in safety["findings"])
    assert "Combiflam" in reasons, "the finding must name their actual medicine"
    assert len(reasons) > 60, "a bare severity label is not a reason"
    assert any(f["severity"] in ("caution", "avoid") for f in safety["findings"])


def test_5b_unrecognised_medicine_is_reported_not_silently_skipped(client):
    from core import medication_safety

    report = medication_safety.evaluate(
        medications=[{"brand_name": "SomeUnknownPill", "generic_name": None}],
        allergies=[],
        conditions=[],
        present_symptoms=set(),
    )
    assert report.unrecognised == ["SomeUnknownPill"]


# --- 6 ----------------------------------------------------------------------

def _prescription_pdf() -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in [
        "CITY HOSPITAL - DISCHARGE SUMMARY",
        "DIAGNOSIS: Hypertension, Asthma",
        "TREATMENT ADVISED:",
        "1. Tab Amlong 5mg once daily",
        "2. Tab Glycomet 500mg twice daily",
    ]:
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_6_document_facts_reach_the_profile_only_after_confirmation(client):
    """Nothing extracted may become profile truth without explicit confirmation."""
    token = make_patient(client, PRIYA)

    r = client.post(
        "/api/documents",
        files={"file": ("prescription.pdf", _prescription_pdf(), "application/pdf")},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["extraction_status"] == "complete"
    assert doc["facts"], "nothing was extracted"
    assert all(f["review_status"] == "pending" for f in doc["facts"])

    before = client.get("/api/profile", headers=auth(token)).json()

    # Confirm only the medicines; reject everything else.
    meds = [f["id"] for f in doc["facts"] if f["fact_type"] == "medication"]
    rest = [f["id"] for f in doc["facts"] if f["fact_type"] != "medication"]
    assert meds and rest, "need both kinds to prove selective confirmation"

    r = client.post(
        f"/api/documents/{doc['id']}/confirm",
        json={"fact_ids": meds, "rejected_ids": rest},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    after = client.get("/api/profile", headers=auth(token)).json()
    assert len(after["medications"]) == len(before["medications"]) + len(meds)
    # Rejected conditions must NOT have appeared.
    assert len(after["conditions"]) == len(before["conditions"])

    added = [
        m for m in after["medications"]
        if m["provenance"] == "document_extracted_confirmed"
    ]
    assert len(added) == len(meds)
    assert all(m["confirmed_at"] for m in added)


def test_6b_scanned_pdf_gets_a_clear_message_not_a_crash(client):
    """No OCR by design. An image-only PDF must fail gracefully."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()  # a page with no text layer at all
    token = make_patient(client, PRIYA)

    r = client.post(
        "/api/documents",
        files={"file": ("scan.pdf", bytes(pdf.output()), "application/pdf")},
        headers=auth(token),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["extraction_status"] == "no_text_layer"
    assert "manually" in body["message"].lower()


# --- 7 ----------------------------------------------------------------------

def test_7_existing_condition_shows_up_in_medication_safety(client):
    """Hypertension must influence the medication safety output."""
    token = make_patient(client, NSAID_USER)
    turn = run_to_completion(
        client, token, "burning in my chest after eating for two weeks", {}
    )

    safety = turn["medication_safety"]
    reasons = " ".join(f["reason"] for f in safety["findings"])
    assert "Hypertension" in reasons, "the patient's condition must be named"

    condition_findings = [f for f in safety["findings"] if f["kind"] == "drug_condition"]
    assert condition_findings, "expected a drug-condition finding"
    assert all(f["source_url"] for f in condition_findings)


# --- 8 ----------------------------------------------------------------------

@pytest.mark.parametrize("text", ["I feel unwell", "not feeling good", "I need help"])
def test_8_vague_input_never_fabricates_an_assessment(client, text):
    token = make_patient(client, RAJESH, email=f"{abs(hash(text))}@example.com")
    turn = start(client, token, text)

    assert turn["outcome"] in ("needs_question", "complete")
    if turn["outcome"] == "complete":
        assert turn["band"] == "insufficient_information"
    assert not turn["candidates"] or turn["band"] == "insufficient_information"


# --- 9 (showcase) -----------------------------------------------------------

def test_9_red_flag_escalates_immediately_and_halts_the_pipeline(client):
    """Invariant 2: escalate, halt, produce nothing else."""
    token = make_patient(client, RAJESH)
    turn = start(client, token, "chest pain radiating to my left arm, sweating")

    assert turn["outcome"] == "escalated"
    assert turn["status"] == "escalated"

    escalation = turn["escalation"]
    assert escalation["urgency"] == "emergency"
    assert escalation["triggered_by"]
    assert escalation["action"]

    # The whole point: no reasoning products at all.
    assert turn["candidates"] == []
    assert turn["medication_safety"] is None
    assert turn["medication_guidance"] is None
    assert turn["diet"] is None
    assert turn["question"] is None


def test_9b_red_flags_beat_an_otherwise_strong_candidate(client):
    """A red flag inside a rich symptom picture still short-circuits."""
    token = make_patient(client, RAJESH)
    turn = start(
        client,
        token,
        "high fever, severe headache, pain behind my eyes, body pain, "
        "and my gums are bleeding",
    )
    assert turn["outcome"] == "escalated"
    assert turn["candidates"] == []


# --- 10 (showcase) ----------------------------------------------------------

def test_10_identical_symptoms_give_different_output_per_patient(client):
    """Same complaint, two profiles, visibly different guidance."""
    dengue = "high fever, severe headache, pain behind my eyes, body pain and a rash for 3 days"

    rajesh = make_patient(client, RAJESH, email="rajesh@example.com")
    priya = make_patient(client, PRIYA, email="priya@example.com")

    a = run_to_completion(client, rajesh, dengue, {})
    b = run_to_completion(client, priya, dengue, {})
    assert a["outcome"] == b["outcome"] == "complete"

    # Same leading candidate...
    assert a["candidates"][0]["code"] == b["candidates"][0]["code"]

    # ...but different medication safety, naming each patient's own medicines.
    a_reasons = " ".join(f["reason"] for f in a["medication_safety"]["findings"])
    b_reasons = " ".join(f["reason"] for f in b["medication_safety"]["findings"])
    assert "Amlong" in a_reasons or "Glycomet" in a_reasons
    assert "Pan-D" in b_reasons
    assert a_reasons != b_reasons

    # ...and different diet. The diabetic must not be offered the sugary item.
    a_diet = " ".join(a["diet"]["prefer"]).lower()
    b_diet = " ".join(b["diet"]["prefer"]).lower()
    assert a_diet != b_diet
    assert "papaya" not in a_diet, "diabetic patient was offered a high-sugar item"
    assert "papaya" in b_diet


def test_10b_vegetarian_is_never_offered_meat(client):
    from core import diet_lifestyle

    veg = diet_lifestyle.build(["common_cold"], diet_type="veg")
    text = " ".join(veg.by_category(diet_lifestyle.Category.DIET_PREFER)).lower()
    assert "chicken" not in text

    non_veg = diet_lifestyle.build(["common_cold"], diet_type="non_veg")
    assert "chicken" in " ".join(
        non_veg.by_category(diet_lifestyle.Category.DIET_PREFER)
    ).lower()


def test_10c_nsaid_allergic_patient_still_sees_the_nsaid_warning(client):
    """Filtering hides recommendations, never warnings.

    Regression: an NSAID-allergic patient lost "avoid ibuprofen" because the
    allergen filter was applied to the avoid list too.
    """
    from core import diet_lifestyle

    plan = diet_lifestyle.build(
        ["dengue"], diet_type="veg", conditions=["GERD"], allergens=["Ibuprofen"]
    )
    avoid = " ".join(plan.by_category(diet_lifestyle.Category.DIET_AVOID)).lower()
    assert "ibuprofen" in avoid


# --- spec section 10: the third output tier ---------------------------------

def test_no_known_conflict_is_shown_not_silently_omitted(client):
    """Spec section 10 defines three tiers; no_known_conflict is one of them.

    Rendering nothing when the check found nothing hides that it ran at all.
    """
    token = make_patient(client, RAJESH)
    # Amlodipine and Metformin have no known interaction with each other.
    turn = run_to_completion(client, token, "sore throat and a blocked nose", {})

    safety = turn["medication_safety"]
    assert safety is not None
    assert safety["overall"] == "none"
    assert safety["findings"] == []
    assert set(safety["checked_medicines"]) == {"Amlong", "Glycomet"}, (
        "the no-conflict state must still name what was checked"
    )


def test_no_known_conflict_survives_into_history(client):
    """History rebuilds from stored rows, so the tier must be persisted."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(client, token, "sore throat and a blocked nose", {})

    r = client.get(f"/api/history/{turn['consultation_id']}", headers=auth(token))
    assert r.status_code == 200
    safety = r.json()["medication_safety"]
    assert safety["overall"] == "none"
    assert safety["findings"] == [], "a no-conflict row must not read as a finding"
    assert set(safety["checked_medicines"]) == {"Amlong", "Glycomet"}


# --- regressions ------------------------------------------------------------

def test_not_sure_does_not_repeat_the_same_question(client):
    """Regression: "Not sure" recorded nothing, so the question repeated.

    Answering "Not sure" must mark the symptom asked-but-unknown. It still
    contributes no evidence, but it must never be selected again.
    """
    token = make_patient(client, RAJESH)
    turn = start(client, token, "I have fever and cough")

    asked: list[str] = []
    for _ in range(6):
        if turn["outcome"] != "needs_question":
            break
        asked.append(turn["question"]["text"])
        turn = answer(client, token, turn, "Not sure")

    assert len(asked) == len(set(asked)), f"a question repeated: {asked}"
    assert len(asked) >= 3, "should keep asking new questions, not stall"


def test_not_sure_is_never_treated_as_a_denial(client):
    """An unknown must not become evidence against anything."""
    token = make_patient(client, RAJESH)
    turn = start(client, token, "I have fever and cough")
    code = turn["question"]["symptom_code"]
    turn = answer(client, token, turn, "Not sure")

    recorded = {s["code"]: s["present"] for s in turn["symptoms"]}
    assert recorded.get(code) is not False, (
        "answering 'Not sure' was recorded as an explicit denial"
    )


def test_ruled_out_explains_why_an_obvious_option_was_dropped(client):
    """The user should be able to see why a plausible condition was set aside."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(
        client,
        token,
        "fever, cough, chills, dry cough, body ache, no runny nose",
        {},
    )

    assert turn["outcome"] == "complete"
    codes = [c["code"] for c in turn["ruled_out"]]
    assert "common_cold" in codes, (
        "denying a runny nose should visibly rule out the common cold"
    )

    cold = next(c for c in turn["ruled_out"] if c["code"] == "common_cold")
    evidence = cold["evidence"]["missing"] + cold["evidence"]["contradictory"]
    assert evidence, "a ruled-out candidate must carry its reason"
    # And the reason must not read as "Runny nose, Runny nose".
    assert len(evidence) == len(set(evidence)), f"duplicated evidence: {evidence}"


def test_full_answers_reach_a_confident_band(client):
    """With the questions actually answered, the engine commits to a leader."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(
        client,
        token,
        "fever, cough, chills, dry cough, body ache, no runny nose",
        {},
    )
    assert turn["band"] == "most_consistent"
    assert turn["candidates"][0]["code"] == "influenza"


# --- question budget --------------------------------------------------------

def test_history_is_long_enough_to_narrow_things_down(client):
    """A vague opening should get a proper history, not a token 2 questions."""
    token = make_patient(client, RAJESH)
    replies = {
        "shortness_of_breath": "No", "chest_pain": "No", "severe_abdominal_pain": "No",
        "chills": "Yes", "sweating": "No", "body_ache": "Yes", "dry_cough": "Yes",
        "fatigue": "Yes", "runny_nose": "No",
    }
    turn = run_to_completion(client, token, "I have fever and cough", replies)

    assert turn["outcome"] == "complete"
    assert turn["questions_asked"] >= 4, (
        f"only asked {turn['questions_asked']} questions for a vague opening"
    )
    assert turn["band"] == "most_consistent", "a full history should reach a verdict"


def test_it_stops_early_when_the_evidence_is_already_decisive(client):
    """A clinician stops asking once the picture is clear. So does this."""
    token = make_patient(client, RAJESH)
    turn = start(
        client,
        token,
        "high fever, severe headache, pain behind my eyes, body pain and a rash for 3 days",
    )

    assert turn["outcome"] == "complete", "a decisive opening should not be interrogated"
    assert turn["questions_asked"] == 0
    assert turn["band"] == "most_consistent"


def test_question_budget_is_always_bounded(client):
    """An unhelpful patient must still terminate, honestly."""
    from core.sufficiency import MAX_QUESTIONS

    token = make_patient(client, RAJESH)
    turn = start(client, token, "I have a cough and feel tired")

    asked = 0
    while turn["outcome"] == "needs_question" and asked < MAX_QUESTIONS + 5:
        turn = answer(client, token, turn, "Not sure")
        asked += 1

    assert turn["outcome"] == "complete"
    assert asked <= MAX_QUESTIONS, f"asked {asked}, budget is {MAX_QUESTIONS}"
    # Nothing was learned, so it must say so rather than invent a verdict.
    assert turn["band"] == "insufficient_information"


def test_questions_read_like_a_person_asked_them(client):
    """The generic fallback used to emit "Do you have headache?"."""
    from core import knowledge
    from core.followup_engine import _phrase

    for code in knowledge.symptoms():
        text = _phrase(code)
        assert text.endswith("?"), code
        # "Do you have headache?" / "Do you have cough?" are the bad shapes.
        assert not text.startswith("Do you have headache"), code
        assert not text.startswith("Do you have cough?"), code


def test_ruled_out_survives_into_history(client):
    """Reopening a consultation must not lose the "why not X?" explanation."""
    token = make_patient(client, RAJESH)
    turn = run_to_completion(
        client, token, "fever, cough, chills, dry cough, body ache, no runny nose", {}
    )
    assert turn["ruled_out"], "live result should carry ruled-out candidates"

    r = client.get(f"/api/history/{turn['consultation_id']}", headers=auth(token))
    assert r.status_code == 200
    stored = r.json()["ruled_out"]
    assert stored, "history lost the ruled-out candidates"
    assert {c["code"] for c in stored} == {c["code"] for c in turn["ruled_out"]}
