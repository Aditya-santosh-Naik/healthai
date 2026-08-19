# HealthAI

A personalised, **fully offline** AI healthcare assistant. Final-year major project.

Most student symptom-checkers match keywords to diseases and print a fake percentage.
HealthAI instead maintains a patient profile, asks targeted follow-up questions when
evidence is insufficient, evaluates candidate conditions against structured evidence,
checks medication safety against the patient's actual drugs and allergies, and refuses
to output confident diagnoses it cannot support.

**Rules decide. The LLM only speaks.**

> HealthAI is an educational project, not a medical device. It does not diagnose,
> prescribe, or replace professional medical care.

---

## Quick start

Three things must be running: Ollama, the backend, and the frontend.

**1. Ollama** (once per machine)

```bash
ollama pull qwen2.5:3b
```

**2. Backend** — from `backend/`

```bash
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
```

Seed the demo patients:

```bash
.venv/Scripts/python.exe seed.py
```

Run it:

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

**3. Frontend** — from `frontend/`

```bash
npm install && npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend, so the browser only
ever sees one origin.

### Demo accounts

| Email | Profile | Why it exists |
|---|---|---|
| `rajesh@example.com` | 48, hypertension + type 2 diabetes, Amlong + Glycomet, **penicillin allergy**, non-veg | Main demo patient |
| `priya@example.com` | 29, GERD, Pan-D, **NSAID allergy**, vegetarian | Same symptoms, visibly different output |
| `arjun@example.com` | 35, vegan, smoker, self-medicating with Combiflam | Exercises the ADR path |

Password for all three: `demo123456`

---

## Verified hardware baseline (Day 1)

Measured on the target machine, not estimated:

| Metric | Value |
|---|---|
| GPU | RTX 4050 Laptop, 6141 MiB VRAM |
| Model | `qwen2.5:3b` (Ollama's `:3b` tag is the instruct build) |
| Placement | **100% GPU** |
| VRAM in use | 2151 MiB — leaves ~4 GB for browser and IDE |
| Throughput (warm) | ~57 tokens/sec |
| Cold load | ~46 s |

The cold load is the only latency risk in a demo. `ollama_keep_alive` is set to 30
minutes in `config.py` so the model stays resident once warmed.

---

## Architecture

See [docs/architecture.md](docs/architecture.md). In one paragraph: symptom extraction
is rules plus a controlled vocabulary; candidate evaluation is a deterministic
evidence-scoring engine over hand-encoded, source-cited condition definitions; red
flags short-circuit everything before reasoning begins; RAG retrieves passages for the
surviving candidates only. The LLM is called **once**, at the very end, and is asked
only to rephrase a completed structured assessment. It never chooses a condition, never
invents a fact, and never sees an unfiltered user message.

That is the answer to "how do you prevent hallucination?" — architecturally, not by
asking the model nicely.

---

## Layout

```
backend/    FastAPI app. core/ is the deterministic reasoning; llm/ only rephrases.
data/       All clinical knowledge as YAML + markdown. No clinical rule lives in Python.
frontend/   React 18 + Vite + Tailwind + shadcn/ui.
docs/       Architecture notes.
```

**Rule: no clinical knowledge hardcoded in Python.** Code reads data. This makes the
knowledge auditable, which is the point.

---

## Assumptions made where the spec was silent

- **Ollama model tag.** The spec names `qwen2.5:3b-instruct`; Ollama's `qwen2.5:3b`
  tag *is* the instruct build, and that is what is pulled and verified.
- **API origin.** Vite proxies `/api` to `127.0.0.1:8000` rather than the frontend
  calling an absolute backend URL. One origin in the browser, no CORS in dev.
- **Under-18 is refused at two layers.** The scope guard refuses at consultation time,
  and `patient_profiles.age` rejects under-18 at the schema boundary, so the state
  cannot exist in the database at all.
- **Account deletion** cascades through every child table via FK `ON DELETE CASCADE`
  with SQLite's `foreign_keys` pragma enabled.
- **Passwords** are capped at bcrypt's 72-byte limit and refused above it rather than
  silently truncated.

---

## Limitations

Stated plainly, because pretending otherwise would be the actual failure.

- **No clinical review.** No clinician validated the rules. The system biases toward
  escalation and never reassures.
- **Not trained on patient data, and deliberately so.** There is no learned model and
  no fine-tuning. Accuracy comes from hand-encoded rules that each carry a source URL
  from MedlinePlus, WHO, NIH, CDC or ICMR. See "Why no model training?" below.
- **Not validated against patient outcomes.** Not a medical device. Not for clinical use.
- Scoped to 14 conditions. Adults only.
- Under-18, pregnancy and mental-health crisis are refused by design.
- English only. Hinglish appears only as aliases in the symptom vocabulary.
- Text-layer PDFs only. No OCR, no handwriting.
- No encryption at rest. No DPDP compliance work.
- Herbal and ayurvedic interactions are out of scope.
- Dev-only JWT secret in `config.py`.

### Why no model training?

There is no validated, labelled clinical dataset available for this scope, and an
unvalidated neural classifier on medical data produces confident wrong answers with no
audit trail. Every rule here instead carries a citation, and the reasoning is fully
inspectable: for any assessment you can see exactly which symptoms supported it, which
contradicted it, and which source said so. That is testable and explainable in a way a
trained model at this scale would not be.
