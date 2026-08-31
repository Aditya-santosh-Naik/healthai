"""HealthAI backend entrypoint.

One process, modular packages. No microservices (spec §15).
"""
import sys
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import auth, profile
from config import settings
from database import init_db

DISCLAIMER = (
    "HealthAI is an educational project, not a medical device. It does not "
    "diagnose, prescribe, or replace professional medical care. Always consult "
    "a qualified doctor or pharmacist about your health."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Offline, personalised healthcare assistant. Rules decide; the LLM only rephrases.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Return nothing internal, and log nothing clinical.

    Two separate obligations that are easy to conflate:

    * The RESPONSE must not carry internals. A stack trace tells an attacker
      the framework, file layout and library versions, and an exception
      message can quote the input that caused it -- which here is the
      patient's own description of their symptoms.
    * The LOG must not carry the patient's text either. Server logs are the
      least protected place health data can land: they are shipped, tailed and
      pasted into issue trackers.

    So the traceback FRAMES are logged (file, line, function -- enough to find
    the bug) while the exception's message and arguments are deliberately
    dropped, because that is where user text ends up. The reference id ties a
    user's report to a log line without either side carrying the content.
    """
    reference = uuid.uuid4().hex[:12]
    frames = traceback.format_tb(exc.__traceback__)
    print(
        f"[error {reference}] {type(exc).__name__} "
        f"at {request.method} {request.url.path}\n" + "".join(frames),
        file=sys.stderr,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Something went wrong on our side. Nothing about your health "
                f"information was affected. Reference: {reference}"
            )
        },
    )


app.include_router(auth.router)
app.include_router(profile.router)

# Imported here rather than at module top: these routers import DISCLAIMER
# from this module, so importing them earlier would be circular.
from api import consultation, documents, history, reports  # noqa: E402

app.include_router(consultation.router)
app.include_router(history.router)
app.include_router(documents.router)
app.include_router(reports.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, object]:
    """Liveness, plus whether the optional pieces are actually up.

    The UI uses ollama_available to warn before a long wait; the app works
    either way because every LLM surface has a template fallback.
    """
    from llm.client import is_available
    from rag import retriever

    return {
        "status": "ok",
        "app": settings.app_name,
        "ollama_available": is_available(),
        "rag_index_built": retriever.available(),
    }


@app.get("/api/disclaimer", tags=["meta"])
def disclaimer() -> dict[str, str]:
    return {"disclaimer": DISCLAIMER}
