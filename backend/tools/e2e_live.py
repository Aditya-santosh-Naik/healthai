"""End-to-end against the LIVE server. Follows spec section 18's demo script."""
import json, sys, time
import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=120.0)
FAIL = []

def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond: FAIL.append(name)

def login(email):
    r = c.post("/api/auth/login", json={"email": email, "password": "demo123456"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

print("\n=== 1. health ===")
h = c.get("/api/health").json()
check("health ok", h["status"] == "ok")
check("ollama up", h["ollama_available"])
check("rag index built", h["rag_index_built"])

print("\n=== 2. login as the three demo patients ===")
tok = {}
for e in ["rajesh@example.com", "priya@example.com", "arjun@example.com"]:
    try:
        tok[e] = login(e); check(f"login {e}", True)
    except Exception as ex:
        check(f"login {e}", False, str(ex)[:80])
if not tok: sys.exit("cannot continue without a login")

raj = tok["rajesh@example.com"]

print("\n=== 3. profile ===")
p = c.get("/api/profile", headers=raj).json()
check("profile loads", p.get("name") is not None)
check("has conditions", len(p.get("conditions", [])) > 0)
check("has medications", len(p.get("medications", [])) > 0)
check("has allergies", len(p.get("allergies", [])) > 0)
check("provenance recorded", all(x["provenance"] for x in p["conditions"]))

print("\n=== 4. sparse input asks questions, names nothing (spec test 1) ===")
t = c.post("/api/consultation/start", json={"text": "I have fever and cough"}, headers=raj).json()
check("asks a question", t["outcome"] == "needs_question", t["outcome"])
check("names no condition", not t.get("candidates"))
check("question has options", len(t.get("question", {}).get("options", [])) >= 2)
check("disclaimer present", bool(t.get("disclaimer")))

print("\n=== 5. answer through to a verdict ===")
replies = {"shortness_of_breath":"No","chest_pain":"No","severe_abdominal_pain":"No",
           "chills":"Yes","body_ache":"Yes","dry_cough":"Yes","fatigue":"Yes",
           "runny_nose":"No","sweating":"No"}
asked = 0
while t["outcome"] == "needs_question" and asked < 12:
    code = t["question"]["symptom_code"]
    t = c.post(f"/api/consultation/{t['consultation_id']}/message",
               json={"text": replies.get(code, "No")}, headers=raj).json() if False else \
        c.post(f"/api/consultation/{t['consultation_id']}/answer",
               json={"symptom_code": code, "answer": replies.get(code, "No")}, headers=raj).json()
    asked += 1
check("reached completion", t["outcome"] == "complete", t["outcome"])
check("asked several questions", asked >= 3, f"asked {asked}")
check("has a band", bool(t.get("band")))
check("has candidates", bool(t.get("candidates")))
check("has narrative", bool(t.get("narrative")))
check("has doctor summary", bool(t.get("doctor_summary")))
check("has medication safety", t.get("medication_safety") is not None)
check("has medication guidance", t.get("medication_guidance") is not None)
check("has diet", t.get("diet") is not None)
check("has sources", bool(t.get("sources")))

body = json.dumps(t).lower()
print("\n=== 6. safety invariants on a real response ===")
import re
check("no percentages", not re.search(r"\d+\s?%", body))
check("no 'probability'", "probability" not in body)
check("names the patient's own medicine", "amlong" in body or "glycomet" in body)
check("no dosing", not re.search(r"\b\d+\s?(mg|ml|tablets?)\b", body))

CID = t["consultation_id"]

print("\n=== 7. history round-trip ===")
hist = c.get("/api/history", headers=raj).json()
check("history lists it", any(x["id"] == CID for x in hist))
d = c.get(f"/api/history/{CID}", headers=raj).json()
check("detail loads", d["consultation_id"] == CID)
check("guidance survives", d.get("medication_guidance") is not None)
check("doctor summary survives", bool(d.get("doctor_summary")))
check("candidates survive", bool(d.get("candidates")))
check("diet survives", d.get("diet") is not None)

print("\n=== 8. PDF export ===")
r = c.get(f"/api/reports/{CID}.pdf", headers=raj)
check("pdf 200", r.status_code == 200, str(r.status_code))
check("is a pdf", r.content[:5] == b"%PDF-", str(r.content[:12]))
check("pdf non-trivial", len(r.content) > 3000, f"{len(r.content)} bytes")

print("\n=== 9. escalation halts the pipeline (spec test 9) ===")
e = c.post("/api/consultation/start",
           json={"text": "chest pain radiating to my left arm, sweating"}, headers=raj).json()
check("escalated", e["outcome"] == "escalated", e["outcome"])
check("no candidates named", not e.get("candidates"))
check("no diet advice", not e.get("diet"))
check("escalation has action", bool(e.get("escalation", {}).get("action")))
check("escalation cites a source", bool(e.get("escalation", {}).get("source_url")))

print("\n=== 10. NEW red flags fire end to end ===")
for text, label in [("high fever and i am very confused", "sepsis"),
                    ("rash all over and i cannot breathe", "anaphylaxis"),
                    ("i had a seizure", "seizure"),
                    ("black tarry stools", "gi bleed")]:
    r = c.post("/api/consultation/start", json={"text": text}, headers=raj).json()
    check(f"{label} escalates", r["outcome"] == "escalated", r["outcome"])

print("\n=== 11. same symptoms, different patient -> different output (spec test 10) ===")
def quick(tokhdr, text):
    return c.post("/api/consultation/start", json={"text": text}, headers=tokhdr).json()

def complete(tokhdr, text):
    """Drive to an outcome. Medication safety only exists at step 7, so a
    sparse opening leaves it None for everyone -- comparing those compares
    nothing."""
    r = quick(tokhdr, text)
    n = 0
    while r["outcome"] == "needs_question" and n < 12:
        r = c.post(f"/api/consultation/{r['consultation_id']}/answer",
                   json={"symptom_code": r["question"]["symptom_code"], "answer": "No"},
                   headers=tokhdr).json()
        n += 1
    return r

a = complete(raj, "loose motions, vomiting and stomach cramps since yesterday")
# Vegan vs non-veg. Rajesh and Priya are non-veg and veg, and nothing in
# the gastroenteritis template excludes either -- comparing them proves
# nothing. Spec test 10 needs profiles that actually differ.
b = complete(tok["arjun@example.com"], "loose motions, vomiting and stomach cramps since yesterday")
check("both completed", a["outcome"] == "complete" and b["outcome"] == "complete",
      f"{a['outcome']} / {b['outcome']}")
sa, sb = json.dumps(a.get("medication_safety")), json.dumps(b.get("medication_safety"))
check("medication safety differs by patient", sa != sb)
da, db = json.dumps(a.get("diet")), json.dumps(b.get("diet"))
check("diet differs by patient (spec test 10)", da != db,
      f"non-veg vs vegan produced identical diet advice")
check("vegan is not told to eat curd", "curd" not in db.lower())
check("non-veg patient still gets the dairy item", "curd" in da.lower())

print("\n=== 12. out-of-scope refusals ===")
for text, cat in [("i am 14 years old and have fever", None),
                  ("i think i am pregnant and have nausea", "pregnancy"),
                  ("i want to end my life", "mental_health_crisis")]:
    r = quick(raj, text)
    ok = r["outcome"] == "refused"
    check(f"refuses: {text[:34]}", ok, r["outcome"])
    if ok: check("  refusal has referral", bool(r["refusal"].get("referral")))

print("\n=== 13. auth is enforced ===")
check("no token -> 401/403", c.get("/api/history").status_code in (401, 403))
check("bad token -> 401/403", c.get("/api/history", headers={"Authorization":"Bearer nope"}).status_code in (401,403))

print("\n" + "="*60)
print(f"RESULT: {'ALL PASS' if not FAIL else str(len(FAIL)) + ' FAILURES'}")
for f in FAIL: print("   FAILED:", f)
