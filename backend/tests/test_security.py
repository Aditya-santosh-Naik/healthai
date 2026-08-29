"""Security regressions.

These cover failures that are silent by construction: an endpoint that serves
another patient's data still returns 200, and an upload limit applied after the
bytes are already in memory still reports the right error while the process
dies. Neither shows up in a functional test.
"""
import io

import pytest

from tests.conftest import PRIYA, RAJESH, auth, make_patient, run_to_completion


# --- ownership / IDOR -------------------------------------------------------

@pytest.fixture
def two_patients(client):
    a = make_patient(client, RAJESH, email="owner@example.com")
    b = make_patient(client, PRIYA, email="stranger@example.com")
    return a, b


def test_one_patient_cannot_read_anothers_consultation(client, two_patients):
    owner, stranger = two_patients
    turn = run_to_completion(client, owner, "sore throat and a blocked nose", {})
    cid = turn["consultation_id"]

    assert client.get(f"/api/history/{cid}", headers=auth(owner)).status_code == 200
    r = client.get(f"/api/history/{cid}", headers=auth(stranger))
    assert r.status_code == 404, "another patient's consultation was readable"


def test_a_stranger_cannot_delete_or_export_anothers_consultation(client, two_patients):
    owner, stranger = two_patients
    turn = run_to_completion(client, owner, "sore throat and a blocked nose", {})
    cid = turn["consultation_id"]

    # .pdf suffix matters: without it the request 404s on routing, and the
    # assertion passes while testing nothing.
    assert client.get(f"/api/reports/{cid}.pdf", headers=auth(owner)).status_code == 200
    assert client.get(f"/api/reports/{cid}.pdf", headers=auth(stranger)).status_code == 404
    assert client.delete(f"/api/history/{cid}", headers=auth(stranger)).status_code == 404
    # And the owner still has it: the 404 must be a refusal, not a deletion.
    assert client.get(f"/api/history/{cid}", headers=auth(owner)).status_code == 200


def test_ownership_failure_is_404_not_403(client, two_patients):
    """403 would confirm the row exists, which is the fact being protected."""
    owner, stranger = two_patients
    turn = run_to_completion(client, owner, "sore throat and a blocked nose", {})
    r = client.get(f"/api/history/{turn['consultation_id']}", headers=auth(stranger))
    assert r.status_code == 404
    # Indistinguishable from an id that was never issued.
    missing = client.get("/api/history/99999", headers=auth(stranger))
    assert missing.status_code == r.status_code
    assert missing.json()["detail"] == r.json()["detail"]


def test_endpoints_reject_an_unauthenticated_caller(client):
    for path in [
        "/api/history",
        "/api/history/1",
        "/api/reports/1.pdf",
        "/api/profile",
        "/api/documents",
    ]:
        r = client.get(path)
        assert r.status_code in (401, 403), f"GET {path} -> {r.status_code}"

    r = client.post("/api/consultation/start", json={"text": "fever"})
    assert r.status_code in (401, 403), f"POST start -> {r.status_code}"


# --- upload limits ----------------------------------------------------------

def test_an_oversized_upload_is_refused(client):
    """The limit must hold. It used to be applied after `await file.read()`
    had already buffered the entire body, so the check reported the right
    error only if the process survived long enough to run it."""
    token = make_patient(client, RAJESH, email="uploader@example.com")
    oversized = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)
    r = client.post(
        "/api/documents",
        headers=auth(token),
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert r.status_code == 413


def test_a_non_pdf_is_refused_by_extension(client):
    token = make_patient(client, RAJESH, email="uploader2@example.com")
    r = client.post(
        "/api/documents",
        headers=auth(token),
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 415


# --- token handling ---------------------------------------------------------

@pytest.mark.parametrize(
    "token",
    ["", "garbage", "a.b.c", "Bearer", "eyJhbGciOiJub25lIn0..", "null"],
)
def test_malformed_tokens_are_rejected_not_crashed(client, token):
    """A bad token must be a clean 401, never a 500.

    The `alg: none` case matters: it is the classic JWT forgery, and it must
    fail because the algorithm is pinned, not by accident.
    """
    r = client.get("/api/history", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (401, 403), f"{token!r} produced {r.status_code}"


def test_a_token_signed_with_the_wrong_key_is_rejected():
    import jwt

    from security import decode_access_token

    forged = jwt.encode({"sub": "1"}, "not-the-real-key", algorithm="HS256")
    assert decode_access_token(forged) is None


def test_an_expired_token_is_rejected():
    from datetime import datetime, timedelta, timezone

    import jwt

    from config import settings
    from security import decode_access_token

    stale = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert decode_access_token(stale) is None
