"""Seed demo patients.

Idempotent: re-running deletes and recreates the demo accounts. Real accounts
are untouched.

Run from the backend directory:
    .venv/Scripts/python.exe seed.py
"""
from datetime import date, datetime, timezone

from database import SessionLocal, init_db
from models import (
    PatientAllergy,
    PatientCondition,
    PatientMedication,
    PatientProfile,
    User,
)
from models.enums import DietType, MedicationStatus, Provenance, Sex
from security import hash_password

DEMO_PASSWORD = "demo123456"

# Three profiles chosen so that identical symptoms produce visibly different
# medication-safety and diet output (acceptance test 10, demo step 6).
DEMO_PATIENTS = [
    {
        "email": "rajesh@example.com",
        "profile": {
            "name": "Rajesh Kumar",
            "age": 48,
            "sex": Sex.MALE,
            "height_cm": 172.0,
            "weight_kg": 81.0,
            "blood_group": "B+",
            "diet_type": DietType.NON_VEG,
            "smoker": False,
            "alcohol": True,
        },
        "conditions": [
            ("Hypertension", date(2019, 6, 1)),
            ("Type 2 Diabetes", date(2021, 3, 15)),
        ],
        "allergies": [
            ("Penicillin", "penicillin", "Widespread rash", "moderate"),
        ],
        "medications": [
            ("Amlong", "amlodipine", "5 mg", "once daily", "Blood pressure"),
            ("Glycomet", "metformin", "500 mg", "twice daily", "Blood sugar"),
        ],
    },
    {
        "email": "priya@example.com",
        "profile": {
            "name": "Priya Sharma",
            "age": 29,
            "sex": Sex.FEMALE,
            "height_cm": 160.0,
            "weight_kg": 54.0,
            "blood_group": "O+",
            "diet_type": DietType.VEG,
            "smoker": False,
            "alcohol": False,
        },
        "conditions": [
            ("GERD", date(2023, 11, 5)),
        ],
        "allergies": [
            ("Ibuprofen", "nsaid", "Stomach pain and hives", "moderate"),
        ],
        "medications": [
            ("Pan-D", "pantoprazole", "40 mg", "once daily", "Acid reflux"),
        ],
    },
    {
        "email": "arjun@example.com",
        "profile": {
            "name": "Arjun Nair",
            "age": 35,
            "sex": Sex.MALE,
            "height_cm": 178.0,
            "weight_kg": 70.0,
            "blood_group": "A+",
            "diet_type": DietType.VEGAN,
            "smoker": True,
            "alcohol": False,
        },
        "conditions": [],
        "allergies": [],
        # Self-medicating: exercises the ADR and duplicate-therapy paths.
        "medications": [
            ("Combiflam", "ibuprofen+paracetamol", "1 tablet", "as needed", "Body ache"),
        ],
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        for spec in DEMO_PATIENTS:
            email = spec["email"]
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                db.delete(existing)
                db.commit()

            user = User(email=email, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()

            profile = PatientProfile(user_id=user.id, **spec["profile"])
            db.add(profile)
            db.flush()

            for name, onset in spec["conditions"]:
                db.add(
                    PatientCondition(
                        profile_id=profile.id,
                        condition_name=name,
                        status="active",
                        onset_date=onset,
                        provenance=Provenance.USER_ENTERED,
                        confirmed_at=_now(),
                    )
                )
            for allergen, klass, reaction, severity in spec["allergies"]:
                db.add(
                    PatientAllergy(
                        profile_id=profile.id,
                        allergen=allergen,
                        allergen_class=klass,
                        reaction=reaction,
                        severity=severity,
                        provenance=Provenance.USER_ENTERED,
                        confirmed_at=_now(),
                    )
                )
            for brand, generic, dose, freq, reason in spec["medications"]:
                db.add(
                    PatientMedication(
                        profile_id=profile.id,
                        brand_name=brand,
                        generic_name=generic,
                        dose=dose,
                        frequency=freq,
                        route="oral",
                        reason=reason,
                        status=MedicationStatus.PRESCRIBED_TAKING,
                        provenance=Provenance.USER_ENTERED,
                        confirmed_at=_now(),
                    )
                )
            db.commit()
            print(f"  seeded {profile.name:<14} {email}")
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding demo patients...")
    seed()
    print(f"\nDone. All demo accounts use password: {DEMO_PASSWORD}")
