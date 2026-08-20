"""Ollama client. One call per assessment (invariant 4).

Everything about this module assumes the LLM is optional. If Ollama is down,
slow, or returns something unusable, the caller falls back to templates and the
demo continues (invariant 10).
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import settings

# Phrases that would violate an invariant if they reached the patient. If the
# model produces one, the output is rejected and the template is used instead.
BANNED_PATTERNS = [
    r"\b\d{1,3}\s?%",                      # any percentage
    r"\b\d{1,3}\s?percent\b",
    r"\bnothing (?:to worry|serious)\b",
    r"\byou (?:are|will be) fine\b",
    r"\bno need to (?:see|worry|consult)\b",
    r"\bdon'?t need (?:to see )?a doctor\b",
    r"\bstop taking\b",
    r"\bdiscontinue\b",
    r"\b\d+\s?mg\b",                       # any dose
    r"\b\d+\s?ml\b",
    r"\btake \d+\b",
    # Probability language. Invariant 1 bans implying likelihood, not just
    # printing a number.
    r"\bmost likely\b",
    r"\bprobabl[ey]\b",
    r"\bchances are\b",
    r"\blikelihood\b",
    r"\bodds (?:are|of)\b",
    # Self-attributed diagnostic claims. "Your doctor can confirm the
    # diagnosis" is fine and is deliberately NOT matched here; the system
    # asserting a diagnosis of its own is not.
    r"\b(?:the|your|this|my)\s+diagnosis\s+is\b",
    r"\bdiagnosed\s+with\b",
    r"\bI\s+diagnose\b",
    r"\byou\s+have\s+(?:been\s+)?diagnos",
]

_BANNED = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]


@dataclass
class LLMResult:
    text: str
    ok: bool
    model: str
    error: str | None = None
    duration_seconds: float = 0.0
    eval_tokens: int = 0

    @property
    def used_fallback(self) -> bool:
        return not self.ok


def check_output(text: str) -> str | None:
    """Return the reason the output is unusable, or None if it passes."""
    if not text or len(text.strip()) < 40:
        return "output too short"
    for pattern in _BANNED:
        match = pattern.search(text)
        if match:
            return f"banned phrase: {match.group(0)!r}"
    return None


def is_available(timeout: float = 2.0) -> bool:
    """Cheap liveness probe, so the UI can warn before a long wait."""
    try:
        with urllib.request.urlopen(
            f"{settings.ollama_url}/api/tags", timeout=timeout
        ) as response:
            return response.status == 200
    except Exception:
        return False


def generate(system_prompt: str, user_prompt: str) -> LLMResult:
    """One non-streaming completion. Never raises."""
    import time

    payload = {
        "model": settings.ollama_model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "keep_alive": settings.ollama_keep_alive,
        "options": {
            "temperature": settings.ollama_temperature,
            "num_predict": settings.ollama_max_tokens,
        },
    }
    request = urllib.request.Request(
        f"{settings.ollama_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    try:
        with urllib.request.urlopen(
            request, timeout=settings.ollama_timeout_seconds
        ) as response:
            body = json.loads(response.read())
    except urllib.error.URLError as exc:
        return LLMResult(
            text="", ok=False, model=settings.ollama_model,
            error=f"ollama unreachable: {exc.reason}",
            duration_seconds=time.time() - started,
        )
    except TimeoutError:
        return LLMResult(
            text="", ok=False, model=settings.ollama_model,
            error=f"timed out after {settings.ollama_timeout_seconds}s",
            duration_seconds=time.time() - started,
        )
    except Exception as exc:  # noqa: BLE001 - the demo must not die here
        return LLMResult(
            text="", ok=False, model=settings.ollama_model,
            error=f"{type(exc).__name__}: {exc}",
            duration_seconds=time.time() - started,
        )

    text = (body.get("response") or "").strip()
    problem = check_output(text)
    if problem:
        return LLMResult(
            text=text, ok=False, model=settings.ollama_model,
            error=f"rejected, {problem}",
            duration_seconds=time.time() - started,
            eval_tokens=body.get("eval_count", 0) or 0,
        )

    return LLMResult(
        text=text,
        ok=True,
        model=settings.ollama_model,
        duration_seconds=time.time() - started,
        eval_tokens=body.get("eval_count", 0) or 0,
    )
