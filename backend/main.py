"""HealthAI backend entrypoint.

One process, modular packages. No microservices (spec §15).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(auth.router)
app.include_router(profile.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/disclaimer", tags=["meta"])
def disclaimer() -> dict[str, str]:
    return {"disclaimer": DISCLAIMER}
