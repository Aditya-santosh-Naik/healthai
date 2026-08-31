"""Day 1 foundation tests: schema, auth, profile CRUD, scope boundaries.

Run from the backend directory:  .venv/Scripts/python.exe -m pytest -q
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401  (registers every table)
from database import Base, get_db
from main import app

EXPECTED_TABLES = {
    "users",
    "patient_profiles",
    "patient_conditions",
    "patient_allergies",
    "patient_medications",
    "medical_documents",
    "extracted_facts",
    "consultations",
    "messages",
    "consultation_symptoms",
    "candidate_evidence",
    "medication_safety_results",
    "rag_retrievals",
    "recommendations",
    "feedback",
    "pdf_reports",
    "audit_logs",
}

VALID_PROFILE = {
    "name": "Test Patient",
    "age": 48,
    "sex": "male",
    "height_cm": 172,
    "weight_kg": 81,
    "blood_group": "B+",
    "diet_type": "non_veg",
    "smoker": False,
    "alcohol": True,
    "conditions": [{"condition_name": "Hypertension", "status": "active"}],
    "allergies": [{"allergen": "Penicillin", "allergen_class": "penicillin"}],
    "medications": [
        {"brand_name": "Amlong", "generic_name": "amlodipine",
         "dose": "5 mg", "status": "prescribed_taking"}
    ],
}


@pytest.fixture
def client():
    """Each test gets a clean in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.engine = engine
        yield c
    app.dependency_overrides.clear()


def register(client, email="user@example.com", password="testpass123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- schema -----------------------------------------------------------------

def test_every_spec_table_exists(client):
    actual = set(inspect(client.engine).get_table_names())
    assert EXPECTED_TABLES <= actual, f"missing: {EXPECTED_TABLES - actual}"


# --- auth -------------------------------------------------------------------

def test_register_login_and_me(client):
    token = register(client)
    r = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "testpass123"},
    )
    assert r.status_code == 200
    assert r.json()["has_profile"] is False

    r = client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"


def test_duplicate_email_rejected(client):
    register(client)
    r = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "testpass123"},
    )
    assert r.status_code == 409


def test_wrong_password_rejected(client):
    register(client)
    r = client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "nope12345"}
    )
    assert r.status_code == 401


def test_password_hash_is_never_stored_or_returned(client):
    token = register(client)
    body = client.get("/api/auth/me", headers=auth(token)).text
    assert "testpass123" not in body
    assert "password_hash" not in body


def test_protected_route_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth("garbage")).status_code == 401


# --- profile ----------------------------------------------------------------

def test_profile_required_before_use(client):
    token = register(client)
    assert client.get("/api/profile", headers=auth(token)).status_code == 409


def test_onboarding_creates_related_rows_with_provenance(client):
    token = register(client)
    r = client.post("/api/profile", json=VALID_PROFILE, headers=auth(token))
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["conditions"][0]["condition_name"] == "Hypertension"
    assert body["allergies"][0]["allergen_class"] == "penicillin"
    assert body["medications"][0]["generic_name"] == "amlodipine"

    # Invariant: nothing enters the profile as AI-inferred.
    for section in ("conditions", "allergies", "medications"):
        for row in body[section]:
            assert row["provenance"] == "user_entered"
            assert row["confirmed_at"] is not None


def test_under_18_can_register_but_is_refused_a_consultation(client):
    """Spec invariant 9: under-18 is out of scope. The refusal MOVED, in full.

    It used to be a 422 at the schema boundary, which made the state
    unrepresentable but told a 15-year-old only that their age was "invalid".
    Registration now accepts them; the scope guard refuses at pipeline step 0,
    every time, with an explanation and a paediatric referral. That is where
    the clinical rule belongs -- and it is enforced per consultation rather
    than once at signup, so it cannot be bypassed by editing a profile later.
    """
    token = register(client)
    child = {**VALID_PROFILE, "age": 12}
    assert client.post("/api/profile", json=child, headers=auth(token)).status_code == 201

    r = client.post(
        "/api/consultation/start", json={"text": "fever and cough"}, headers=auth(token)
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["outcome"] == "refused", "a 12-year-old was assessed"
    assert body["refusal"]["category"] == "under_18"
    assert body["candidates"] == [], "a refusal must name no condition"


def test_one_user_one_profile(client):
    token = register(client)
    client.post("/api/profile", json=VALID_PROFILE, headers=auth(token))
    r = client.post("/api/profile", json=VALID_PROFILE, headers=auth(token))
    assert r.status_code == 409


def test_profile_is_isolated_between_users(client):
    token_a = register(client, "a@example.com")
    token_b = register(client, "b@example.com")
    client.post("/api/profile", json=VALID_PROFILE, headers=auth(token_a))
    med_id = client.get("/api/profile", headers=auth(token_a)).json()["medications"][0]["id"]

    # B has no profile at all, and must not be able to touch A's rows.
    assert client.get("/api/profile", headers=auth(token_b)).status_code == 409
    client.post("/api/profile", json={**VALID_PROFILE, "name": "B"}, headers=auth(token_b))
    r = client.delete(f"/api/profile/medications/{med_id}", headers=auth(token_b))
    assert r.status_code == 404


def test_medication_needs_a_name(client):
    token = register(client)
    client.post("/api/profile", json=VALID_PROFILE, headers=auth(token))
    r = client.post(
        "/api/profile/medications",
        json={"dose": "5 mg", "status": "prescribed_taking"},
        headers=auth(token),
    )
    assert r.status_code == 422


def test_account_delete_cascades(client):
    token = register(client)
    client.post("/api/profile", json=VALID_PROFILE, headers=auth(token))
    assert client.delete("/api/auth/me", headers=auth(token)).status_code == 204
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


# --- disclaimer -------------------------------------------------------------

def test_disclaimer_is_available_and_does_not_reassure(client):
    """Invariant 6: never reassure. Invariant 11: disclaimer everywhere."""
    text = client.get("/api/disclaimer").json()["disclaimer"].lower()
    assert "not a medical device" in text
    for banned in ("nothing serious", "you are fine", "no need to see"):
        assert banned not in text
