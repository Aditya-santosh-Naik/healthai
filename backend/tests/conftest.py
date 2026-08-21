"""Shared test fixtures.

The LLM is stubbed out by default. Two reasons: tests stay fast and hermetic,
and every assertion then runs against the deterministic template fallback,
which is exactly the path invariant 10 promises will work when Ollama is down.
A test that wants the real model can opt back in.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401  (registers every table)
from database import Base, get_db
from main import app

# --- profiles used across the acceptance tests ------------------------------

RAJESH = {
    "name": "Rajesh Kumar",
    "age": 48,
    "sex": "male",
    "height_cm": 172,
    "weight_kg": 81,
    "diet_type": "non_veg",
    "smoker": False,
    "alcohol": True,
    "conditions": [
        {"condition_name": "Hypertension", "status": "active"},
        {"condition_name": "Type 2 Diabetes", "status": "active"},
    ],
    "allergies": [{"allergen": "Penicillin", "allergen_class": "penicillin"}],
    "medications": [
        {"brand_name": "Amlong", "generic_name": "amlodipine", "status": "prescribed_taking"},
        {"brand_name": "Glycomet", "generic_name": "metformin", "status": "prescribed_taking"},
    ],
}

PRIYA = {
    "name": "Priya Sharma",
    "age": 29,
    "sex": "female",
    "diet_type": "veg",
    "smoker": False,
    "alcohol": False,
    "conditions": [{"condition_name": "GERD", "status": "active"}],
    "allergies": [{"allergen": "Ibuprofen", "allergen_class": "nsaid"}],
    "medications": [
        {"brand_name": "Pan-D", "generic_name": "pantoprazole", "status": "prescribed_taking"}
    ],
}

# A patient self-medicating with an NSAID, for the interaction test.
NSAID_USER = {
    "name": "Arjun Nair",
    "age": 52,
    "sex": "male",
    "diet_type": "veg",
    "conditions": [{"condition_name": "Hypertension", "status": "active"}],
    "allergies": [],
    "medications": [
        {"brand_name": "Amlong", "generic_name": "amlodipine", "status": "prescribed_taking"},
        {"brand_name": "Combiflam", "status": "self_medicating"},
    ],
}


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Force the deterministic fallback for every test by default."""
    from llm import client as llm_client

    def unavailable(_system: str, _user: str) -> llm_client.LLMResult:
        return llm_client.LLMResult(
            text="", ok=False, model="stub", error="stubbed out in tests"
        )

    monkeypatch.setattr(llm_client, "generate", unavailable)


@pytest.fixture
def client():
    """A clean in-memory database per test."""
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


# --- helpers ----------------------------------------------------------------

def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_patient(client, profile: dict, email: str = "p@example.com") -> str:
    """Register a user and attach a profile. Returns the bearer token."""
    r = client.post(
        "/api/auth/register", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]

    r = client.post("/api/profile", json=profile, headers=auth(token))
    assert r.status_code == 201, r.text
    return token


def start(client, token: str, text: str) -> dict:
    r = client.post(
        "/api/consultation/start", json={"text": text}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    return r.json()


def answer(client, token: str, turn: dict, reply: str) -> dict:
    """Answer whatever question the turn is asking."""
    r = client.post(
        f"/api/consultation/{turn['consultation_id']}/answer",
        json={"symptom_code": turn["question"]["symptom_code"], "answer": reply},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


def run_to_completion(client, token: str, text: str, replies: dict[str, str]) -> dict:
    """Drive a consultation to an outcome, answering from a lookup table."""
    turn = start(client, token, text)
    for _ in range(6):
        if turn["outcome"] != "needs_question":
            break
        code = turn["question"]["symptom_code"]
        turn = answer(client, token, turn, replies.get(code, "No"))
    return turn


def all_text(payload) -> str:
    """Every string in a response, flattened. Used for invariant sweeps."""
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return " ".join(parts)
