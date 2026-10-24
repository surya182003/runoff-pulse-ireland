"""Read-only access to acquired datasets in backend/data, cached until the file changes."""

from __future__ import annotations

import csv
import json
import threading
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.config import get_settings


class DatasetMissing(FileNotFoundError):
    """Raised when an expected dataset has not been acquired yet."""


class DataStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or get_settings().data_dir
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def path(self, name: str) -> Path:
        return self.data_dir / name

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def _cached(self, name: str, loader: Callable[[Path], Any]) -> Any:
        path = self.path(name)
        if not path.exists():
            raise DatasetMissing(name)
        mtime = path.stat().st_mtime
        with self._lock:
            hit = self._cache.get(name)
            if hit and hit[0] == mtime:
                return hit[1]
        value = loader(path)
        with self._lock:
            self._cache[name] = (mtime, value)
        return value

    def json(self, name: str) -> Any:
        return self._cached(name, lambda p: json.loads(p.read_text(encoding="utf-8")))

    def json_or(self, name: str, default: Any) -> Any:
        try:
            return self.json(name)
        except DatasetMissing:
            return default

    def geojson(self, name: str) -> dict:
        return self.json(name)

    def features_or_empty(self, name: str) -> list[dict]:
        return self.json_or(name, {"features": []}).get("features", [])

    def manifest(self) -> dict:
        return self.json_or("manifest.json", {"datasets": {}})

    def bathing_measurements(self) -> pd.DataFrame:
        def load(path: Path) -> pd.DataFrame:
            df = pd.read_csv(path, dtype={"beach_id": str, "qualifier": str, "value_raw": str}, keep_default_na=False)
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df["result_date"] = pd.to_datetime(df["result_date"], errors="coerce").dt.date
            return df

        return self._cached("bathing_measurements.csv", load)

    def rainfall_daily(self) -> pd.DataFrame:
        def load(path: Path) -> pd.DataFrame:
            df = pd.read_csv(path, dtype={"station_id": str, "rain_indicator": str}, keep_default_na=False)
            df["rain_mm"] = pd.to_numeric(df["rain_mm"], errors="coerce")
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df

        return self._cached("rainfall_daily.csv", load)

    def rainfall_hourly_archive(self) -> pd.DataFrame:
        return self._cached("rainfall_hourly.csv", _load_hourly)

    def rainfall_recent(self) -> pd.DataFrame:
        try:
            return self._cached("rainfall_recent_hourly.csv", _load_hourly)
        except DatasetMissing:
            return _empty_hourly()

    def opw_series(self, station_number: str) -> list[dict]:
        name = f"opw_series/{station_number}_0001.json"
        return self.json_or(name, {"values": []}).get("values", [])


def _empty_hourly() -> pd.DataFrame:
    return pd.DataFrame(columns=["datetime_utc", "rain_mm", "source"]).astype({"rain_mm": float})


def _load_hourly(path: Path) -> pd.DataFrame:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return _empty_hourly()
    df = pd.DataFrame(rows)
    df["rain_mm"] = pd.to_numeric(df["rain_mm"], errors="coerce")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df[["datetime_utc", "rain_mm", "source"]]


_store: DataStore | None = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store


def set_store(store: DataStore | None) -> None:
    """Override the store (used by tests)."""
    global _store
    _store = store
