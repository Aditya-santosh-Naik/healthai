"""Application configuration. Everything is local; no cloud, no external calls."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = BACKEND_DIR / "uploads"
REPORT_DIR = BACKEND_DIR / "reports_out"


class Settings(BaseSettings):
    app_name: str = "HealthAI"

    # Auth. Dev-only secret; noted as a limitation in the README.
    secret_key: str = "healthai-dev-secret-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'healthai.db').as_posix()}"

    # Ollama. Verified Day 1: qwen2.5:3b, 100% GPU, ~57 tok/s warm.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_fallback_model: str = "llama3.2:3b"
    ollama_timeout_seconds: int = 45
    ollama_temperature: float = 0.3
    ollama_max_tokens: int = 600
    # Keeps the model resident so a demo never pays the ~46s cold load.
    ollama_keep_alive: str = "30m"

    embedding_model: str = "BAAI/bge-small-en-v1.5"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_prefix="HEALTHAI_", env_file=".env")


settings = Settings()

for _d in (UPLOAD_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
