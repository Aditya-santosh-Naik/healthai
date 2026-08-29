"""Reopening a consultation must show what the live view showed.

The failure these guard against has now happened four times in this file's
history: a field is added to the live consultation response, and the history
rebuild -- a second, hand-maintained assembly of the same shape -- is not
updated. The block then renders empty for anyone reviewing a past
consultation, silently, because nothing type-checks the two against each other.
"""
from tests.conftest import RAJESH, auth, make_patient, run_to_completion, start, answer

DECISIVE = "fever, body aches, chills, sudden onset, dry cough for 2 days"


def complete(client, token, text=DECISIVE, replies=None):
    return run_to_completion(client, token, text, replies or {})


def reopen(client, token, turn):
    r = client.get(f"/api/history/{turn['consultation_id']}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_medication_guidance_survives_into_history(client):
    """The three-tier medication block must not vanish when reopened.

    It is not stored in any table -- it is derived from the candidates and the
    patient's own medicines -- so the rebuild has to recompute it. That is
    deterministic and calls no LLM, so it still reflects what was decided.
    """
    token = make_patient(client, RAJESH)
    turn = complete(client, token)
    assert turn["medication_guidance"] is not None, "precondition: live view has it"

    past = reopen(client, token, turn)
    assert past["medication_guidance"] is not None, (
        "reopening a consultation dropped the entire medication guidance block"
    )
    live, stored = turn["medication_guidance"], past["medication_guidance"]
    assert stored["needs_doctor_prescription"] == live["needs_doctor_prescription"]
    assert len(stored["treatment"]) == len(live["treatment"])
    assert [a for a in stored["avoid"]] == [a for a in live["avoid"]]


def test_doctor_summary_survives_into_history(client):
    token = make_patient(client, RAJESH)
    turn = complete(client, token)
    past = reopen(client, token, turn)
    if turn["doctor_summary"]:
        assert past["doctor_summary"], "the doctor summary was lost on reopening"


def test_not_sure_is_not_rebuilt_as_a_denial(client):
    """`bool(None)` is False, which turned "Not sure" into an explicit denial.

    A fabricated denial is not cosmetic: a denied symptom is scored as evidence
    against a condition, and the symptom list is what a doctor would read off
    the printed summary.
    """
    token = make_patient(client, RAJESH)
    turn = start(client, token, "I have fever and cough")

    unsure: list[str] = []
    for _ in range(12):
        if turn["outcome"] != "needs_question":
            break
        code = turn["question"]["symptom_code"]
        # Answer the safety screens honestly; be unsure about everything else,
        # so at least one symptom is recorded as asked-but-unknown.
        if code in ("shortness_of_breath", "chest_pain", "severe_abdominal_pain"):
            turn = answer(client, token, turn, "No")
        else:
            unsure.append(code)
            turn = answer(client, token, turn, "Not sure")

    assert unsure, "precondition: at least one question answered 'Not sure'"
    live = {s["code"]: s["present"] for s in turn["symptoms"]}
    assert any(live.get(c) is None for c in unsure), "precondition: live view kept None"

    past = reopen(client, token, turn)
    rebuilt = {s["code"]: s["present"] for s in past["symptoms"]}
    for code in unsure:
        if code in rebuilt:
            assert rebuilt[code] is not False, (
                f"{code} was answered 'Not sure' but came back from history as an "
                "explicit denial"
            )


def test_history_detail_fills_every_field_the_live_turn_filled(client):
    """The general form of the bug, so the next added field cannot slip through.

    Compares the two responses field by field rather than naming one field, so
    this fails when someone adds a field to the live turn and forgets history.
    """
    token = make_patient(client, RAJESH)
    turn = complete(client, token)
    past = reopen(client, token, turn)

    # Fields that legitimately differ: these describe the live exchange, not
    # the decision that was recorded.
    exempt = {
        "question", "sufficiency_reason", "questions_asked", "status", "outcome",
        "narrative", "messages", "started_at", "completed_at", "symptoms",
        "sources", "disclaimer",
    }
    lost = [
        key
        for key, value in turn.items()
        if key not in exempt
        and value not in (None, [], "", {})
        and past.get(key) in (None, [], "", {})
    ]
    assert not lost, f"history rebuild dropped fields the live turn had: {lost}"
