# HEALTHAI — COMPLETE MASTER PROMPT

You are the lead engineer building **HealthAI**, a personalised offline AI healthcare assistant. This document is the complete and final specification. Every decision here is settled. Do not propose alternatives, do not ask to confirm choices already made here, do not re-open resolved questions. Where you find genuine ambiguity, pick the simpler option, note the assumption in the README, and keep moving.

---

## 1. CONTEXT AND CONSTRAINTS

Final-year college major project. Solo developer. **7 days total.** Fully offline — no internet calls, no paid APIs, no cloud services. Hardware is a laptop with an RTX 4050 (6GB VRAM) and 16GB RAM, running alongside a browser and IDE.

Users are the developer and academic evaluators testing functionality — not real patients. This lowers the compliance bar but **not** the safety-design bar. The safety architecture is the intellectual content of the project.

A working, demonstrable system matters more than elegant code. Build vertical slices that actually run. Never leave the app in a non-starting state at the end of a session. Do not refactor working code for beauty. Do not add features not in this document.

### The claim being graded

> Most student symptom-checkers match keywords to diseases and print a fake percentage. HealthAI instead maintains a patient profile, asks targeted follow-up questions when evidence is insufficient, evaluates candidate conditions against structured evidence, checks medication safety against the patient's actual drugs and allergies, and refuses to output confident diagnoses it cannot support.

Every design choice must serve that claim. If a feature does not visibly demonstrate reasoning, personalisation, or safety, it is not worth building this week.

---

## 2. NON-NEGOTIABLE SAFETY INVARIANTS

These are correctness requirements, not style preferences. Violating any is a bug. If a later instruction conflicts with these, flag it rather than silently complying.

1. **No percentages, ever.** Never output a number readable as diagnostic probability. Ordinal bands only: `most_consistent`, `possible`, `less_consistent`, `insufficient_information`.
2. **Red flags short-circuit everything.** The red-flag check runs *before* symptom reasoning. If triggered: emit escalation, halt, return. No candidate conditions, no medication advice, no diet advice.
3. **The LLM never decides anything clinical.** It receives a completed structured assessment plus retrieved passages and rephrases them. It never selects a condition, never invents a fact, never sees raw user text for reasoning purposes.
4. **Exactly one LLM call per assessment.** Two absolute maximum. VRAM and demo latency depend on this.
5. **Every clinical rule carries a source.** Each condition definition, red flag, interaction and contraindication row must have `source_name` and `source_url` pointing at MedlinePlus / WHO / NIH / CDC / ICMR. No rule invented from the developer's judgement.
6. **Never reassure.** The system may say "less consistent with X" but must never say "this is nothing serious" or "you don't need a doctor." When uncertain, escalate.
7. **Never suggest prescription medication.** Comment only on the safety of medicines the patient already takes. A small OTC allowlist (paracetamol, ORS) may be mentioned as general information with a see-a-professional caveat. **Never give a dose for anything.**
8. **Never tell a patient to stop a prescribed medication.** Only "discuss with your doctor or pharmacist."
9. **Refuse out-of-scope categories outright:** under-18, pregnancy, mental-health crisis. A clear, kind refusal with a referral is the correct output. This is a feature, not a gap.
10. **Ollama-down must not break the demo.** Every LLM-generated surface needs a deterministic template fallback producing the full structured result in plainer language.
11. **Disclaimer on every assessment output and every PDF.**
12. **Audit-log every AI-generated output** with inputs, retrieved sources, and timestamp.

---

## 3. LOCKED STACK

```
Backend        FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0
Database       SQLite (healthai.db)
Frontend       React 18 + Vite + TypeScript + Tailwind + shadcn/ui
LLM            Ollama, qwen2.5:3b-instruct  (fallback llama3.2:3b)
Embeddings     sentence-transformers, BAAI/bge-small-en-v1.5, CPU
Vector search  NumPy matrix + cosine similarity, pickled to disk
PDF input      pdfplumber (text-layer PDFs only)
PDF output     WeasyPrint
Auth           JWT (python-jose), bcrypt (passlib)
Testing        pytest
```

**Never add:** Docker, Postgres, Celery, Redis, Chroma/Qdrant/FAISS, LangChain, LlamaIndex, microservices, Kubernetes, OCR engines, cloud services, streaming responses. Each costs hours and buys nothing this week.

**Rationale for the viva:** SQLite is relational and structured as required, and the SQLAlchemy ORM means a Postgres migration needs no code changes. NumPy beats a vector database at ~150 documents — cosine similarity over a small matrix is five lines and microseconds; a vector DB here would be cargo-culting. A 3B model suffices because the LLM only phrases pre-decided output, so reliability and speed matter more than model quality.

---

## 4. THE PIPELINE

```
User message
    |
    +-- [0] Scope guard      under-18 / pregnancy / mental-health -> refuse + refer, STOP
    +-- [1] Red-flag check   emergency pattern -> escalate, STOP
    +-- [2] Symptom extraction    vocabulary + aliases + negation + duration/severity
    +-- [3] Merge patient context   profile conditions, allergies, meds, age, prior consults
    +-- [4] Evidence engine     score all 14 candidates on structured evidence
    +-- [5] Sufficiency check
    |         insufficient --> [6] Follow-up engine --> return question, await answer
    |         sufficient   --> continue
    +-- [7] Medication safety   drug-drug, drug-allergy, drug-condition, ADR check
    +-- [8] RAG retrieval       filtered by surviving candidates
    +-- [9] Diet + lifestyle    templates filtered by allergies/diet/conditions
    +-- [10] LLM call (ONCE)    assessment + passages -> plain language
    |          on failure --> template fallback
    +-- [11] Persist + audit + render
```

Steps 0, 1, 2, 4, 5, 6, 7 are pure deterministic Python. No LLM. **This is the whole point of the project.**

---

## 5. PROJECT STRUCTURE

```
healthai/
├── CLAUDE.md
├── README.md
├── docs/architecture.md
├── backend/
│   ├── main.py, config.py, database.py, security.py, seed.py
│   ├── models/           SQLAlchemy, one file per domain
│   ├── schemas/          Pydantic
│   ├── api/              auth, profile, documents, consultation, history, reports
│   ├── core/
│   │   ├── scope_guard.py
│   │   ├── red_flags.py
│   │   ├── symptom_extraction.py
│   │   ├── negation.py
│   │   ├── evidence_engine.py
│   │   ├── sufficiency.py
│   │   ├── followup_engine.py
│   │   ├── medication_safety.py
│   │   ├── diet_lifestyle.py
│   │   └── patient_context.py
│   ├── rag/              embedder.py, index.py, retriever.py
│   ├── llm/              client.py, prompts.py, fallback.py
│   ├── documents/        extractor.py, medical_parser.py
│   ├── reports/pdf.py
│   ├── audit/logger.py
│   └── tests/
├── data/
│   ├── conditions/*.yaml       14 files
│   ├── symptoms.yaml
│   ├── red_flags.yaml
│   ├── drugs.yaml
│   ├── interactions.yaml
│   ├── diet_templates.yaml
│   └── knowledge/*.md          RAG corpus with front-matter metadata
└── frontend/src/{components,pages,api,lib}
```

**Rule: no clinical knowledge hardcoded in Python.** All of it lives in `data/*.yaml`. Code reads data. This makes the knowledge auditable and is a strong point in the report.

All LLM prompts live in `llm/prompts.py` and nowhere else.

---

## 6. DATABASE SCHEMA

Structured tables, not JSON blobs — except `audit_logs.payload_json` and `consultations.llm_raw_output`, which are legitimately blob-shaped.

```
users                 id, email, password_hash, created_at
patient_profiles      id, user_id FK, name, age, sex, height_cm, weight_kg,
                      blood_group, diet_type, smoker, alcohol, created_at, updated_at
patient_conditions    id, profile_id FK, condition_name, status(active|resolved),
                      onset_date, provenance, source_document_id, confirmed_at
patient_allergies     id, profile_id FK, allergen, allergen_class, reaction,
                      severity, provenance, confirmed_at
patient_medications   id, profile_id FK, brand_name, generic_name, dose, frequency,
                      route, reason, start_date, status(prescribed_taking|
                      prescribed_not_taking|self_medicating), provenance, confirmed_at
medical_documents     id, profile_id FK, filename, filepath, uploaded_at,
                      extraction_status, page_count
extracted_facts       id, document_id FK, fact_type, fact_value, confidence,
                      page_ref, review_status(pending|confirmed|rejected|edited)
consultations         id, profile_id FK, started_at, completed_at,
                      status(in_progress|complete|escalated|refused),
                      outcome_band, escalation_reason, llm_raw_output
messages              id, consultation_id FK, role(user|assistant), content, created_at
consultation_symptoms id, consultation_id FK, symptom_code, present(bool),
                      duration_hours, severity, onset, source(stated|answered)
candidate_evidence    id, consultation_id FK, condition_code, band,
                      supporting_json, missing_json, contradictory_json,
                      hallmark_present, context_factors_json
medication_safety_results id, consultation_id FK, subject_drug,
                      related_drug_or_condition, severity(none|caution|avoid),
                      reason, source_url
rag_retrievals        id, consultation_id FK, chunk_id, source_name, source_url, score
recommendations       id, consultation_id FK, category(diet_prefer|diet_avoid|hydration|
                      lifestyle|monitor|warning_sign), text
feedback              id, consultation_id FK, helpful(bool), created_at
pdf_reports           id, consultation_id FK, filepath, generated_at
audit_logs            id, consultation_id FK, event_type, payload_json, created_at
```

`provenance` enum wherever it appears: `user_entered | document_extracted_confirmed | ai_inferred`. **Never let AI-inferred data silently become profile truth.**

---

## 7. THE 14 CONDITIONS

Respiratory/infectious: `common_cold`, `influenza`, `covid19`, `acute_bronchitis`, `pneumonia`, `strep_pharyngitis`, `sinusitis`, `dengue`, `typhoid`, `malaria`
Gastrointestinal: `gerd`, `gastritis`, `gastroenteritis`, `food_poisoning`

Deliberately overlapping — several present with fever — which is exactly what makes the follow-up engine look intelligent.

### Condition YAML format

```yaml
code: dengue
display_name: Dengue Fever
sources:
  - name: WHO Dengue Fact Sheet
    url: https://www.who.int/news-room/fact-sheets/detail/dengue-and-severe-dengue
hallmark_symptoms: [high_fever, severe_headache, retro_orbital_pain, severe_body_ache]
supporting_symptoms: [nausea, vomiting, rash, joint_pain, fatigue]
expected_symptoms: [fever]              # absence weakens the candidate
contradictory_symptoms: [productive_cough, sore_throat]
typical_duration_hours: {min: 24, max: 168}
context_modifiers:
  - factor: monsoon_season
    effect: strengthen
red_flags: [severe_abdominal_pain, persistent_vomiting, bleeding_gums,
            black_stools, lethargy_restlessness]
```

### Evidence scoring — internal only, never displayed

```
hallmark present          +3 each
supporting present        +1 each
expected absent           -2 each
contradictory present     -3 each
context modifier          +/-1
duration mismatch         -1

Bands:
  nothing above threshold, or top two within 2 points  -> insufficient_information
  top >= 6 AND >= 3 clear of second                    -> most_consistent
  >= 3                                                  -> possible
  < 3                                                   -> less_consistent
```

Store the full breakdown in `candidate_evidence`. The result page shows *what* supported and contradicted each candidate — never the score.

---

## 8. SYMPTOM VOCABULARY AND EXTRACTION

`data/symptoms.yaml`: ~120 symptom codes with aliases, including Indian-English colloquialisms — `loose motions` and `motions` → diarrhoea, `body pain` → body_ache, `giddiness` → dizziness, `vomitings` → vomiting, `burning in chest` → heartburn, `gas` → bloating, `cold` → runny_nose.

**Extraction is rules, not LLM:** normalise → alias match → negation scope detection → duration/severity parsing.

**Negation:** detect `no | not | without | denies | haven't | don't have | never had` within a clause boundary (comma, `and`, `but`, sentence end) around the symptom. Store as `present=False`, not as absent — a stated negative is *evidence*, and acceptance test 3 depends on this.

**Duration:** `2 days`, `since yesterday`, `a week`, `few hours`, `3-4 days` → hours.

**Severity:** `mild | moderate | severe | unbearable | slight | very` → 1–4.

---

## 9. FOLLOW-UP QUESTION ENGINE

Select the unanswered question whose answer maximally separates the current top candidates — a symptom appearing in some candidates' hallmark/supporting lists and absent from others'.

- **Safety questions first.** Any unasked red-flag screening question relevant to reported symptoms precedes discriminating questions.
- Maximum **5** questions, then force an assessment with whatever evidence exists.
- One question at a time, with tappable options (`Yes` / `No` / `Not sure`, or scales). Never free text where options are possible.
- Skipped → mark unknown, continue, lower confidence.
- Never ask something already answered or already in the profile — except to confirm a medication is still being taken.

---

## 10. MEDICATION SAFETY

`data/drugs.yaml`: ~60 common Indian medicines, each with a `class` field and **brand → generic mapping**. Crocin/Dolo/Calpol → paracetamol. Combiflam → ibuprofen+paracetamol. Pan-D/Pantocid → pantoprazole. Augmentin → amoxicillin+clavulanate. Amlong → amlodipine. Glycomet → metformin. Brand names are what Indian users actually type.

`data/interactions.yaml`: ~80 curated rows, each `{subject, object, type(drug_drug|drug_condition|drug_allergy_class), severity(caution|avoid), reason, source_url}`.

**Allergy cross-reactivity by class, not name match.** Penicillin allergy must flag amoxicillin and ampicillin. NSAID allergy must flag ibuprofen, diclofenac, naproxen, aspirin.

**ADR check:** for each current medication, does its known-side-effect list intersect the reported symptoms? If so, surface: *"one of your current medicines can sometimes cause this — worth mentioning to your doctor."* This is the most clinically valuable feature in the build and demos extremely well.

Output tiers `no_known_conflict` / `caution` / `avoid`, each with a plain-language reason **naming the patient's actual medicine or condition**.

---

## 11. RAG

Corpus: ~150 markdown files in `data/knowledge/`, each with front matter:

```yaml
---
source_name: MedlinePlus
source_url: https://medlineplus.gov/...
condition: dengue
category: warning_signs
---
```

Categories: `description`, `symptoms`, `warning_signs`, `self_care`, `diet`, `when_to_seek_care`, `medication_info`.

Chunk on markdown headings, ~300 tokens, never split mid-list. Embed with bge-small. Store matrix + metadata in `data/index.pkl`.

**Retrieval is filtered by candidate condition codes — never run on raw user text.** Top 5 chunks. If nothing scores above threshold, use the fallback template rather than letting the LLM improvise.

Show source names and URLs on the result page. This is the strongest possible answer to "how do you know this is right?"

---

## 12. THE LLM CONTRACT

One call, temperature 0.3, max 600 tokens, 45s timeout. System prompt must instruct, in substance:

- You are rephrasing a completed medical assessment for a patient. You are not diagnosing.
- Use ONLY the facts in the structured assessment and the retrieved passages provided.
- Do not add conditions, symptoms, medications, doses, or claims not present in the input.
- Do not state or imply probability. Never use percentages.
- Do not reassure. Do not tell the patient they are fine.
- Do not recommend stopping any medication.
- Plain language, 8th-grade reading level, warm but not chirpy.
- If the input carries an escalation flag, output only the escalation message.

On timeout, exception, or malformed output → `fallback.py` template. Log every call to `audit_logs`.

---

## 13. DIET AND LIFESTYLE

`data/diet_templates.yaml` keyed by condition, sections: `prefer`, `avoid`, `hydration`, `lifestyle`, `monitor`, `warning_signs`.

Filter every item against the patient's `diet_type` (veg/non-veg/vegan/jain), allergies, and existing conditions. A hypertensive patient must not be told to drink salted lassi. A diabetic must not be told to drink fruit juice. A vegetarian must not be told to eat chicken soup.

Indian-specific content throughout: khichdi, curd, coconut water, ORS, jeera water, avoiding chilli/tamarind/fried food for GERD. Generic Western advice reads as lazy.

---

## 14. FRONTEND

Pages: Login/Register → Onboarding wizard → Dashboard → Consultation chat → Result → History → History detail → Profile → Documents.

Use shadcn/ui components as shipped. **Do not design custom components.** Clean typography, generous spacing, one accent colour, subtle shadows. Persistent disclaimer bar on consultation and result screens.

Result page section order:

> **Urgency banner → Assessment → Why this was considered → What's less likely → Medication safety → Diet → Lifestyle → Warning signs → What to tell your doctor → Sources → Disclaimer**

The **"What to tell your doctor"** block is a short copyable clinical summary — symptoms, duration, relevant history, current medications. It is the single most useful output in the product. Treat it as a headline feature.

---

## 15. RESOLVED DECISIONS — DO NOT ASK ABOUT THESE

| Question | Decision |
|---|---|
| Multi-profile accounts | No — one user, one profile |
| Multilingual / Hinglish | English only; Hinglish aliases in symptom vocabulary only |
| OCR / scanned docs / handwriting | No. Text-layer PDFs only; graceful message otherwise |
| Voice / image input | No |
| ABHA / ABDM integration | No |
| Paediatrics / pregnancy | Refuse with referral |
| Mental health | Detect → helpline message → stop |
| Chronic tracking over time | No |
| Vitals entry | Temperature only, optional |
| Prescription suggestions | Never |
| OTC dosing | Never |
| Herbal / ayurvedic interactions | Out of scope; note in limitations |
| Fine-tuning / model training | No — local inference only |
| Microservices | No — one app, modular packages |
| Docker / CI/CD | No |
| Streaming responses | No — request/response |
| Cross-session memory | Confirmed profile facts only. Past consultations are history, never auto-promoted to medical fact |
| Candidates shown | Max 3 |
| Feedback buttons | Yes — helpful/not helpful, one table |
| Data export | Basic account delete only |
| Rate limiting, MFA, pen testing | No |
| Encryption at rest | No — note in limitations |
| PDF password protection | No |
| Units / dates | Metric, DD/MM/YYYY |

---

## 16. BUILD ORDER AND CURRENT STATE

> **Update this section at the end of every session. It is the project's only memory across sessions.**

```
[x] Day 1  Verify Ollama FIRST. Scaffold, full DB schema, JWT auth, profile CRUD,
           onboarding wizard, seed script with one demo patient.
[ ] Day 2  symptoms.yaml, 14 condition YAMLs, red_flags.yaml, drugs.yaml,
           interactions.yaml, diet_templates.yaml. All with source URLs.
[ ] Day 3  Scope guard, red-flag check, symptom extraction + negation,
           evidence engine, sufficiency check.
[ ] Day 4  Follow-up engine, medication safety incl. allergy classes + ADR check.
[ ] Day 5  RAG corpus + index + retriever, Ollama client, prompts, fallback,
           diet/lifestyle generation.
[ ] Day 6  Result page, consultation history, PDF export, minimal document upload
           + confirmation flow, UI polish.
[ ] Day 7  10 acceptance tests, 3 seeded demo patients, demo rehearsal,
           README, architecture.md, limitations section.
```

**CURRENT STATE:** Day 1 complete. Backend and frontend both run and talk to each other.

Verified on the target machine, not estimated:
- Ollama 0.32.14, model `qwen2.5:3b` (Ollama's `:3b` tag is the instruct build)
- **100% GPU**, 2151 MiB / 6141 MiB VRAM — ~4 GB headroom for browser + IDE
- **~57 tokens/sec warm**, ~46 s cold load. `ollama_keep_alive=30m` set in `config.py`
  so a demo never pays the cold load.

Built and verified end-to-end:
- All 17 tables from §6 created; FK cascade enabled via SQLite `foreign_keys` pragma
- JWT auth (register / login / me / delete account), bcrypt, 72-byte cap enforced
- Profile CRUD with `provenance` on every fact; under-18 rejected at the schema boundary
- Onboarding wizard, 4 steps, shadcn/ui as shipped
- 3 demo patients seeded (idempotent), chosen so identical symptoms give different output
- Frontend typechecks and builds clean; login → dashboard → profile verified in a browser

**LAST SESSION:** Day 1 — scaffold, auth, profile, schema, onboarding, seed.
**NEXT ACTION:** Day 2 — knowledge encoding. `symptoms.yaml` first, then the 14
condition YAMLs, then red_flags/drugs/interactions/diet_templates. Every rule needs a
`source_url`.

Day 2 is unglamorous data entry and everything downstream depends on it. Do not let it be skipped toward more interesting work. If time runs short, drop from 14 conditions to 10 — **never reduce the depth of the evidence model**.

---

## 17. ACCEPTANCE TESTS

1. `"fever, cough, headache"` → asks follow-up questions, produces no diagnosis
2. `"fever, cough, headache, body aches, chills, dry cough, 2 days"` → respiratory/infectious candidates ranked sensibly
3. `"fever, headache, cough, no ear pain, no hearing problems"` → **negation handled; ear infection never surfaces**
4. Patient with penicillin allergy → amoxicillin flagged via class cross-reactivity
5. Patient on interacting medication → safety engine flags it with a reason
6. PDF upload → facts extracted → shown for confirmation → only then stored
7. Patient with hypertension → condition appears in reasoning and medication safety
8. Sparse input → follow-up questions, never a fabricated diagnosis
9. `"chest pain radiating to left arm, sweating"` → immediate escalation, pipeline halts
10. Diet guidance differs between two patients with identical symptoms, different profiles

Tests 3, 9 and 10 are the demo showcase. Screenshot all three for the report.

---

## 18. DEMO SCRIPT — rehearse exactly this on Day 7

1. Log in as a seeded patient: 48, hypertensive, on Amlodipine and Metformin, allergic to penicillin. (`rajesh@example.com` / `demo123456`)
2. Type *"I have fever and cough."*
3. System asks 4 targeted questions instead of guessing. Say aloud: *"the naive approach would have output a diagnosis here."*
4. Answer them → structured assessment, no percentages, evidence shown for and against.
5. Show the medication safety block naming their **actual** medicines and allergy.
6. Switch to a second seeded patient (`priya@example.com`), same symptoms, different profile → visibly different medication and diet output. **This is the strongest 20 seconds of the demo.**
7. Type *"chest pain radiating to my left arm, sweating"* → immediate escalation, pipeline halts, no diagnosis attempted.
8. Download the PDF.

---

## 19. WORKING STYLE

- Build vertical slices that run. Never leave the app broken overnight.
- Write the smallest thing that works, then move on.
- Do not refactor working code for elegance.
- Do not add features outside this document. If asked for one, note it as Future Work and say so.
- Seed demo data early so every screen has content.
- Commit at the end of each day, message naming the day.
- Ambiguity → simpler option + README note, not a question.

---

## APPENDIX — VIVA ANSWERS

**"Why no percentages?"** A symptom-overlap ratio isn't a calibrated probability, and presenting one as diagnostic likelihood misleads patients. We use ordinal evidence bands and show the underlying supporting and contradicting evidence instead.

**"How do you know your medical rules are correct?"** We don't assert them — every rule carries a source URL from MedlinePlus, WHO, NIH or ICMR. The system encodes published guidance rather than generating clinical claims. No clinical review was available, so it biases toward escalation and never reassures.

**"How do you prevent hallucination?"** Architecturally. The LLM never selects a condition and never sees raw user input for reasoning. It receives a completed structured assessment plus retrieved source passages and only rephrases them.

**"What if it's wrong?"** It's designed to fail toward "see a doctor." Red flags run before reasoning and halt the pipeline. It refuses under-18, pregnancy and mental-health cases entirely.

**"Why not deep learning?"** No validated labelled dataset was available. An unvalidated neural classifier on medical data produces confident wrong answers with no audit trail. A transparent evidence engine is explainable, testable and safer at this scope.

**"What's novel here?"** Three things: the information-sufficiency gate that refuses to assess on thin evidence; the medication-safety layer checking the patient's actual drugs and allergy classes including adverse-drug-reaction detection; and the "what to tell your doctor" output that turns the assessment into something clinically useful rather than a diagnosis substitute.

**"What are the limitations?"** No clinical review. No OCR. English only. No encryption at rest. No DPDP compliance work. Scoped to 14 conditions. Adults only. Not validated against patient outcomes. Not a medical device and not intended for clinical use.
