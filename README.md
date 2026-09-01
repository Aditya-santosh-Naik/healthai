# HealthAI

A personalised, offline health assistant that shows its reasoning.

Final-year major project. Runs entirely on one laptop: no internet calls, no
paid APIs, no cloud services, no API keys.

---

## The claim

Most student symptom-checkers match keywords to diseases and print a fake
percentage. HealthAI does something different:

- it **maintains a patient profile** and reasons about *that* patient
- it **asks targeted follow-up questions** when the evidence is thin
- it **evaluates candidates against structured evidence**, showing what
  supports and what contradicts each one
- it **checks medication safety** against the patient's actual drugs, allergy
  classes and conditions
- it **refuses to output a confident answer it cannot support**

The safety architecture is the intellectual content of the project, not a
wrapper around it.

---

## Running it on Windows

### 1. Install the prerequisites

| | Version | Where |
|---|---|---|
| **Python** | 3.11 or newer | [python.org](https://www.python.org/downloads/) — **tick "Add python.exe to PATH"** on the first screen |
| **Node** | 18 or newer | [nodejs.org](https://nodejs.org) — the LTS installer |
| **Ollama** | any | [ollama.com](https://ollama.com) — optional, see below |

Check the terminal can see all three:

```bash
python --version && node --version && ollama --version
```

Ollama is optional. Without it the app still works end to end — every AI
surface has a deterministic fallback — but the final wording comes from
templates instead of the model. With it, pull the model once (~2 GB):

```bash
ollama pull qwen2.5:3b
```

### 2. Enable Long Path support — one time, needs admin

PyTorch ships header files whose paths are longer than Windows' default
260-character limit, so **`pip install` fails part-way through without this.**
Open PowerShell **as Administrator** and run:

```bash
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

Then close and reopen the terminal. You can skip this only if you clone to a
short path such as `C:\healthai`.

### 3. Clone

```bash
git clone https://github.com/Aditya-santosh-Naik/healthai.git
```

### 4. Set up the backend

Takes a few minutes: about 700 MB of packages, mostly PyTorch, then a 130 MB
embedding model. All four commands are safe to re-run.

```bash
cd healthai\backend
```

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe seed.py
```

```bash
.venv\Scripts\python.exe -m rag.index
```

`seed.py` creates the three demo patients. `rag.index` builds the vector index.

### 5. Set up the frontend

```bash
cd healthai\frontend && npm install
```

### 6. Run it

Two terminals, kept open.

Backend:

```bash
cd healthai\backend && .venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

Frontend:

```bash
cd healthai\frontend && npm run dev
```

Open **http://localhost:5173**.

### 7. Log in

Password `demo123456` for all three. The profiles differ deliberately, so the
same symptoms produce visibly different medication and diet output:

| Email | Profile |
|---|---|
| `rajesh@example.com` | 48M, hypertension + type 2 diabetes, Amlodipine + Metformin, penicillin allergy, non-veg |
| `priya@example.com` | 29F, GERD, Pantoprazole, NSAID allergy, vegetarian |
| `arjun@example.com` | 35M, vegan, smoker, self-medicating with Combiflam |

`GET /api/health` reports whether Ollama and the vector index are up.

---

## Running it on macOS or Linux

Identical, minus step 2, and the virtual environment puts Python in `bin/`
rather than `Scripts/`:

```bash
git clone https://github.com/Aditya-santosh-Naik/healthai.git && cd healthai/backend
```

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

On **Linux only**, install the CPU build of PyTorch first — the default PyPI
wheel bundles CUDA and is several GB, and the embedder runs on CPU anyway:

```bash
.venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
```

```bash
.venv/bin/python seed.py && .venv/bin/python -m rag.index
```

```bash
.venv/bin/python -m uvicorn main:app --port 8000
```

```bash
cd ../frontend && npm install && npm run dev
```

---

## Troubleshooting

**`pip install` dies on a long filename**, or one mentioning
`predicated_tile_access_iterator`. Long Path support is off — do step 2, reopen
the terminal, and run the `pip install` again.

**`OSError: [WinError 4551] An Application Control policy has blocked this
file`**, naming `torch_global_deps.dll`. Windows **Smart App Control** is
blocking PyTorch's unsigned DLLs. It has no exclusion list and is not intended
for development machines. Turn it off in Windows Security → App & browser
control → Smart App Control → Off. **This is permanent — Windows will not let
you switch it back on without resetting the PC.** Check the current state with:

```bash
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy" -Name VerifiedAndReputablePolicyState
```

`1` means enforced, `0` means off. Symptom if you miss it: about 35 tests fail
for no obvious reason, all of them touching retrieval.

**`python` opens the Microsoft Store.** The PATH entry is missing. Re-run the
Python installer, choose Modify, and tick "Add python.exe to PATH".

**Port 8000 or 5173 is already in use.** Find the process and stop it:

```bash
netstat -ano | findstr :8000
```

**The result page says the AI service is unavailable.** Ollama is not running.
Start it, or carry on — the deterministic fallback still produces a full
assessment.

**Checking the install worked.** From `backend`, with the virtual environment
built:

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

324 tests should pass.

---

## The pipeline

```
User message
  │
  ├─ [0] Scope guard        under-18 / pregnancy / mental-health → refuse + refer, STOP
  ├─ [1] Red-flag check     emergency pattern → escalate, STOP
  ├─ [2] Symptom extraction vocabulary + aliases + negation + duration/severity
  ├─ [3] Patient context    profile conditions, allergies, medicines, age
  ├─ [4] Evidence engine    score all 14 candidates on structured evidence
  ├─ [5] Sufficiency check  insufficient → [6] ask a question, await answer
  ├─ [7] Medication safety  drug↔drug, drug↔allergy, drug↔condition, ADR
  ├─ [8] RAG retrieval      filtered by surviving candidates
  ├─ [9] Diet + lifestyle   templates filtered per patient
  ├─ [10] LLM call (ONCE)   rephrase the finished assessment
  │        on failure → template fallback
  └─ [11] Persist + audit + render
```

**Steps 0, 1, 2, 4, 5, 6, 7 are deterministic Python. No LLM touches them.**
The model is called once, at the end, to rephrase a decision that has already
been made.

---

## Why it does not hallucinate

Architecturally, not by asking the model nicely:

1. The LLM **never selects a condition**. The rule engine does, before the
   model is invoked.
2. The LLM **never sees raw user text for reasoning**. It receives a completed
   structured assessment plus retrieved source passages.
3. Its output passes a **safety filter** that rejects percentages, probability
   language, doses, reassurance, stop-medicine advice, and asserted diagnoses.
   Rejected output falls back to templates.
4. If Ollama is down, slow, or returns something unusable, the deterministic
   fallback produces the full result anyway.

---

## What is in the knowledge base

No clinical rule is hardcoded in Python. Code reads `data/`.

| File | Contents |
|---|---|
| `symptoms.yaml` | 101 symptom codes, 720 aliases incl. Indian-English, plus an implication graph so "high fever" entails "fever" |
| `conditions/*.yaml` | 14 conditions with hallmark / supporting / expected / contradictory symptoms |
| `red_flags.yaml` | 15 escalation rules + a curated screening-question list |
| `drugs.yaml` | 55 medicines, Indian brand → generic, drug class, known side effects |
| `interactions.yaml` | 52 interaction rules + class-based allergy cross-reactivity |
| `diet_templates.yaml` | Per-condition diet and lifestyle, tagged for filtering |
| `treatment_expectations.yaml` | Whether a condition needs a prescribed course |
| `knowledge/*.md` | 60 source-cited passages → 120 RAG chunks |

**Every clinical row carries a `source_url`** pointing at MedlinePlus, WHO,
NIH, CDC or NHS. A test asserts this and fails the build if any row lacks one.

---

## Evidence bands, not percentages

The engine scores candidates internally, but the score **never leaves the
server** — a test enforces that. What the user sees is an ordinal band plus
the actual evidence:

| Band | Meaning |
|---|---|
| `most_consistent` | Clearly better supported than anything else |
| `possible` | Supported, but not established |
| `less_consistent` | Evidence argues against it |
| `insufficient_information` | Not enough to separate the candidates |

A symptom-overlap ratio is not a calibrated probability. Presenting one as a
diagnostic likelihood would be misleading, so the system does not.

---

## Medication safety

Four checks, all against the patient's **actual** medicines:

1. **drug ↔ drug** — interactions between what they already take
2. **drug ↔ allergy** — *by class, not by name*. A penicillin allergy flags
   Augmentin even though the names share no substring
3. **drug ↔ condition** — contraindications against their conditions
4. **adverse drug reaction** — could a current medicine be *causing* the
   reported symptom? Commonly missed, and the most useful check here

Combination products expand to their components, so Combiflam is checked as
both ibuprofen and paracetamol. An unrecognised medicine is reported, never
silently skipped.

**The system never suggests prescription medication and never gives a dose.**
It comments on safety, names the small OTC allowlist as general information
with a caveat, and says whether a condition normally needs a doctor-prescribed
course. That routing is health information, not a prescription.

---

## Testing

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q                    # 86 tests
.venv/Scripts/python.exe -m tools.eval_extraction        # NL accuracy
```

- `tests/test_acceptance.py` — the 10 spec acceptance cases
- `tests/test_invariants.py` — the 12 safety invariants, asserted against real
  API responses
- `tests/test_day1_foundation.py` — schema, auth, profile boundaries

The suite stubs the LLM out, so everything runs against the deterministic
fallback — the path that must work when Ollama is down.

### Natural-language extraction

`data/eval/nl_symptom_cases.yaml` holds 96 labelled real phrasings — negations,
Indian-English, durations, vague input, false-positive guards. The extractor
was tuned against it:

| Metric | Baseline | Final |
|---|---|---|
| Cases passing fully | 74.0% | **100%** |
| Symptom recall | 86.7% | **100%** |
| Negation recall | 89.5% | **100%** |
| Duration accuracy | 93.3% | **100%** |
| False positives | 0 | **0** |

This is the "training" loop for understanding ordinary English: label real
phrasings, measure, fix the gaps, re-measure. There is no neural model being
fitted — the extractor is deterministic rules — but the method is the same,
and unlike a fine-tune it is fully inspectable.

---

## Measured performance

On the target machine (RTX 4050 laptop, 6 GB VRAM, 16 GB RAM):

| | |
|---|---|
| Model | `qwen2.5:3b` via Ollama, **100% GPU** |
| VRAM | 2151 / 6141 MiB — leaves room for a browser and IDE |
| Throughput | ~57 tokens/sec warm |
| Cold load | ~46 s, avoided by `keep_alive=30m` |
| Full assessment | 8–24 s including retrieval and one LLM call |

---

## Design decisions worth defending

**SQLite, not Postgres.** The spec asks for a relational database with
structured tables; SQLite is both. The SQLAlchemy ORM means a Postgres
migration needs no code changes.

**NumPy, not a vector database.** At 120 chunks, cosine similarity over a small
matrix is five lines and runs in microseconds. A vector DB here would be
cargo-culting.

**A 3B model.** The LLM only phrases pre-decided output, so reliability and
speed matter far more than model quality.

**Rules, not deep learning.** No validated labelled dataset was available. An
unvalidated neural classifier on medical data produces confident wrong answers
with no audit trail. A transparent evidence engine is explainable, testable,
and safer at this scope.

---

## Deviations from the original spec

**WeasyPrint → fpdf2.** WeasyPrint requires GTK system libraries
(`libgobject`) that are not available on the target Windows machine; this was
confirmed by an import failure, not assumed. fpdf2 is pure Python and produces
the same artefact. This is the only stack change.

**Diet follows the leading candidate only.** Merging templates from three
candidates produced incoherent advice — a flu patient was told not to skip
antimalarial doses. Generic defaults still fill the gaps.

**Safety screening is capped at three questions.** Screening every red flag of
every candidate burned the whole budget before any discriminating question
ran. The screening list is curated and prioritised in `red_flags.yaml`;
extreme signs still escalate instantly if reported.

**Ten questions, not five.** The original spec said five, which was too thin
to narrow anything down. Ten is sized to the shape of a focused acute history
rather than to a round number, and it is rarely reached because the engine
stops as soon as one candidate is decisively clear.

---

## Limitations

Stated plainly, because they matter more than the feature list:

- **No clinical review.** No qualified clinician validated the rules. The
  system encodes published guidance and biases toward escalation, but it has
  not been checked by a doctor.
- **The base-rate priors are author judgement, not epidemiology.** Every one
  of the 14 conditions carries a prevalence tier — `very_common`, `common`,
  `uncommon`, `rare` — that shifts its starting score before any symptom is
  considered. The tiers reflect published prevalence patterns in Indian
  primary care, but they were assigned by the author and are not drawn from a
  cited dataset, so every condition YAML records
  `base_rate_source: author judgement` alongside a `base_rate_note` giving the
  reasoning. They are ordinal tiers, not probabilities, and nothing in the
  system converts them into one. An unsourced prior is a defensible
  limitation; an undisclosed one would not be, which is why they are declared
  in the data rather than buried in the scoring code.
- **The evidence weights are unfitted constants.** +3 for a hallmark and the
  0.5–2.0 specificity clamp are reasoned choices, not values learned from
  outcome data. The specificity weights themselves are derived from the
  knowledge base rather than hand-set. With only 14 conditions the
  inverse-frequency term is normalised by `ln(N)` rather than clamped, because
  the clamped form saturated — 50 of the 63 symptoms sat on the ceiling. After
  normalising, 28 do, and all of those are symptoms unique to a single
  condition. It would still discriminate more finely across a larger condition
  set.
- **Not a medical device**, not intended for clinical use, not validated
  against patient outcomes.
- **14 conditions only.** Anything outside that set will not be recognised.
- **Adults only.** Under-18, pregnancy and mental-health crisis are refused by
  design. Registration accepts ages 1-122 as a data-integrity range, but the
  scope guard refuses a consultation for anyone under 18 on every turn, with a
  paediatric referral. The clinical rule is enforced per consultation rather
  than once at signup, so editing a profile afterwards cannot bypass it.
- **English only.** Hinglish appears only as aliases in the symptom vocabulary.
- **No OCR.** Text-layer PDFs only; scanned documents get a clear message.
- **No encryption at rest.** The SQLite file is unencrypted. The JWT signing
  key is generated on first run and kept out of version control, but it sits
  in a plain file next to the database.
- **No DPDP compliance work.** Consent capture, retention policy and data
  export are out of scope.
- **Herbal and ayurvedic interactions** are not modelled.
- **Retrieval is limited** to the 120 curated chunks in `data/knowledge/`.

---

## Future work

Multi-profile accounts · multilingual input · OCR for scanned reports ·
lab-value extraction feeding the reasoning engine · chronic tracking over time
· ABDM/ABHA integration · a clinician review queue · a clinical vignette test
set validated by a doctor.
