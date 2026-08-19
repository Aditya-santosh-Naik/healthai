# HealthAI — Architecture

One process, modular packages. Not microservices: the module boundaries are real, the
deployment is one FastAPI app.

---

## The pipeline

Every consultation turn runs this sequence. Steps 0, 1, 2, 4, 5, 6 and 7 are pure
deterministic Python with no LLM involvement. **That is the whole point of the project.**

```
User message
    |
    +--> [0] Scope guard      under-18 / pregnancy / mental-health -> refuse + refer, STOP
    |
    +--> [1] Red-flag check   emergency pattern -> escalate, STOP
    |
    +--> [2] Symptom extraction    vocabulary + aliases + negation + duration/severity
    |
    +--> [3] Merge patient context   conditions, allergies, meds, age, prior consults
    |
    +--> [4] Evidence engine     score all 14 candidates on structured evidence
    |
    +--> [5] Sufficiency check
    |          insufficient --> [6] Follow-up engine --> return question, await answer
    |          sufficient   --> continue
    |
    +--> [7] Medication safety   drug-drug, drug-allergy, drug-condition, ADR
    |
    +--> [8] RAG retrieval       filtered by surviving candidates
    |
    +--> [9] Diet + lifestyle    templates filtered by allergies / diet / conditions
    |
    +--> [10] LLM call (ONCE)    assessment + passages -> plain language
    |           on failure --> deterministic template fallback
    |
    +--> [11] Persist + audit + render
```

### Why the order matters

The red-flag check runs *before* symptom reasoning, not after. A pipeline that reasons
first and checks safety second can talk itself out of escalating. This one cannot: if a
red flag fires, the function returns before any candidate condition exists.

---

## Where the intelligence lives

| Layer | Decides | Implementation |
|---|---|---|
| Scope guard | Whether to engage at all | Rules |
| Red flags | Whether to escalate | Rules, runs first |
| Extraction | What the patient said | Vocabulary + aliases + negation |
| Evidence engine | Which conditions fit | Deterministic scoring |
| Sufficiency | Whether it knows enough | Threshold on evidence separation |
| Follow-up | What to ask next | Maximal candidate separation |
| Medication safety | What is unsafe | Curated tables, class-aware |
| RAG | What sources say | Cosine similarity, candidate-filtered |
| **LLM** | **Nothing.** Only wording | One call, strict prompt |

The LLM receives a completed structured assessment plus retrieved passages. It never
selects a condition, never invents a fact, and never sees raw user text for reasoning
purposes. If it is unavailable, `llm/fallback.py` produces the same structured result
in plainer language and the demo continues.

---

## Data model

17 tables, structured rather than JSON blobs. The two exceptions —
`audit_logs.payload_json` and `consultations.llm_raw_output` — are legitimately
blob-shaped.

The evidence breakdown per candidate is persisted in `candidate_evidence`:
supporting, missing and contradictory symptoms, whether a hallmark was present, and the
internal score. **The score is stored for audit and testing and is never rendered.** The
result page shows *what* supported and contradicted each candidate, never a number.

### Provenance

`provenance` appears on every profile fact: `user_entered`,
`document_extracted_confirmed`, or `ai_inferred`. Facts extracted from an uploaded PDF
land in `extracted_facts` with `review_status = pending` and reach the profile only
after the user confirms them. **AI-inferred data never silently becomes profile truth.**

---

## Stack, and why

| Choice | Reason |
|---|---|
| SQLite | Relational and structured as required. The SQLAlchemy ORM means a Postgres migration needs no code changes. |
| NumPy + cosine similarity | ~150 documents. Cosine over a small matrix is five lines and microseconds. A vector database here would be cargo-culting. |
| qwen2.5:3b | The LLM only phrases pre-decided output, so reliability and speed matter more than model quality. Verified at 100% GPU, ~57 tok/s. |
| One process | The module boundaries are what matter. Splitting into services buys nothing at this scale. |

---

## Safety invariants

These are correctness requirements, not style preferences. Violating any is a bug.

1. **No percentages, ever.** Ordinal bands only: `most_consistent`, `possible`,
   `less_consistent`, `insufficient_information`.
2. **Red flags short-circuit everything**, before symptom reasoning.
3. **The LLM never decides anything clinical.**
4. **Exactly one LLM call per assessment.**
5. **Every clinical rule carries a source** (`source_name` + `source_url`).
6. **Never reassure.** When uncertain, escalate.
7. **Never suggest prescription medication.** Never give a dose for anything.
8. **Never tell a patient to stop a prescribed medication.**
9. **Refuse under-18, pregnancy, mental-health crisis** — a kind refusal with a referral
   is the correct output, and is a feature.
10. **Ollama-down must not break the demo.**
11. **Disclaimer on every assessment output and every PDF.**
12. **Audit-log every AI-generated output.**
