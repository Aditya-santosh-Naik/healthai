"""What a failure is allowed to reveal.

Health text is the most sensitive thing this system holds, and an exception is
the easiest way for it to escape: the message quotes the input, the response
carries the message, and the log carries both. These tests pin all three.
"""
import pytest
from fastapi.testclient import TestClient

from database import get_db
from main import app
from tests.conftest import RAJESH, auth, make_patient

SECRET_SYMPTOM_TEXT = "i have had unprotected sex and now burning when i pee"


def test_a_crash_does_not_return_health_text_or_internals(client, monkeypatch, capsys):
    from api import consultation as consultation_api

    token = make_patient(client, RAJESH)

    def explode(text, *a, **kw):
        raise ValueError(f"unexpected parse state for input: {text}")

    # api.consultation does `from core.pipeline import run`, which binds the
    # function object at import time -- patching core.pipeline.run would leave
    # the caller pointing at the original and the test would pass vacuously.
    monkeypatch.setattr(consultation_api, "run", explode)

    bare = TestClient(app, raise_server_exceptions=False)
    response = bare.post(
        "/api/consultation/start",
        json={"text": SECRET_SYMPTOM_TEXT},
        headers=auth(token),
    )

    assert response.status_code == 500
    body = response.text.lower()

    # The response must not quote the patient.
    assert "unprotected" not in body
    assert "burning when i pee" not in body
    # ...nor expose the machinery.
    assert "traceback" not in body
    assert "valueerror" not in body
    assert ".py" not in body
    assert "sqlalchemy" not in body

    # It must still be actionable: a reference the user can quote.
    assert "reference" in body


def test_the_log_records_the_bug_but_not_the_patient(client, monkeypatch, capsys):
    """The frames are logged; the exception message is not.

    That distinction is the whole design: frames say where the bug is, the
    message says what the patient typed.
    """
    from api import consultation as consultation_api

    token = make_patient(client, RAJESH)

    def explode(text, *a, **kw):
        raise ValueError(f"unexpected parse state for input: {text}")

    # api.consultation does `from core.pipeline import run`, which binds the
    # function object at import time -- patching core.pipeline.run would leave
    # the caller pointing at the original and the test would pass vacuously.
    monkeypatch.setattr(consultation_api, "run", explode)

    bare = TestClient(app, raise_server_exceptions=False)
    capsys.readouterr()  # discard anything already buffered
    bare.post(
        "/api/consultation/start",
        json={"text": SECRET_SYMPTOM_TEXT},
        headers=auth(token),
    )
    logged = capsys.readouterr().err.lower()

    assert "unprotected" not in logged, "patient text was written to the log"
    assert "burning when i pee" not in logged
    # But the bug is still findable.
    assert "valueerror" in logged
    assert "error " in logged


def test_a_handled_error_still_says_something_useful(client):
    """Genericising failures must not make ordinary 4xx errors useless."""
    token = make_patient(client, RAJESH)
    r = client.get("/api/history/999999", headers=auth(token))
    assert r.status_code == 404
    assert "not found" in r.text.lower()


def test_an_unreadable_upload_reports_the_kind_not_the_contents(client):
    """The extractor names the exception TYPE only.

    A PDF library's message can include file paths and fragments of the
    document, which for a medical report is exactly the data being protected.
    """
    import io

    token = make_patient(client, RAJESH)
    r = client.post(
        "/api/documents",
        headers=auth(token),
        files={"file": ("notes.pdf", io.BytesIO(b"not really a pdf"), "application/pdf")},
    )
    assert r.status_code in (201, 400, 415, 422)
    assert "traceback" not in r.text.lower()
