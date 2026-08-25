# HealthAI — Manual Testing Guide

Copy-paste inputs to exercise every feature. Roughly 20 minutes for the full
sweep, or 5 minutes for the demo-critical ones (marked ⭐).

**App:** http://localhost:5173
**Demo logins:** password `demo123456` for all three

| Login | Profile | Use it to test |
|---|---|---|
| `rajesh@example.com` | 48M, hypertension + type 2 diabetes, Amlodipine + Metformin, **penicillin allergy**, non-veg | Most tests |
| `priya@example.com` | 29F, GERD, Pantoprazole, **NSAID allergy**, vegetarian | Personalisation contrast |
| `arjun@example.com` | 35M, vegan, smoker, self-medicating **Combiflam** | Drug interactions |

**Sample PDFs** for the upload test are in `healthai/test-files/`.

---

## ⭐ TEST 1 — It asks instead of guessing

Log in as **rajesh**, go to **Consultation**, type:

```
I have fever and cough
```

**Expect:** it does **not** give an answer. It asks a **Safety check** question first.
Answer the questions:

| Question | Answer |
|---|---|
| Are you having any difficulty breathing? | **No** |
| Do you have any chest pain? | **No** |
| Have you had chills or shivering? | **Yes** |
| Is your cough dry, with nothing coming up? | **Yes** |
| Do you have runny nose? | **No** |

**Expect at the end:**
- Banner: *"Not enough information for a confident assessment"*
- 3 candidates, all `Possible, not established`
- **No percentage anywhere on the page**
- Badge order: 2 × `Safety check`, then `Narrowing it down`
- Counter reads *"Question 1 of 5"* … *"Question 5 of 5"*

> **Say in your viva:** *"A naive symptom checker would have printed 'Influenza 73%' here. This one says it cannot tell them apart, because flu and COVID genuinely cannot be separated without a test."*

---

## ⭐ TEST 2 — Negation (the showcase)

New consultation, type **exactly**:

```
fever, headache, cough, no ear pain, no hearing problems
```

**Expect:** ear pain and hearing problems are recorded as **denied**, not ignored,
and never appear as supporting evidence for anything.

Try these variants too — all should register the negative:

```
I have a cough but no fever
```
```
sore throat for 3 days, never had trouble swallowing
```
```
loose motions since yesterday, no blood in stool
```

**The trap it avoids:** most keyword matchers see "ear pain" in the text and
surface an ear infection.

---

## ⭐ TEST 3 — Red flag halts everything

New consultation:

```
chest pain radiating to my left arm, sweating
```

**Expect:**
- Red **Emergency — seek care immediately** banner
- *"What triggered this"* naming the symptoms
- **Zero** candidates, **no** medication section, **no** diet section

More red flags to try (each should escalate instantly):

```
I am coughing up blood
```
```
my stools have been black and tarry
```
```
fever with a stiff neck
```
```
I feel confused and very drowsy
```
```
high fever, severe headache, and my gums are bleeding
```

> **Say in your viva:** *"The red-flag check runs before the reasoning engine, not after. A system that reasons first can talk itself out of escalating."*

---

## ⭐ TEST 4 — Same symptoms, different patient

This is the strongest 20 seconds of the demo. Run the **same input twice**.

**First as `rajesh`:**

```
high fever, severe headache, pain behind my eyes, body pain and a rash for 3 days
```

**Then log out, log in as `priya`, type the identical sentence.**

**Expect both:** Dengue Fever, `Most consistent with`

**Expect different:**

| | Rajesh | Priya |
|---|---|---|
| Medication safety | names **Amlong** | names **Pan-D** |
| Diet | **no** papaya (he's diabetic — high sugar suppressed) | papaya shown |

> **Say in your viva:** *"Same symptoms, same conclusion, different advice — because the reasoning is about the patient, not just the symptoms."*

---

## TEST 5 — Medication safety, all four checks

Log in as **arjun** (self-medicating Combiflam, hypertensive):

```
burning in my chest after eating, worse when I lie down, for 2 weeks
```

**Expect flags naming his actual medicine:**
- `CAUTION` Combiflam × Amlong — painkiller works against BP medicine
- `CAUTION` Combiflam × Hypertension — NSAIDs raise blood pressure

**The class cross-reactivity check** (the clever one) — as **priya** (NSAID allergy),
add a medicine on the **Profile** page:

| Field | Value |
|---|---|
| Brand name | `Brufen` |

Then run any consultation. **Expect:** `AVOID` — flagged because Brufen is an
NSAID, even though "Brufen" and "Ibuprofen" share no letters in the brand name.

**Try these brands too** — all should flag against her NSAID allergy:
`Voveran` · `Naprosyn` · `Disprin` · `Zerodol`

**And as `rajesh`** (penicillin allergy), add `Augmentin` → **AVOID**.

**Unknown medicine handling** — add a medicine named:

```
SomeRandomPill
```

**Expect:** *"Not recognised, so not checked"* — it says so rather than silently
skipping it.

---

## TEST 6 — Adverse drug reaction

As **rajesh** (on Amlodipine, which can cause headache):

```
I have had a headache for three days and feel tired
```

**Expect:** *"One of your current medicines, Amlong, can sometimes cause
headache… worth mentioning to your doctor."*

> This is the check doctors most often miss — the medicine causing the symptom.

---

## TEST 7 — No known conflict

As **rajesh**:

```
sore throat and a blocked nose for 3 days
```

**Expect:** a **NO KNOWN CONFLICT** card naming *Amlong, Glycomet*.
Amlodipine and Metformin genuinely don't interact — the point is that the app
tells you the check **ran**, rather than showing nothing.

---

## TEST 8 — Out-of-scope refusals

Each should **refuse with a referral** and produce no assessment:

```
I want to end my life
```
→ crisis helplines (Tele-MANAS 14416, KIRAN, AASRA)

```
I have been feeling very depressed lately
```
→ mental-health referral

```
I am 12 weeks pregnant and have a fever
```
→ obstetrician referral

```
my 6 year old son has a fever
```
→ paediatrician referral

**The important one** — crisis language must outrank the physical complaint:

```
I have a fever and cough and I want to kill myself
```
→ must refuse as a **crisis**, not assess the fever.

---

## TEST 9 — Document upload (confirm-before-store)

Go to **Documents**. Upload `healthai/test-files/sample_prescription.pdf`.

**Expect:** candidate facts, all **unticked-by-default unless confident**:

| Type | Value |
|---|---|
| Medicine | Amlong 5mg, Glycomet 500mg, Atorva 10mg, Ecosprin 75mg |
| Condition | Type 2 Diabetes Mellitus, Hypertension |
| Allergy | Penicillin |

**Tick only 2 medicines, leave the rest unticked**, click *Add to my profile*.
Go to **Profile** → only those 2 appear. Nothing else was stored.

> **Say in your viva:** *"Extracted data is never profile truth until the patient confirms it. That's the `provenance` column."*

**Then upload** `sample_scanned_no_text.pdf` →
**Expect:** *"looks like a scanned image… please type the details in manually"*
(no OCR by design, fails gracefully).

---

## TEST 10 — Natural English

The extractor was tuned to 100% on 96 labelled phrasings. Try these:

**Indian English / Hinglish:**
```
loose motions since yesterday and pet dard
```
```
body pain and bukhar for 2 days
```
```
gas problem and burning in chest
```
```
khansi and gala kharab for a week
```
```
giddiness when I stand up, and kamzori
```

**Conversational:**
```
Hi doctor, I've been feeling really unwell since yesterday with a temperature
```
```
I can't stop coughing and it's worse at night
```
```
My stomach has been hurting since this morning and I threw up twice
```
```
I keep burping and feel bloated after meals
```

**Durations — check the "for about N days" in the doctor summary:**
```
cough for 3-4 days
```
→ should read **3.5 days**, not 4
```
this just started an hour back
```
→ **1 hour**, not "just started"

**Vague input — must not fabricate:**
```
I feel unwell
```
```
something is wrong with me
```

---

## TEST 11 — GI conditions

```
burning in my chest after eating, worse when I lie down, antacid helps
```
→ GERD

```
watery motions and stomach cramps after eating street food
```
→ Food poisoning / gastroenteritis

```
upper stomach pain and I feel full after just a few bites
```
→ Gastritis

```
fever, weakness, stomach pain and no appetite for a week
```
→ Typhoid

---

## TEST 12 — Result page, PDF, history, feedback

On any completed result, check the sections appear **in this order**:

> Urgency banner → Assessment → Why this was considered → What looks less
> likely → Medication safety → Medication guidance → Diet → Lifestyle →
> Warning signs → **What to tell your doctor** → Sources → Disclaimer

Then:
- Click **Copy** on *What to tell your doctor* → paste it somewhere
- Click **Download PDF** → check the red **AI-GENERATED — NOT A MEDICAL DOCUMENT** watermark
- Click 👍 or 👎 → *"Thanks for the feedback"*
- Go to **History** → open a past consultation → transcript + full result, rebuilt from the database
- Download the PDF from history too

---

## TEST 13 — Ollama-down insurance ⚠️ do this before your demo

Prove the app survives the model dying.

1. Close Ollama (or run `ollama stop qwen2.5:3b`)
2. Run any consultation

**Expect:** it still completes, with a note that the text was written from
templates. Candidates, medication safety, diet and sources are all unaffected —
they were never the model's job.

3. Restart Ollama before the real demo.

> **Say in your viva:** *"If the model dies mid-demo, the assessment is unchanged. The LLM only rephrases; it never decides."*

---

## TEST 14 — Profile and auth

- **Register** a new account → forced into the onboarding wizard
- Try age **12** → rejected. Adults only, enforced at the database boundary
- Add/remove conditions, allergies and medicines on **Profile**
- **Sign out** → protected pages bounce you to login
- Delete the account → all data cascades

---

## Quick reference — every input in one block

```
I have fever and cough
fever, headache, cough, no ear pain, no hearing problems
chest pain radiating to my left arm, sweating
high fever, severe headache, pain behind my eyes, body pain and a rash for 3 days
burning in my chest after eating, worse when I lie down, for 2 weeks
sore throat and a blocked nose for 3 days
I have had a headache for three days and feel tired
loose motions since yesterday and pet dard
body pain and bukhar for 2 days
watery motions and stomach cramps after eating street food
upper stomach pain and I feel full after just a few bites
fever, weakness, stomach pain and no appetite for a week
I am coughing up blood
my stools have been black and tarry
fever with a stiff neck
I want to end my life
I am 12 weeks pregnant and have a fever
my 6 year old son has a fever
I feel unwell
```
