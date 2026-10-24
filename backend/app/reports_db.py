"""SQLite persistence for citizen reports and safe photo storage."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.schemas import Report, ReportCreate

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    photo_filename TEXT,
    photo_content_type TEXT,
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
"""

# Accepted image types, identified by file signature rather than the client-supplied name/type.
IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def sniff_image_type(data: bytes) -> str | None:
    for content_type, signatures in IMAGE_SIGNATURES.items():
        if any(data.startswith(sig) for sig in signatures):
            if content_type == "image/webp" and data[8:12] != b"WEBP":
                continue
            return content_type
    return None


class ReportStore:
    def __init__(self, db_path: Path, upload_dir: Path) -> None:
        self.db_path = db_path
        self.upload_dir = upload_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create(self, report: ReportCreate, photo: bytes | None = None, photo_type: str | None = None) -> Report:
        report_id = uuid.uuid4().hex
        photo_filename = None
        if photo is not None and photo_type is not None:
            # Server-generated name only: user input never reaches the filesystem path.
            photo_filename = f"{report_id}.{EXTENSIONS[photo_type]}"
            (self.upload_dir / photo_filename).write_bytes(photo)
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        observed_at = report.observed_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reports (id, category, description, latitude, longitude, observed_at, created_at, "
                "photo_filename, photo_content_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report_id,
                    report.category.value,
                    report.description,
                    round(report.latitude, 6),
                    round(report.longitude, 6),
                    observed_at,
                    created_at,
                    photo_filename,
                    photo_type,
                ),
            )
        return self.get(report_id)  # type: ignore[return-value]

    def get(self, report_id: str) -> Report | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return _to_model(row) if row else None

    def photo(self, report_id: str) -> tuple[Path, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT photo_filename, photo_content_type FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        if not row or not row["photo_filename"]:
            return None
        path = (self.upload_dir / row["photo_filename"]).resolve()
        if path.parent != self.upload_dir.resolve() or not path.exists():
            return None
        return path, row["photo_content_type"]

    def list(self, page: int, page_size: int) -> tuple[list[Report], int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return [_to_model(r) for r in rows], total


def _to_model(row: sqlite3.Row) -> Report:
    return Report(
        id=row["id"],
        category=row["category"],
        description=row["description"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        observed_at=row["observed_at"],
        created_at=row["created_at"],
        has_photo=bool(row["photo_filename"]),
        verification_status=row["verification_status"],
    )
