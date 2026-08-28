# HealthAI — Handoff Report

**Generated 2026-08-28 from the live repo, not from memory.** Every number here
was measured by running the thing.

> **Naming note:** this project is called **HealthAI**. The string "MediBridge"
> appears nowhere in the codebase. If a rename is intended it has not happened
> yet and would touch `backend/config.py` (`app_name`),
> `frontend/src/components/Layout.tsx`, `index.html`, and the docs.

**Status: complete and working.** All 7 planned days delivered. 86 tests pass,
working tree clean at commit `0733750`, 15 commits total.

---

## 1. Project structure

```
healthai/
├── CLAUDE.md                        Full spec + build state (the project's memory)
├── README.md                        What it is, how to run, limitations
├── docs/
│   ├── architecture.md              Why it is shaped this way (for the viva)
│   ├── TESTING-GUIDE.md             Copy-paste manual test inputs
│   └── HANDOFF.md                   This file
├── backend/
│   ├── main.py                      FastAPI app, router wiring, /api/health
│   ├── config.py                    Settings; generates + persists the JWT key
│   ├── database.py                  SQLAlchemy engine, session, FK pragma
│   ├── security.py                  bcrypt hashing, JWT encode/decode
│   ├── seed.py                      Creates the 3 demo patients (idempotent)
│   ├── requirements.txt             Pinned Python dependencies
│   ├── models/                      SQLAlchemy ORM, one file per domain
│   │   ├── enums.py                 Provenance, bands, statuses as StrEnum
│   │   ├── user.py                  users
│   │   ├── profile.py               profiles, conditions, allergies, medications
│   │   ├── document.py              medical_documents, extracted_facts
│   │   ├── consultation.py          consultations, messages, symptoms, evidence,
│   │   │                            safety results, retrievals, recs, feedback, pdfs
│   │   └── audit.py                 audit_logs
│   ├── schemas/                     Pydantic request/response models
│   │   ├── auth.py                  register/login/token/user
│   │   ├── profile.py               profile + sub-resources, enforces age >= 18
│   │   └── consultation.py          TurnOut — the single shape the UI renders
│   ├── api/                         HTTP layer only, no clinical logic
│   │   ├── deps.py                  get_current_user / get_current_profile
│   │   ├── auth.py                  register, login, me, delete account
│   │   ├── profile.py               profile CRUD + conditions/allergies/meds
│   │   ├── consultation.py          start/message/answer/feedback; persists + audits
│   │   ├── history.py               list + detail rebuilt from stored rows
│   │   ├── documents.py             upload, list, confirm-before-store
│   │   └── reports.py               PDF download
│   ├── core/                        Deterministic reasoning. No LLM anywhere here.
│   │   ├── pipeline.py              Orchestrates steps 0-10 in spec order
│   │   ├── knowledge.py             Loads + caches every data/*.yaml
│   │   ├── scope_guard.py           Refuse under-18 / pregnancy / MH crisis
│   │   ├── red_flags.py             Escalate and halt, before any reasoning
│   │   ├── text_norm.py             Canonicalisation shared by text and aliases
│   │   ├── negation.py              Forward-scope negation cue detection
│   │   ├── symptom_extraction.py    Text -> symptom codes, duration, severity
│   │   ├── evidence_engine.py       Scores 14 candidates, assigns ordinal bands
│   │   ├── sufficiency.py           Assess now, or ask another question?
│   │   ├── followup_engine.py       Picks the most informative next question
│   │   ├── medication_safety.py     drug x drug/allergy/condition + ADR
│   │   ├── medication_guidance.py   Three tiers; never prescribes
│   │   ├── diet_lifestyle.py        Per-patient filtered diet and lifestyle
│   │   └── patient_context.py       Profile -> facts the engines consume
│   ├── rag/
│   │   ├── embedder.py              bge-small on CPU, lazy-loaded
│   │   ├── index.py                 Chunk, embed, save/load .npz (no pickle)
│   │   └── retriever.py             Cosine search filtered by candidate
│   ├── llm/
│   │   ├── client.py                httpx -> Ollama + output safety filter
│   │   ├── prompts.py               EVERY prompt in the project lives here
│   │   └── fallback.py              Deterministic templates when the LLM fails
│   ├── documents/
│   │   ├── extractor.py             pdfplumber text extraction, no OCR
│   │   └── medical_parser.py        Rule-based fact extraction from that text
│   ├── reports/pdf.py               fpdf2 report with watermark + disclaimer
│   ├── audit/logger.py              Writes audit_logs rows
│   ├── tools/eval_extraction.py     Measures NL extraction against labelled data
│   └── tests/
│       ├── conftest.py              Fixtures; stubs the LLM by default
│       ├── test_day1_foundation.py  Schema, auth, profile boundaries (14)
│       ├── test_acceptance.py       The 10 spec acceptance cases (29)
│       └── test_invariants.py       The 12 safety invariants (43)
├── data/                            All clinical knowledge. None of it in Python.
│   ├── symptoms.yaml                101 codes, 720 aliases, implication graph
│   ├── conditions/*.yaml            14 conditions, each source-cited
│   ├── red_flags.yaml               15 rules + screening list + caps
│   ├── drugs.yaml                   55 medicines, Indian brand -> generic
│   ├── interactions.yaml            52 rules + allergy class cross-reactivity
│   ├── diet_templates.yaml          Per-condition, tagged for filtering
│   ├── treatment_expectations.yaml  Does this need a prescription?
│   ├── knowledge/*.md               60 source-cited RAG passages -> 120 chunks
│   ├── eval/nl_symptom_cases.yaml   96 labelled natural-language test cases
│   └── index.npz                    Built artefact (gitignored)
└── frontend/
    └── src/
        ├── App.tsx                  Routes + auth guards
        ├── lib/auth.tsx             Auth context, token handling
        ├── api/client.ts            fetch wrapper, bearer token, error shapes
        ├── api/consultation.ts      TypeScript mirrors of the backend schemas
        ├── components/Layout.tsx    Nav + the always-on disclaimer bar
        ├── components/ResultView.tsx  The result page, spec section-14 order
        ├── components/ui/*.tsx       8 vendored shadcn/ui components
        └── pages/                   Login, Onboarding, Dashboard, Consultation,
                                     History, Documents, Profile
```

---

## 2. Features fully working

### Auth and profile
- **Register / login / delete account** — `api/auth.py`. bcrypt via passlib,
  JWT via python-jose. Login errors are identical for unknown email and wrong
  password so account existence does not leak.
- **Onboarding wizard** — `pages/Onboarding.tsx`, 4 steps. Submits to
  `POST /api/profile`. **Age < 18 is rejected at the Pydantic boundary**
  (`schemas/profile.py`, `MIN_AGE`), so the state cannot exist in the DB.
- **Profile CRUD** — conditions, allergies, medications as separate related
  tables, each carrying a `provenance` enum.

### The consultation pipeline (`core/pipeline.py::run`)
Runs steps 0-10 in spec order. Everything except step 10 is deterministic.

- **Scope guard** (`scope_guard.py::check`) — refuses under-18, pregnancy,
  mental-health, and self-harm crisis with a referral. Crisis language
  outranks a physical complaint in the same sentence.
- **Red-flag escalation** (`red_flags.py::check`) — runs *before* reasoning.
  On a hit it returns immediately: no candidates, no medication advice, no
  diet. Only positively-reported symptoms can trigger it.
- **Symptom extraction** (`symptom_extraction.py::extract`) — normalise →
  stopword-strip → clause split → longest-alias match → negation scope →
  duration/severity → implication closure. Handles Indian English
  ("loose motions", "bukhar", "pet dard").
- **Negation** (`negation.py`) — forward-scope cue detection with a
  pseudo-negation list ("no better" must not negate). A stated negative is
  stored as `present=False`, which is evidence, not absence.
- **Evidence engine** (`evidence_engine.py::evaluate`) — scores all 14
  candidates; assigns ordinal bands by leader-vs-runner-up margin. The numeric
  score is persisted for audit and **never leaves the server** (asserted by a
  test).
- **Sufficiency gate** (`sufficiency.py::assess`) — can refuse to assess.
  Stops early when the leader is decisive (`DECISIVE_LEAD = 5`).
- **Follow-up engine** (`followup_engine.py::next_question`) — max 3 safety
  screening questions, then questions ranked by **expected information across
  both answers**. Budget 10, typically uses 4-8.
- **Medication safety** (`medication_safety.py::evaluate`) — four checks:
  drug×drug, drug×allergy **by class**, drug×condition, and ADR (does a current
  medicine's side-effect list intersect the reported symptoms?). Combination
  products expand to components (Combiflam → ibuprofen + paracetamol).
  Unrecognised medicines are reported, never silently skipped.
- **Medication guidance** (`medication_guidance.py::build`) — three tiers:
  what to avoid (naming their drugs), OTC general information with no doses,
  and whether the condition needs a doctor-prescribed course.
- **RAG** (`rag/retriever.py::retrieve`) — filtered by surviving candidates,
  never run on raw user text. Top 5 above cosine 0.30.
- **Diet and lifestyle** (`diet_lifestyle.py::build`) — filtered by diet type,
  allergies and conditions. Follows the leading candidate only.
- **One LLM call** (`llm/client.py::generate`) — rephrases the finished
  assessment. Output passes a safety filter; failure falls back to templates.

### Surfaces
- **Consultation chat** — tappable options, safety/discriminating badges.
- **Result page** (`ResultView.tsx`) — spec section-14 order, including
  "Also considered, and set aside" (why not a common cold?) and the copyable
  **"What to tell your doctor"** block.
- **History** — list + detail rebuilt from stored rows; the LLM is not re-run.
- **PDF export** — fpdf2, watermark + disclaimer, all three outcome types.
- **Document upload** — text-layer PDF → candidate facts → **confirm before
  store**. Nothing reaches the profile without explicit confirmation.
- **Feedback** — helpful / not helpful.
- **Audit log** — every AI output with inputs, retrieved sources, timings.

### Verified numbers
| | |
|---|---|
| Tests | **86 pass** (14 foundation + 29 acceptance + 43 invariant) |
| NL extraction | **100%** cases / symptom recall / negation / duration; 0 false positives |
| Acceptance tests 1-10 | all automated and passing |
| API endpoints | 26 |
| Demo rehearsal | passes end to end in ~20-38s |

---

## 3. Partially done

Genuinely little. Two items:

1. **`extracted_facts.review_status = "edited"`** — the enum
   (`models/enums.py::ReviewStatus`) allows it, but `api/documents.py::confirm_facts`
   only ever sets `confirmed` or `rejected`. There is no edit-before-confirm UI.
   *To finish:* add a text input per fact in `pages/Documents.tsx` and accept an
   edited value in the confirm payload.

2. **`ConsultationSymptom.onset`** — column exists, is never written.
   Duration is captured; onset wording is not. *To finish:* have
   `symptom_extraction` return the matched onset phrase and store it.

---

## 4. Tech stack (actually installed)

**Runtime:** Python 3.12.10 · Node 24.19.0 · Ollama 0.33.0 · Windows 11

**Backend**
| Package | Version | Used for |
|---|---|---|
| fastapi | 0.115.6 | HTTP API |
| uvicorn | 0.34.0 | ASGI server |
| pydantic | 2.10.4 | Validation, response shapes |
| pydantic-settings | 2.7.0 | Config from env |
| SQLAlchemy | 2.0.36 | ORM, 17 tables |
| python-jose | 3.3.0 | JWT |
| passlib + bcrypt | 1.7.4 / 4.0.1 | Password hashing |
| PyYAML | 6.0.2 | All knowledge files + front matter |
| httpx | 0.28.1 | Ollama client + test client |
| sentence-transformers | 3.3.1 | bge-small embeddings |
| torch | 2.13.0 | (transitive, CPU only) |
| numpy | 2.2.1 | Vector index + cosine search |
| pdfplumber | 0.11.5 | PDF text extraction |
| fpdf2 | 2.8.2 | PDF generation |
| pytest | 8.3.4 | Tests |
| python-multipart | 0.0.20 | File upload |

**Frontend:** React 18.3.1 · Vite 8.2 · TypeScript 6.0 · Tailwind 3.4.17 ·
react-router-dom 6.28 · 4 Radix primitives · lucide-react · CVA + clsx +
tailwind-merge

**No paid APIs and no API keys.** The only outbound HTTP in the codebase is
`llm/client.py` → `localhost:11434`.

---

## 5. Data

**Everything is local. Nothing real, nothing personal.**

- **Database:** SQLite at `backend/healthai.db`, 17 tables, created by
  `database.py::init_db`. Gitignored. Currently holds 3 seeded demo users and
  5 test consultations.
- **Demo patients** (`seed.py`, idempotent, password `demo123456`):
  Rajesh Kumar (48M, hypertension + T2 diabetes, Amlodipine + Metformin,
  penicillin allergy, non-veg) · Priya Sharma (29F, GERD, Pantoprazole, NSAID
  allergy, vegetarian) · Arjun Nair (35M, vegan, smoker, self-medicating
  Combiflam). Chosen so identical symptoms produce visibly different output.
- **Clinical knowledge:** hand-curated YAML in `data/`. Every condition, red
  flag, drug and interaction row carries a `source_url` to MedlinePlus / WHO /
  CDC / NIH / NHS. A test iterates the whole base and fails if any row lacks
  one. **No clinical rule is hardcoded in Python.**
- **RAG corpus:** 60 markdown files, hand-written from those sources, chunked
  on H2 headings into 120 passages.
- **Vector index:** `data/index.npz` — NumPy matrix + JSON metadata, built by
  `python -m rag.index`. Gitignored.
- **Eval set:** `data/eval/nl_symptom_cases.yaml`, 96 labelled phrasings.

---

## 6. AI / ML components

There are exactly **two** ML pieces, and neither makes a clinical decision.

### The LLM — `llm/client.py`, `llm/prompts.py`, `llm/fallback.py`
- **Model:** `qwen2.5:3b` via Ollama on localhost. 100% GPU, ~2.1 GB VRAM,
  ~57 tok/s warm, ~46 s cold load (mitigated by `keep_alive=30m`).
- **Called exactly once per assessment**, at step 10. Temperature 0.3,
  600 max tokens, 45 s timeout. A test counts the calls.
- **What it receives:** a *completed* structured assessment plus retrieved
  passages — never the raw user message. It cannot pick a condition because it
  is never asked to.
- **Prompts:** `SYSTEM_PROMPT` and `ESCALATION_SYSTEM_PROMPT` in `prompts.py`,
  and nowhere else. Eight hard rules: only given facts, no probability, no
  medicine names or doses, no stopping medication, never reassure, never use
  the word "diagnosis".
- **Output filter** (`client.py::check_output`) rejects percentages,
  probability wording ("most likely"), doses, reassurance, stop-medicine
  advice, and asserted diagnoses. "Your doctor can confirm the diagnosis" is
  deliberately allowed. Rejected output falls back to templates.
- **Fallback** (`fallback.py`) produces the full result deterministically. The
  entire test suite runs on this path.

### Embeddings — `rag/embedder.py`
- `BAAI/bge-small-en-v1.5` via sentence-transformers, **CPU**, 384 dims.
- Used only to embed the 120 corpus chunks and the retrieval query. Query is
  built from condition *display names*, never user text.
- Cosine similarity over a NumPy matrix. No vector database — at 120 chunks it
  would be cargo-culting.

### Deliberately NOT AI
Symptom extraction, negation, candidate scoring, sufficiency, question
selection, medication safety, and diet are **all rules**. That is the project's
central claim.

---

## 7. Known issues

**Zero TODO/FIXME/HACK markers in the codebase** (verified by grep).

Real limitations, in rough order of how likely an examiner is to raise them:

1. **No clinical review.** No qualified clinician validated the knowledge base.
   It encodes published guidance and biases toward escalation, but nobody
   checked the encoding.
2. **Evidence weights are judgement, not fitted.** +3 for a hallmark is a
   reasonable choice, not a learned parameter.
3. **14 conditions is a closed world.** Anything outside is invisible.
   Mitigated by red flags and the sufficiency gate.
4. **The eval set is author-written.** 100% means it handles the phrasings
   anticipated, not all phrasings.
5. **Spec numbers came in under target** — red flags 15 (spec said ~30),
   interactions 52 (~80), knowledge files 60 (~150). Depth is intact; counts
   are short.
6. **`Vitals entry: temperature`** is listed in the spec (§15) and was never
   built.
7. **No encryption at rest.** SQLite is plaintext; the JWT key sits in
   `backend/.secret_key` next to it.
8. **Stack deviation:** WeasyPrint replaced by **fpdf2** — WeasyPrint needs GTK
   libraries unavailable on this Windows machine (confirmed by import failure).
9. **`history` does not restore `medication_guidance`** — only safety findings
   and diet are persisted; the three-tier guidance is recomputed live and shows
   empty when reopening an old consultation.
10. **Two SQLAlchemy footguns already hit and fixed** — worth knowing: a
    `default=True` on a nullable column silently converted "Not sure" into
    "Yes"; and pickling a dataclass tied the index file to the module path it
    was built from.

---

## 8. How to run it

**Prerequisites:** Python 3.11+, Node 18+, Ollama with `ollama pull qwen2.5:3b`.

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe seed.py             # 3 demo patients
.venv/Scripts/python.exe -m rag.index        # build the vector index
.venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

```bash
# Frontend (second terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

**Env variables: none required.** All settings have working defaults in
`config.py`; override with the `HEALTHAI_` prefix (e.g.
`HEALTHAI_OLLAMA_MODEL`, `HEALTHAI_SECRET_KEY`). The JWT signing key is
generated on first run into `backend/.secret_key` (gitignored).

**First run downloads** the bge-small model (~130 MB) from HuggingFace. After
that everything is offline.

**Logins:** `rajesh@example.com` / `priya@example.com` / `arjun@example.com`,
password `demo123456`.

**Verify:**
```bash
cd backend
.venv/Scripts/python.exe -m pytest -q                 # 86 tests
.venv/Scripts/python.exe -m tools.eval_extraction     # 100% on 4 metrics
curl http://localhost:8000/api/health                 # ollama + index status
```

**Gotchas**
- If port 8000 is held, find the PID with `netstat -ano | findstr :8000`.
- `rm healthai.db` fails while uvicorn is running — stop it first.
- The app works with Ollama down; narration falls back to templates.

---

## 9. Not started

Deliberate scope decisions, all recorded in `CLAUDE.md` §15:

| Missing | Why |
|---|---|
| Deployment / Docker / CI | Explicitly cut. Runs locally only. |
| Multi-profile accounts | One user, one profile by design. |
| OCR for scanned documents | Cut. Text-layer PDFs only, with a graceful message. |
| Multilingual UI | English only; Hinglish lives in the alias table. |
| Voice / image input | Cut. |
| ABHA / ABDM integration | Cut. |
| Chronic tracking over time | Cut. Episodic consultations only. |
| Fine-tuning | Cut. Local inference only. |

Genuinely absent rather than decided:

- **No frontend tests.** All 86 tests are backend. No Vitest/RTL/Playwright.
  This is the largest real gap — the UI is verified only by hand and by the
  scripted rehearsal.
- **No rate limiting, MFA, CSRF protection, or security review.** Tokens live
  in `localStorage`.
- **No DPDP compliance work** — no consent capture, retention policy, or data
  export.
- **No structured logging or error tracking.** Uvicorn's default only.
- **No database migrations.** Schema changes need `rm healthai.db` + reseed.
  Alembic was never added.
- **No clinical vignette validation set** reviewed by a doctor.

---

## 10. If you pick this up next

The highest-value work, in order:

1. **Frontend tests** — the only substantial untested surface.
2. **Close the spec number gaps** — red flags 15→30, interactions 52→80,
   knowledge 60→150 files. Pure data entry in `data/`, no code changes.
3. **Add temperature entry** — the one spec item never built.
4. **Persist `medication_guidance`** so history detail matches the live result
   (same class of bug as the two already fixed there).

Read `CLAUDE.md` first — it is the spec and the build log. `docs/architecture.md`
explains the design decisions; `docs/TESTING-GUIDE.md` has copy-paste inputs for
every feature.
