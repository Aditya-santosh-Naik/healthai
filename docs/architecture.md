# HealthAI — Architecture

Companion to the README. This document explains *why* the system is shaped the
way it is, for the project report and the viva.

---

## 1. The central design decision

> **Rules decide. The LLM speaks.**

Every clinical decision — which conditions are candidates, whether the evidence
is sufficient, what question to ask next, whether a medicine is unsafe, whether
to escalate — is made by deterministic Python reading source-cited YAML.

The language model is called **once**, at the very end, and is given a
*completed* assessment to rephrase. It cannot select a condition because it is
never asked to. It cannot invent a symptom because it never sees the raw user
message.

This is the answer to "how do you prevent hallucination?" — prevented
structurally, not by prompt-begging.

---

## 2. Module map

One process, sixteen well-separated modules. Not microservices: at this scale
that would add operational cost and buy nothing.

```
                         ┌──────────────────────┐
                         │  React 18 + Vite     │
                         │  (Tailwind, shadcn)  │
                         └──────────┬───────────┘
                                    │  /api/*  (Vite proxy)
                         ┌──────────▼───────────┐
                         │      FastAPI         │
                         │  api/ auth profile   │
                         │  consultation history│
                         │  documents reports   │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      core/pipeline.py          │
                    │  orchestrates steps 0 → 10     │
                    └───┬────────┬────────┬──────┬───┘
                        │        │        │      │
        ┌───────────────▼──┐  ┌──▼─────┐ ┌▼────┐ ┌▼──────────┐
        │ deterministic    │  │  rag/  │ │ llm/│ │ audit/    │
        │ core/            │  │        │ │     │ │ logger    │
        │  scope_guard     │  │embedder│ │client│└───────────┘
        │  red_flags       │  │index   │ │prompts│
        │  symptom_extract │  │retriever│ │fallback│
        │  negation        │  └───┬────┘ └──┬───┘
        │  evidence_engine │      │         │
        │  sufficiency     │   index.pkl  Ollama
        │  followup_engine │   (NumPy)    qwen2.5:3b
        │  medication_safety│
        │  medication_guide│
        │  diet_lifestyle  │
        │  patient_context │
        └────────┬─────────┘
                 │  reads, never hardcodes
        ┌────────▼─────────┐        ┌──────────────┐
        │   data/*.yaml    │        │  SQLite      │
        │   knowledge/*.md │        │  17 tables   │
        └──────────────────┘        └──────────────┘
```

**Nothing below the pipeline calls anything above it.** `core/` has no
knowledge of HTTP; `api/` has no clinical logic. That separation is what makes
the engine testable without a database or a server.

---

## 3. The pipeline, step by step

| Step | Module | Deterministic? | What it does |
|---|---|---|---|
| 0 | `scope_guard` | ✅ | Refuse under-18 / pregnancy / mental-health crisis |
| 1 | `red_flags` | ✅ | Escalate and **halt** on any emergency pattern |
| 2 | `symptom_extraction` + `negation` | ✅ | Text → symptom codes, with stated negatives |
| 3 | `patient_context` | ✅ | Merge confirmed profile facts |
| 4 | `evidence_engine` | ✅ | Score all 14 candidates |
| 5 | `sufficiency` | ✅ | Decide: assess, or ask? |
| 6 | `followup_engine` | ✅ | Pick the most separating question |
| 7 | `medication_safety` | ✅ | Four safety checks |
| 8 | `rag/retriever` | ✅ | Retrieve passages for surviving candidates |
| 9 | `diet_lifestyle` | ✅ | Filtered per-patient guidance |
| 10 | `llm/client` | ❌ | Rephrase — the only non-deterministic step |
| 11 | `api/consultation` | ✅ | Persist, audit, render |

### Why the order matters

**Step 1 runs before step 4 deliberately.** A system that reasons first and
checks safety afterwards can talk itself out of escalating — it finds a benign
explanation and stops looking. Running red flags first, on positively-reported
symptoms only, makes escalation unconditional. When it fires, the function
returns before a candidate list exists.

**Step 5 is the novel part.** Most symptom-checkers always produce an answer.
This one has a gate that can refuse, and refusing is a normal outcome rather
than an error.

---

## 4. Symptom extraction

Rules and a controlled vocabulary, not an LLM. Rules are more reliable for
negation and are fully inspectable.

```
raw text
  → normalise            lowercase, expand contractions, strip punctuation
  → strip stopwords      applied to BOTH text and aliases so they line up
  → split into clauses   on , ; . and but also however
  → alias match          longest-first, non-overlapping
  → negation scope       forward scope from cue to clause end
  → duration / severity  explicit values beat vague relative phrases
  → implication closure  "high fever" also asserts "fever"
```

Two details that took real work:

**Both sides are canonicalised the same way.** The alias `blood in phlegm` will
never match `no blood in the phlegm` unless the stopword `the` is stripped from
the text *and* from the alias table. Contracted aliases (`cant smell`) also get
an expanded twin (`can not smell`), because negation detection needs the word
`not` to be visible.

**A stated negative is evidence, not absence.** `no ear pain` is stored as
`present=False`, which is different from a symptom simply not being mentioned.
The evidence engine penalises a denied hallmark. Acceptance test 3 depends on
this.

---

## 5. The evidence engine

```
score = base_rate_prior
      + Σ( specificity_weight(symptom) × evidence_value(symptom) )
      + context_modifiers
      + duration_mismatch
```

**The prior** is how common the condition is before any symptom is examined:
`very_common` +4, `common` +2, `uncommon` 0, `rare` −3. Declared per condition
in YAML, author judgement, disclosed in the README limitations.

**The specificity weight** is `0.5 + 1.5 × ln(N / n) / ln(N)`, where `n` is
how many of the `N` conditions list that symptom. Derived from the knowledge
base, never hand-set. It is what stops `fever` — which half the conditions
claim — counting the same as `retro_orbital_pain`, which exactly one does.

Dividing by `ln(N)` rather than clamping matters at this scale. The clamped
form, `clamp(0.5 + ln(N/n), 0.5, 2.0)`, saturated: with only 14 conditions it
hit the ceiling for any symptom in three or fewer, which was **50 of the 63
symptoms in use**. Four fifths of the vocabulary shared one weight, so the
weighting was close to a uniform ×2 rescale. Normalising maps the range onto
`[0.5, 2.0]` by construction — `n=1` lands exactly on the maximum, `n=N`
exactly on the minimum — and ceiling occupancy fell to 28, all of them symptoms
genuinely unique to one condition. Tests assert both that the ceiling is not
crowded and that the weight is monotone in `n`.

**The evidence values** are unchanged in magnitude — hallmark +3, supporting
+1, expected absent −2, contradictory −3, context ±1, duration mismatch −1 —
but each is multiplied by that symptom's specificity weight.

Bands compare the leader to the runner-up, not the absolute score alone:

```
top < 6, or (top − second) ≤ 4     →  insufficient_information
top ≥ 11.5 and (top − second) ≥ 5.5 →  most_consistent
top ≥ 6                             →  possible
otherwise                           →  less_consistent
```

These cutoffs were measured, not guessed: across all 96 eval cases the top
score per case runs p25 2.39 / p50 4.94 / p85 11.38, and the lead over the
runner-up p50 1.25 / p80 5.80. They were re-derived when the specificity
formula changed — a scoring change that leaves the thresholds alone silently
moves every band. The `possible` threshold is additionally
anchored — it must exceed the largest prior (4.0), or a cold would qualify on
prevalence alone with no evidence at all. A test asserts that relationship so
the two cannot drift apart.

The margin rule is what makes the system honest. Flu and COVID-19 genuinely
cannot be separated on symptoms alone, so the engine lands on
`insufficient_information` and says so rather than picking one.

The score is persisted in `candidate_evidence` for audit and testing, and a
test asserts it never appears in an API response.

---

## 6. The follow-up engine

Two-phase selection:

1. **Safety first, capped at three.** Screening questions come from a curated
   priority list in `red_flags.yaml`. Extreme signs (blue lips, seizures) are
   deliberately excluded — a patient with blue lips is not typing into a web
   form, and asking burns the question budget. They still escalate instantly if
   reported.

2. **Then maximum separation.** For each unanswered symptom, compute how much
   the top candidates' scores would diverge on a yes/no. Value peaks when
   roughly half the pool moves — a question everyone gains from, or nobody
   does, teaches nothing.

Questions are scored by **expected information across both answers**, not by
the best case. Scoring only the "yes" branch made the engine ask about symptoms
that are merely contradictory for the runner-up, where answering "no" moves
nothing -- so half those questions were wasted.

Hard cap of ten questions, sized to a focused acute history rather than to a
round number, with an early stop once one candidate is decisively clear. A
clinician does not keep working through a checklist after the picture has
settled.

"Decisive" means the same thing in the gate as in the verdict: both are
derived from `MOST_CONSISTENT_MIN_SCORE` / `MIN_LEAD` rather than being set
independently. They were independent once, and the gate stopped as soon as the
candidates merely *separated* — ending "I have fever and cough" after four
questions, three of them red-flag screens, on a merely `possible` answer, with
six questions of budget unspent and body ache, fatigue and runny nose never
asked. Giving up on becoming confident is the same failure as over-claiming,
just quieter. The consultation now continues until it can name a
most-consistent candidate, the question budget runs out, or no unanswered
symptom would move the ranking.

`Not sure` records presence as **unknown**, not as a denial. It contributes no
evidence, but it is remembered -- returning nothing left the symptom
unanswered and the same question was selected forever.

---

## 7. Medication safety

The layer with the most clinical value and the most legal sensitivity.

```
patient's medicines ──► brand → generic resolution
                              │   ("Dolo 650" → paracetamol)
                              ▼
                        component expansion
                              │   (Combiflam → ibuprofen + paracetamol)
                              ▼
        ┌─────────────┬───────┴────────┬──────────────┐
        ▼             ▼                ▼              ▼
   drug × drug   drug × allergy   drug × condition   ADR
                 (BY CLASS)                     (side effect ∩
                                                 reported symptom)
```

**Cross-reactivity is by class.** A name-match system fails here: "Penicillin"
and "Augmentin" share no substring, yet one contraindicates the other. Classes
are declared in `interactions.yaml`, with `flags_classes` (avoid) separate from
`also_caution_classes` (caution), so the penicillin→cephalosporin relationship
is graded rather than binary.

**Component expansion was a real bug.** Combiflam resolves to the generic
`ibuprofen+paracetamol`, which matched no interaction rule keyed on
`ibuprofen`. Acceptance tests 5 and 7 silently passed with zero findings until
components were expanded.

**The ADR check** intersects each medicine's known side effects with the
reported symptoms. If a patient on Amlodipine reports headache, that is
surfaced — not as a claim, but as something worth mentioning to their doctor.

---

## 8. What the system will not do

Encoded as invariants and asserted by `tests/test_invariants.py`:

| Invariant | Enforced by |
|---|---|
| No percentages or probability language | Output filter + regex sweep over real responses |
| Red flags halt everything | `pipeline.run` returns before candidates exist |
| The LLM decides nothing clinical | It receives a finished assessment; prompt asserted in tests |
| Exactly one LLM call | Call counter in tests |
| Every rule has a source | Test iterates the whole knowledge base |
| Never reassure | Regex sweep over responses |
| Never prescribe, never dose | Regex sweep; OTC items must carry a caveat |
| Never say to stop a medicine | Allowed only inside "do not stop" |
| Refuse out-of-scope | Four categories tested, crisis outranks physical complaints |
| Fallback when Ollama is down | The entire suite runs with the LLM stubbed out |
| Disclaimer everywhere | Asserted on every outcome and in the PDF |
| Audit every AI output | Asserted against the `audit_logs` table |

---

## 9. Data provenance

The `provenance` enum appears on every profile fact:

```
user_entered                    typed by the patient
document_extracted_confirmed    read from a PDF AND confirmed by the patient
ai_inferred                     never written to the profile
```

Extracted facts land in `extracted_facts` with `review_status=pending` and are
copied to the profile only on explicit confirmation. There is no other code
path into the profile. This is why acceptance test 6 checks that rejected
facts leave the profile unchanged.

---

## 10. Retrieval

Filtered retrieval, never open-ended:

```
surviving candidates ──► query built from condition DISPLAY NAMES
                              │        (never raw user text)
                              ▼
                    mask index to those conditions + general
                              ▼
                    cosine similarity (NumPy, 120 × 384)
                              ▼
                    top 5 above threshold 0.30
                              ▼
                    passages + source URLs → LLM and result page
```

If nothing clears the threshold, the LLM is told so explicitly and the template
fallback is used rather than letting the model improvise.

The index is a NumPy `.npz` archive: the matrix as binary, the chunk metadata
as a JSON string inside it, loaded with `allow_pickle=False`.

It was originally a pickle. `pickle.load` executes arbitrary code contained in
the file it reads, so a pickled index is a remote-code-execution primitive the
moment that file can be replaced. `npz` + JSON carries data only and cannot
execute anything, and `allow_pickle=False` makes that structural rather than a
matter of trust.

---

## 10a. Where the time goes

Profiled per stage rather than reasoned about, because the answer was not the
one the code shape suggests. One consultation, deterministic path only:

| Stage | Before | After |
|---|---|---|
| RAG retrieval | 41.60 ms | **0.03 ms** |
| Symptom extraction | 4.99 ms | **1.03 ms** |
| Scope guard | 0.13 ms | 0.13 ms |
| Evidence engine | 0.09 ms | 0.10 ms |
| Medication safety | 0.08 ms | 0.08 ms |
| Diet / lifestyle | 0.07 ms | 0.02 ms |
| Follow-up, red flags, sufficiency | <0.02 ms each | unchanged |
| **Total** | **46.99 ms** | **1.42 ms** |

Two changes, both aimed at the measured hot spots:

**The query embedding is memoised.** 35.9 of retrieval's 41.6 ms was a single
`embed_query` call -- a transformer forward pass -- against 0.016 ms for the
mask rebuild and 0.006 ms for the similarity matmul. Caching is sound here
specifically because retrieval is filtered by candidate CODES and never runs on
user text: the query is condition display names plus a fixed suffix, bounded at
roughly 2,400 permutations, so it cannot leak between patients or be poisoned
by input.

**Alias matching is bucketed by first word.** `_match_clause` tested all 789
aliases against every clause, ~3,900 regex scans per message. An alias cannot
match a clause that does not contain its first word, so the filter is exact
rather than heuristic. O(clauses x aliases x length) becomes
O(clauses x matching-aliases x length).

What was deliberately NOT optimised, because the profile said not to: the
`np.argsort` over 120 chunks (0.012 ms) and the mask rebuild (0.016 ms). Both
have textbook improvements available -- `argpartition` is O(n) against
`argsort`'s O(n log n) -- and at this scale both would be theatre.

The honest caveat: **none of this is felt by a user.** End to end the request is
dominated by the single Ollama call at 8-24 s, which is unchanged. At the API
level the deterministic pipeline is now 1.4 ms of a 21 ms request, the rest
being database writes and serialisation. This work matters for the
Ollama-down fallback path and for throughput under load, not for perceived
latency, and presenting a 33x speedup as a user-visible win would be
misleading.

---

## 11. Known weaknesses

Honest ones, worth raising before an examiner does:

- **The knowledge base is hand-curated and unreviewed.** It encodes published
  guidance, but no clinician checked the encoding.
- **Evidence weights are judgement, not data.** +3 for a hallmark is a
  reasonable choice, not a fitted parameter. With labelled outcome data these
  could be learned; without it, transparent constants beat false precision.
- **The 14 conditions are a closed world.** Anything outside is invisible, and
  the system cannot know what it does not model. It mitigates by escalating on
  red flags and refusing on thin evidence.
- **Retrieval quality is bounded by the corpus** — 120 chunks is enough to
  ground phrasing, not enough to answer arbitrary questions.
- **The extraction eval set is author-written.** 100% on it means the extractor
  handles the phrasings anticipated, not all phrasings.
