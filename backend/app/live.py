"""Cached access to near-real-time upstream feeds, with on-disk snapshots as fallback.

Upstream calls happen here (never in the frontend) and are cached for
RUNOFFPULSE_LIVE_CACHE_SECONDS so page loads don't hammer public services. Every response
says whether it came from the live feed or the snapshot and when that data was retrieved.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import httpx
import pandas as pd

from app.config import get_settings
from app.data_store import get_store
from app.ingest.common import USER_AGENT, utc_now_iso
from app.ingest.met import LATEST_URLS, parse_latest_observations
from app.ingest.opw import OPW_LATEST, load_screened_catchments, parse_latest

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _cached(key: str, fetch: Callable[[], Any]) -> Any:
    settings = get_settings()
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < settings.live_cache_seconds:
            return hit[1]
    value = fetch()
    with _lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _client() -> httpx.Client:
    return httpx.Client(timeout=get_settings().http_timeout_seconds, headers={"User-Agent": USER_AGENT})


def opw_latest() -> dict[str, Any]:
    """Latest OPW readings for the study area: {features, mode, retrieved_at, error}."""
    store = get_store()
    snapshot = store.json_or("opw_latest.geojson", None)

    def from_snapshot(error: str | None) -> dict[str, Any]:
        if snapshot is None:
            return {"features": [], "mode": "UNAVAILABLE", "retrieved_at": None, "error": error}
        return {
            "features": snapshot["features"],
            "mode": "SNAPSHOT",
            "retrieved_at": snapshot.get("retrieved_at"),
            "error": error,
        }

    if not get_settings().live_enabled:
        return from_snapshot(None)

    def fetch() -> dict[str, Any]:
        try:
            catchment = store.json("catchment.geojson")["features"][0]["geometry"]
        except Exception:
            catchment = None
        screened = load_screened_catchments(store.data_dir)
        try:
            with _client() as client:
                response = client.get(OPW_LATEST)
                response.raise_for_status()
                features = parse_latest(response.json(), catchment, screened)
            return {"features": features, "mode": "LIVE", "retrieved_at": utc_now_iso(), "error": None}
        except Exception as error:
            return from_snapshot(f"Live OPW feed unavailable ({type(error).__name__}); using snapshot")

    return _cached("opw_latest", fetch)


def met_latest_hourly() -> dict[str, Any]:
    """Met Éireann latest hourly reports for Cork (yesterday + today) as a DataFrame."""
    empty = {"frame": pd.DataFrame(columns=["datetime_utc", "rain_mm", "source"]), "mode": "UNAVAILABLE",
             "retrieved_at": None, "error": None}
    if not get_settings().live_enabled:
        return {**empty, "mode": "DISABLED"}

    def fetch() -> dict[str, Any]:
        rows: list[dict] = []
        try:
            with _client() as client:
                for url in LATEST_URLS.values():
                    response = client.get(url)
                    response.raise_for_status()
                    rows.extend(parse_latest_observations(response.json()))
        except Exception as error:
            return {**empty, "error": f"Live Met Éireann feed unavailable ({type(error).__name__})"}
        frame = pd.DataFrame(rows)
        if frame.empty:
            return {**empty, "mode": "LIVE", "retrieved_at": utc_now_iso()}
        frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)
        frame["rain_mm"] = pd.to_numeric(frame["rain_mm"], errors="coerce")
        return {"frame": frame[["datetime_utc", "rain_mm", "source"]], "mode": "LIVE",
                "retrieved_at": utc_now_iso(), "error": None}

    return _cached("met_latest", fetch)
