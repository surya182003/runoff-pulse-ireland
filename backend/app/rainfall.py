"""Rainfall series assembly and window statistics for Cork Airport (Met Éireann station 3904)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.data_store import DataStore, DatasetMissing
from app.ingest.met import STATION_ID, STATION_LAT, STATION_LON, STATION_NAME

# When the same hour appears in several sources, the quality-controlled archive wins.
SOURCE_PRIORITY = {"met_eireann_hourly_archive": 0, "met_eireann_latest_reports": 1, "met_eireann_live": 1}

STATION = {"id": STATION_ID, "name": STATION_NAME, "lon": STATION_LON, "lat": STATION_LAT}


def combined_hourly(store: DataStore, live_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    frames = []
    try:
        frames.append(store.rainfall_hourly_archive())
    except DatasetMissing:
        pass
    frames.append(store.rainfall_recent())
    if live_frame is not None and not live_frame.empty:
        frames.append(live_frame)
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["datetime_utc", "rain_mm", "source"])
    df = pd.concat(frames, ignore_index=True)
    df["priority"] = df["source"].map(SOURCE_PRIORITY).fillna(9)
    df = df.sort_values(["datetime_utc", "priority"]).drop_duplicates("datetime_utc", keep="first")
    return df.drop(columns="priority").reset_index(drop=True)


@dataclass
class WindowStats:
    hours: int
    total_mm: float | None
    hours_with_data: int
    coverage: float
    max_hourly_mm: float | None
    start: datetime
    end: datetime

    def as_dict(self) -> dict:
        return {
            "window_hours": self.hours,
            "total_mm": None if self.total_mm is None else round(self.total_mm, 1),
            "hours_with_data": self.hours_with_data,
            "coverage": round(self.coverage, 2),
            "max_hourly_mm": None if self.max_hourly_mm is None else round(self.max_hourly_mm, 1),
            "start_utc": self.start.isoformat().replace("+00:00", "Z"),
            "end_utc": self.end.isoformat().replace("+00:00", "Z"),
        }


def window_stats(hourly: pd.DataFrame, end: datetime, hours: int) -> WindowStats:
    """Rainfall in the window (end - hours, end]. Missing hours are not treated as dry."""
    start = end - timedelta(hours=hours)
    if hourly.empty:
        return WindowStats(hours, None, 0, 0.0, None, start, end)
    mask = (hourly["datetime_utc"] > start) & (hourly["datetime_utc"] <= end)
    values = hourly.loc[mask, "rain_mm"].dropna()
    count = int(values.size)
    if count == 0:
        return WindowStats(hours, None, 0, 0.0, None, start, end)
    return WindowStats(hours, float(values.sum()), count, min(1.0, count / hours), float(values.max()), start, end)


def latest_observation(hourly: pd.DataFrame, at_or_before: datetime) -> pd.Series | None:
    if hourly.empty:
        return None
    valid = hourly[(hourly["datetime_utc"] <= at_or_before) & hourly["rain_mm"].notna()]
    if valid.empty:
        return None
    return valid.iloc[-1]


def two_day_climatology(store: DataStore) -> np.ndarray:
    """Sorted array of all consecutive two-day rainfall totals in the daily archive."""
    try:
        daily = store.rainfall_daily()
    except DatasetMissing:
        return np.array([])
    series = daily.set_index("date")["rain_mm"].astype(float)
    full_index = pd.date_range(min(series.index), max(series.index), freq="D").date
    series = series.reindex(full_index)
    totals = series.rolling(2, min_periods=2).sum().dropna().to_numpy()
    return np.sort(totals)


def percentile_of(sorted_values: np.ndarray, value: float) -> float | None:
    if sorted_values.size == 0:
        return None
    return float(np.searchsorted(sorted_values, value, side="right") / sorted_values.size)


def daily_series(
    store: DataStore, hourly: pd.DataFrame, start: date | None, end: date | None
) -> list[dict]:
    """Daily totals: archive daily values, then (after the archive ends) totals of the hourly
    reports for days with complete 24-hour coverage. Incomplete days are returned with
    total null and their coverage, never as zero."""
    out: list[dict] = []
    archive_end: date | None = None
    try:
        daily = store.rainfall_daily()
        archive_end = max(daily["date"]) if not daily.empty else None
        for row in daily.itertuples():
            if (start and row.date < start) or (end and row.date > end):
                continue
            out.append(
                {
                    "date": row.date.isoformat(),
                    "rain_mm": None if pd.isna(row.rain_mm) else float(row.rain_mm),
                    "hours_with_data": None,
                    "source": "met_eireann_daily_archive",
                    "complete": not pd.isna(row.rain_mm),
                }
            )
    except DatasetMissing:
        pass

    if not hourly.empty:
        frame = hourly.dropna(subset=["rain_mm"]).copy()
        # Hour-ending timestamps: the 00:00 value belongs to the previous day (00-24 UTC).
        frame["day"] = (frame["datetime_utc"] - pd.Timedelta(minutes=1)).dt.date
        grouped = frame.groupby("day").agg(total=("rain_mm", "sum"), hours=("rain_mm", "size"))
        for day, row in grouped.iterrows():
            if archive_end and day <= archive_end:
                continue
            if (start and day < start) or (end and day > end):
                continue
            complete = int(row["hours"]) >= 24
            out.append(
                {
                    "date": day.isoformat(),
                    "rain_mm": round(float(row["total"]), 1) if complete else None,
                    "hours_with_data": int(row["hours"]),
                    "source": "met_eireann_hourly_reports",
                    "complete": complete,
                }
            )
    # Make missing days explicit so charts show gaps instead of silently closing them.
    if out:
        present = {r["date"] for r in out}
        first = start or date.fromisoformat(out[0]["date"])
        last = min(end or date.fromisoformat(out[-1]["date"]), datetime.now(timezone.utc).date())
        day = first
        while day <= last:
            if day.isoformat() not in present:
                out.append({"date": day.isoformat(), "rain_mm": None, "hours_with_data": 0, "source": "none", "complete": False})
            day += timedelta(days=1)
    out.sort(key=lambda r: r["date"])
    return out


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
