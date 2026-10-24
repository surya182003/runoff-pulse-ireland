"""Runtime predictions from the exported logistic-regression model card (no scikit-learn needed)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.data_store import DataStore, DatasetMissing
from app.ml.features import RAIN_WINDOWS, build_features, is_elevated
from app.rainfall import combined_hourly, daily_series

MODEL_FILE = "models/bathing_model.json"
BACKTEST_FILE = "models/bathing_backtest.csv"
VARIANT_ORDER = ["recent", "full"]  # only variants present in the model card are used
FEATURE_LABELS = {
    "rain_d1": "Rain yesterday",
    "rain_d2_3": "Rain 2-3 days before",
    "rain_d4_7": "Rain 4-7 days before",
    "season_sin": "Time of year",
    "season_cos": "Time of year",
}


class ModelUnavailable(RuntimeError):
    pass


def load_model(store: DataStore) -> dict:
    card = store.json_or(MODEL_FILE, None)
    if card is None:
        raise ModelUnavailable("No trained model found. Run scripts/train_bathing_model.py.")
    return card


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def band_for(card: dict, p: float) -> str:
    for band in card["bands"]:
        if band["min"] <= p < band["max"] or (p >= band["max"] == 1.0):
            return band["band"]
    return card["bands"][-1]["band"]


def score(variant: dict, features: dict[str, float], beach_id: str) -> tuple[float, list[dict], float, bool]:
    """Return (probability, per-feature contributions on the log-odds scale, beach effect, beach known)."""
    mean, std = variant["standardisation"]["mean"], variant["standardisation"]["std"]
    logit = variant["intercept"]
    contributions: dict[str, float] = {}
    for name, coef in variant["coefficients"].items():
        z = (features[name] - mean[name]) / std[name]
        value = coef * z
        label = FEATURE_LABELS.get(name, name)
        contributions[label] = contributions.get(label, 0.0) + value
        logit += value
    beach_known = beach_id in variant["beach_coefficients"]
    beach_effect = variant["beach_coefficients"].get(beach_id, 0.0)
    logit += beach_effect
    drivers = [{"factor": k, "log_odds": round(v, 3)} for k, v in contributions.items()]
    drivers.append({"factor": "Beach history", "log_odds": round(beach_effect, 3)})
    drivers.sort(key=lambda d: -abs(d["log_odds"]))
    return sigmoid(logit), drivers, beach_effect, beach_known


def complete_daily_rain(store: DataStore, live_frame: pd.DataFrame | None, start: date, end: date) -> dict[date, float]:
    hourly = combined_hourly(store, live_frame)
    records = daily_series(store, hourly, start, end)
    return {date.fromisoformat(r["date"]): r["rain_mm"] for r in records if r["complete"] and r["rain_mm"] is not None}


def _observed(store: DataStore, day: date) -> dict[str, dict]:
    try:
        df = store.bathing_measurements()
    except DatasetMissing:
        return {}
    df = df[df["result_date"] == day]
    out: dict[str, dict] = {}
    for beach_id, g in df.groupby("beach_id"):
        vals = {r.indicator: r for r in g.itertuples()}
        ec, ie = vals.get("E. coli"), vals.get("Intestinal enterococci")
        ec_v = None if ec is None or ec.value != ec.value else float(ec.value)
        ie_v = None if ie is None or ie.value != ie.value else float(ie.value)
        out[beach_id] = {
            "e_coli": ec.value_raw if ec is not None else None,
            "enterococci": ie.value_raw if ie is not None else None,
            "elevated": is_elevated(ec_v, ie_v),
            "sample_status": g.iloc[0]["sample_water_quality_status"] or None,
        }
    return out


def _backtest(store: DataStore, day: date) -> dict[str, float]:
    path = store.path(BACKTEST_FILE)
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    df = df[df["date"] == day.isoformat()]
    return dict(zip(df["beach_id"], df["p_out_of_sample"]))


def predict_for_date(store: DataStore, day: date, live_frame: pd.DataFrame | None = None) -> dict[str, Any]:
    card = load_model(store)
    lookback = max(last for _, last in RAIN_WINDOWS.values())
    rain = complete_daily_rain(store, live_frame, day - timedelta(days=lookback + 1), day)

    chosen_name, chosen, features, raw = None, None, None, {}
    for name in VARIANT_ORDER:
        variant = card["variants"].get(name)
        if not variant:
            continue
        feats, raw_vals = build_features(rain, day, variant["rain_features"])
        raw = raw or raw_vals  # keep the richest variant's inputs for display if all variants fail
        if feats is not None:
            chosen_name, chosen, features, raw = name, variant, feats, raw_vals
            break

    beaches = store.features_or_empty("bathing_locations.geojson")
    observed = _observed(store, day)
    backtest = _backtest(store, day)
    in_season = chosen is not None and day.month in chosen["training"]["months"]

    predictions = []
    for f in beaches:
        props = f["properties"]
        beach_id = props["beach_id"]
        item: dict[str, Any] = {
            "beach_id": beach_id,
            "beach_name": props["beach_name"],
            "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1],
            "probability": None,
            "band": None,
            "drivers": [],
            "observed": observed.get(beach_id),
            "backtest_out_of_sample_probability": backtest.get(beach_id),
        }
        if chosen is not None:
            p, drivers, _, known = score(chosen, features, beach_id)
            item.update(
                probability=round(p, 4),
                band=band_for(card, p),
                drivers=drivers,
                beach_in_training=known,
            )
        predictions.append(item)
    predictions.sort(key=lambda x: -(x["probability"] or -1))

    if chosen is None:
        status, message = (
            "UNAVAILABLE",
            "The previous day's full rainfall record is not available for this date, so no forecast is shown "
            "rather than a guess.",
        )
    elif not in_season:
        status, message = (
            "OUT_OF_SEASON",
            "Beaches are only tested from May to September, so the model has no off-season examples to learn "
            "from. Treat these numbers as a rough guide.",
        )
    else:
        status, message = "OK", "Bathing-season forecast based on the previous day's rainfall."

    return {
        "date": day.isoformat(),
        "status": status,
        "message": message,
        "model_id": card["model_id"],
        "model_version": card["version"],
        "variant": chosen_name,
        "inputs": {"rainfall_mm": raw, "rain_station": "Met Éireann Cork Airport"},
        "predictions": predictions,
        "target": card["target"],
        "bands": card["bands"],
        "data_status": "MODELLED_INDICATOR",
        "disclaimer": "Machine-learning estimate of the chance of elevated bacteria in a sample. Not an official "
        "bathing-water advisory and not a measurement.",
        "calculated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def model_card(store: DataStore) -> dict:
    card = load_model(store)
    public = {k: v for k, v in card.items() if k != "variants"}
    public["variants"] = {
        name: {k: v for k, v in variant.items() if k not in ("standardisation", "beach_coefficients")}
        | {"beach_effects": sorted(
            ({"beach_id": b, "beach_name": variant["beach_names"].get(b, b), "log_odds": round(c, 3)}
             for b, c in variant["beach_coefficients"].items()),
            key=lambda e: -e["log_odds"])}
        for name, variant in card["variants"].items()
    }
    return public
