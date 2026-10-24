"""Feature engineering shared by model training and runtime prediction.

All rainfall features use COMPLETE days strictly before the sample/prediction date, so a
prediction for day D can be made at the start of day D (no same-day leakage).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Mapping

# EU Bathing Water Directive (2006/7/EC) coastal-water "Excellent" thresholds per 100 ml.
ECOLI_THRESHOLD = 250.0
ENTEROCOCCI_THRESHOLD = 100.0

RAIN_WINDOWS = {
    "rain_d1": (1, 1),  # yesterday
    "rain_d2_3": (2, 3),  # the two days before yesterday
    "rain_d4_7": (4, 7),  # antecedent wetness, days 4-7 before
}
SEASON_FEATURES = ["season_sin", "season_cos"]


def is_elevated(e_coli: float | None, enterococci: float | None) -> bool | None:
    """Target: either indicator above the coastal 'Excellent' threshold. None if both unknown."""
    if e_coli is None and enterococci is None:
        return None
    return bool((e_coli or 0) > ECOLI_THRESHOLD or (enterococci or 0) > ENTEROCOCCI_THRESHOLD)


def rain_window(daily: Mapping[date, float | None], day: date, first: int, last: int) -> float | None:
    """Total rainfall from day-last to day-first (inclusive). None if any day is missing."""
    total = 0.0
    for lag in range(first, last + 1):
        value = daily.get(day - timedelta(days=lag))
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        total += float(value)
    return total


def season_features(day: date) -> dict[str, float]:
    angle = 2 * math.pi * (day.timetuple().tm_yday - 1) / 365.25
    return {"season_sin": math.sin(angle), "season_cos": math.cos(angle)}


def build_features(daily: Mapping[date, float | None], day: date, rain_features: list[str]) -> tuple[dict[str, float] | None, dict]:
    """Return (numeric features, raw values) for one day, or (None, raw) if rainfall is missing.

    Rain totals are log1p-transformed: runoff response saturates, and it tames heavy-tailed totals.
    """
    raw: dict[str, float | None] = {}
    features: dict[str, float] = {}
    for name in rain_features:
        first, last = RAIN_WINDOWS[name]
        total = rain_window(daily, day, first, last)
        raw[name] = None if total is None else round(total, 1)
        if total is None:
            return None, raw
        features[name] = math.log1p(total)
    features.update(season_features(day))
    return features, raw
