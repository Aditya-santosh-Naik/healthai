"""PDF text extraction.

Text-layer PDFs only. No OCR (spec section 15): a scanned document gets a
clear message rather than a silent failure or a bad guess.
"""
from dataclasses import dataclass
from pathlib import Path

MIN_CHARS_PER_PAGE = 40


@dataclass
class ExtractionOutcome:
    status: str  # complete | no_text_layer | failed
    text: str = ""
    page_count: int = 0
    pages: list[str] | None = None
    message: str = ""


def extract_text(path: Path) -> ExtractionOutcome:
    try:
        import pdfplumber
    except ImportError:
        return ExtractionOutcome(status="failed", message="pdfplumber is not installed")

    try:
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception as exc:  # noqa: BLE001 - a bad upload must not 500
        return ExtractionOutcome(
            status="failed",
            message=f"This file could not be read as a PDF ({type(exc).__name__}).",
        )

    text = "\n".join(pages).strip()
    page_count = len(pages)

    if page_count and len(text) < MIN_CHARS_PER_PAGE * page_count / 2:
        return ExtractionOutcome(
            status="no_text_layer",
            text=text,
            page_count=page_count,
            pages=pages,
            message=(
                "This looks like a scanned image rather than a text PDF. "
                "Automatic reading is not available, so please type the details "
                "in manually."
            ),
        )

    return ExtractionOutcome(
        status="complete", text=text, page_count=page_count, pages=pages
    )
