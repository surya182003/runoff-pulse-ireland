"""Application configuration, read from environment variables (.env supported)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("RUNOFFPULSE_DATA_DIR", str(BACKEND_DIR / "data")))
    )
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("RUNOFFPULSE_DB_PATH", str(BACKEND_DIR / "var" / "runoffpulse.sqlite3"))
        )
    )
    upload_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("RUNOFFPULSE_UPLOAD_DIR", str(BACKEND_DIR / "var" / "uploads"))
        )
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "RUNOFFPULSE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
    )
    # Live upstream calls (OPW water levels, Met Éireann latest observations).
    # Set to "false" for offline demos and tests: only on-disk datasets are used.
    live_enabled: bool = field(
        default_factory=lambda: os.getenv("RUNOFFPULSE_LIVE_ENABLED", "true").lower() == "true"
    )
    live_cache_seconds: int = field(
        default_factory=lambda: int(os.getenv("RUNOFFPULSE_LIVE_CACHE_SECONDS", "900"))
    )
    http_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("RUNOFFPULSE_HTTP_TIMEOUT", "20"))
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("RUNOFFPULSE_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    )


def get_settings() -> Settings:
    return Settings()
