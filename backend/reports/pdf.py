"""PDF report generation.

Built with fpdf2 rather than WeasyPrint: WeasyPrint needs GTK system libraries
(libgobject) which are not available on the target Windows machine. fpdf2 is
pure Python. Noted as a stack deviation in the README.

Invariant 11: the disclaimer appears on every PDF, and the watermark makes
clear this is not a medical document.
"""
import re
from pathlib import Path

from fpdf import FPDF

from config import REPORT_DIR

WATERMARK = "AI-GENERATED - NOT A MEDICAL DOCUMENT"

DISCLAIMER = (
    "HealthAI is an educational project, not a medical device. It does not "
    "diagnose, prescribe, or replace professional medical care. This report was "
    "produced by an automated system with no clinical review. Always consult a "
    "qualified doctor or pharmacist about your health."
)

BAND_LABEL = {
    "most_consistent": "Most consistent with",
    "possible": "Possible, not established",
    "less_consistent": "Less consistent",
    "insufficient_information": "Not enough information",
}

# fpdf2's built-in fonts are latin-1 only. Map the typographic characters that
# actually show up rather than dropping them.
_REPLACEMENTS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", " ": " ",
    "•": "-", "→": "->", "°": " deg",
}


def _clean(text: str) -> str:
    out = str(text or "")
    for bad, good in _REPLACEMENTS.items():
        out = out.replace(bad, good)
    out = re.sub(r"\s+\n", "\n", out)
    return out.encode("latin-1", "replace").decode("latin-1")


class Report(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(150, 40, 40)
        self.cell(0, 6, WATERMARK, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(220, 220, 220)
        self.line(15, 22, 195, 22)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 4, f"HealthAI - page {self.page_no()}", align="C")

    # --- building blocks ---------------------------------------------------

    def title_block(self, title: str, subtitle: str = "") -> None:
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 8, _clean(title))
        if subtitle:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(110, 110, 110)
            self.multi_cell(0, 5, _clean(subtitle))
        self.ln(3)

    def section(self, heading: str) -> None:
        if self.get_y() > 250:
            self.add_page()
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(15, 90, 85)
        self.multi_cell(0, 6, _clean(heading))
        self.set_text_color(35, 35, 35)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(35, 35, 35)
        self.multi_cell(0, 5, _clean(text))
        self.ln(1)

    def bullets(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(35, 35, 35)
        for item in items:
            if self.get_y() > 265:
                self.add_page()
            self.multi_cell(0, 5, _clean(f"  -  {item}"))
        self.ln(1)

    def callout(self, text: str, rgb: tuple[int, int, int]) -> None:
        self.set_fill_color(*rgb)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, _clean(text), fill=True)
        self.ln(2)


def _add_candidates(pdf: Report, turn: dict) -> None:
    candidates = turn.get("candidates") or []
    if not candidates:
        return
    pdf.section("What was considered")
    for candidate in candidates:
        pdf.set_font("Helvetica", "B", 10)
        label = BAND_LABEL.get(candidate.get("band", ""), "Considered")
        pdf.multi_cell(0, 5, _clean(f"{candidate['display_name']} - {label}"))
        evidence = candidate.get("evidence") or {}
        if evidence.get("supporting"):
            pdf.body("Supported by: " + ", ".join(evidence["supporting"]))
        if evidence.get("contradictory"):
            pdf.body("Argues against: " + ", ".join(evidence["contradictory"]))
        if evidence.get("missing"):
            pdf.body("Expected but not reported: " + ", ".join(evidence["missing"]))
        pdf.ln(1)


def _add_medication(pdf: Report, turn: dict) -> None:
    safety = turn.get("medication_safety") or {}
    guidance = turn.get("medication_guidance") or {}

    findings = safety.get("findings") or []
    if findings:
        pdf.section("Medication safety")
        for finding in findings:
            pdf.body(f"[{finding['severity'].upper()}] {finding['reason']}")

    if guidance.get("treatment"):
        pdf.section("What this usually needs")
        for note in guidance["treatment"]:
            pdf.body(f"{note['condition_display']}: {note['summary']}")

    if guidance.get("general_info"):
        pdf.section("General medicine information")
        pdf.body(
            "This is general information only. It is not a recommendation for "
            "you, and no doses are given. Confirm anything here with a doctor "
            "or pharmacist."
        )
        for item in guidance["general_info"]:
            pdf.body(f"{item['display']} - used for {item['used_for']}. {item['caveat']}")


def _add_diet(pdf: Report, turn: dict) -> None:
    diet = turn.get("diet") or {}
    sections = [
        ("Foods to prefer", diet.get("prefer")),
        ("Foods to avoid", diet.get("avoid")),
        ("Fluids", diet.get("hydration")),
        ("Lifestyle", diet.get("lifestyle")),
        ("What to keep an eye on", diet.get("monitor")),
        ("Warning signs", diet.get("warning_signs")),
    ]
    for heading, items in sections:
        if items:
            pdf.section(heading)
            pdf.bullets(items)


def build_report(turn: dict, patient_name: str, generated_at: str) -> bytes:
    """Render a consultation into PDF bytes."""
    pdf = Report(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    pdf.title_block(
        "Health Assessment Summary",
        f"{patient_name}   |   Generated {generated_at}",
    )

    escalation = turn.get("escalation")
    refusal = turn.get("refusal")

    if escalation:
        pdf.callout(
            f"URGENT: {escalation['urgency'].upper()} - SEEK CARE NOW",
            (255, 228, 228),
        )
        pdf.body(escalation["reason"])
        pdf.body(escalation["action"])
        if escalation.get("triggered_by"):
            pdf.body("Triggered by: " + ", ".join(escalation["triggered_by"]))
    elif refusal:
        pdf.callout("OUTSIDE THE SCOPE OF THIS TOOL", (255, 244, 220))
        pdf.body(refusal["message"])
        pdf.body(refusal["referral"])
        if refusal.get("resources"):
            pdf.bullets(refusal["resources"])
    else:
        band = turn.get("band") or "insufficient_information"
        pdf.callout(BAND_LABEL.get(band, "Assessment").upper(), (226, 242, 240))

        if turn.get("narrative"):
            pdf.section("Assessment")
            pdf.body(turn["narrative"])

        symptoms = turn.get("symptoms") or []
        present = [s["display"] for s in symptoms if s.get("present")]
        denied = [s["display"] for s in symptoms if not s.get("present")]
        if present or denied:
            pdf.section("Symptoms recorded")
            if present:
                pdf.body("Reported: " + ", ".join(present))
            if denied:
                pdf.body("Specifically denied: " + ", ".join(denied))

        _add_candidates(pdf, turn)
        _add_medication(pdf, turn)
        _add_diet(pdf, turn)

        if turn.get("doctor_summary"):
            pdf.section("What to tell your doctor")
            pdf.body(turn["doctor_summary"])

    sources = turn.get("sources") or []
    if sources:
        pdf.section("Sources")
        pdf.set_font("Helvetica", "", 8)
        for source in sources:
            pdf.multi_cell(
                0, 4, _clean(f"  -  {source.get('name', '')}  {source.get('url', '')}")
            )

    pdf.ln(4)
    pdf.section("Disclaimer")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 4, _clean(DISCLAIMER))

    return bytes(pdf.output())


def write_report(turn: dict, patient_name: str, generated_at: str, consultation_id: int) -> Path:
    data = build_report(turn, patient_name, generated_at)
    path = REPORT_DIR / f"healthai_consultation_{consultation_id}.pdf"
    path.write_bytes(data)
    return path
