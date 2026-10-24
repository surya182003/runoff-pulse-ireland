"""Assemble risk-engine inputs from the acquired datasets and live feeds."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from shapely.geometry import shape

from app.data_store import DataStore, DatasetMissing
from app.geo import SCREENED_CATCHMENTS, STUDY_CATCHMENT_NAME, haversine_km

SCREENED_NAMES = set(SCREENED_CATCHMENTS.values())
from app.live import met_latest_hourly, opw_latest
from app.rainfall import (
    STATION,
    combined_hourly,
    latest_observation,
    percentile_of,
    two_day_climatology,
    window_stats,
)
from app.risk_engine import (
    LIMITATIONS,
    AreaInput,
    GaugeInput,
    RainfallInput,
    ScreeningConfig,
    WaterQualitySample,
    config_as_dict,
    screen_area,
)

# Gauges excluded from the river-response signal, with the reason shown in the API.
EXCLUDED_GAUGES = {
    "19094": "Inniscarra headrace: reservoir level regulated by ESB dam operation",
    "19095": "Carrigadrohid headrace: reservoir level regulated by ESB dam operation",
    "19109": "Inniscarra tailrace: discharge regulated by dam releases",
    "19161": "St Patrick's Quay: tidal reach of the Lee in Cork city",
    "19163": "Pope's Quay: tidal reach of the Lee in Cork city",
    "19164": "Mercy Hospital: tidal reach of the Lee in Cork city",
    "19118": "Ballyedmond backup: duplicate sensor of 19020",
}
WQ_CONTEXT_RADIUS_KM = 10.0
MIN_SERIES_POINTS = 960  # ten days of 15-minute readings


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def build_rainfall_input(store: DataStore, as_of: datetime, live: bool) -> tuple[RainfallInput | None, dict]:
    live_info = met_latest_hourly() if live else {"frame": None, "mode": "NOT_USED", "retrieved_at": None, "error": None}
    hourly = combined_hourly(store, live_info.get("frame"))
    w24 = window_stats(hourly, as_of, 24)
    w48 = window_stats(hourly, as_of, 48)
    latest = latest_observation(hourly, as_of)
    climatology = two_day_climatology(store)
    meta = {
        "mode": live_info.get("mode"),
        "live_retrieved_at": live_info.get("retrieved_at"),
        "live_error": live_info.get("error"),
        "window_24h": w24.as_dict(),
        "window_48h": w48.as_dict(),
    }
    if latest is None:
        return None, meta
    latest_time = latest["datetime_utc"].to_pydatetime()
    return (
        RainfallInput(
            station_name=f"Met Éireann {STATION['name']}",
            total_24h_mm=None if w24.total_mm is None else round(w24.total_mm, 1),
            total_48h_mm=None if w48.total_mm is None else round(w48.total_mm, 1),
            coverage_48h=round(w48.coverage, 2),
            max_hourly_24h_mm=w24.max_hourly_mm,
            latest_observation_utc=latest_time.isoformat().replace("+00:00", "Z"),
            latest_age_hours=round((as_of - latest_time).total_seconds() / 3600, 2),
            percentile_48h=None if w48.total_mm is None else percentile_of(climatology, w48.total_mm),
            climatology_years="2015-present daily archive" if climatology.size else None,
        ),
        meta,
    )


def build_gauge_inputs(store: DataStore, as_of: datetime, current: bool) -> tuple[list[GaugeInput], dict]:
    latest = opw_latest()
    gauges: list[GaugeInput] = []
    excluded: list[dict] = []
    for feature in latest["features"]:
        props = feature["properties"]
        # Snapshots acquired before multi-catchment support only carry in_study_catchment.
        catchment = props.get("catchment_name") or (STUDY_CATCHMENT_NAME if props.get("in_study_catchment") else None)
        if props.get("sensor_ref") != "0001" or catchment not in SCREENED_NAMES:
            continue
        number = props["station_number"]
        if number in EXCLUDED_GAUGES:
            excluded.append({"station_number": number, "station_name": props["station_name"], "reason": EXCLUDED_GAUGES[number]})
            continue
        series = store.opw_series(number)
        window_start = as_of - timedelta(days=30)
        values = [
            (t, v["value"])
            for v in series
            if (t := _parse_utc(v["datetime_utc"])) is not None and window_start <= t <= as_of
        ]
        level: float | None
        observed: datetime | None
        if current:
            level, observed = props.get("value"), _parse_utc(props.get("observed_at"))
        else:
            level, observed = (values[-1][1], values[-1][0]) if values else (None, None)
        pct = None
        if level is not None and len(values) >= MIN_SERIES_POINTS:
            pct = percentile_of(np.sort(np.array([v for _, v in values])), level)
        gauges.append(
            GaugeInput(
                station_number=number,
                station_name=props["station_name"],
                latest_level_m=level,
                observed_at=observed.isoformat().replace("+00:00", "Z") if observed else None,
                age_hours=round((as_of - observed).total_seconds() / 3600, 2) if observed else None,
                percentile_30d=None if pct is None else round(pct, 3),
                series_points=len(values),
                catchment=catchment,
            )
        )
    gauges.sort(key=lambda g: g.station_number)
    return gauges, {
        "mode": latest["mode"],
        "retrieved_at": latest["retrieved_at"],
        "error": latest["error"],
        "excluded_gauges": excluded,
    }


def _bathing_samples(store: DataStore, as_of: datetime) -> list[dict]:
    try:
        df = store.bathing_measurements()
    except DatasetMissing:
        return []
    as_of_date = as_of.date()
    df = df[df["result_date"].notna() & (df["result_date"] <= as_of_date)]
    df = df[df["result_date"] >= as_of_date - timedelta(days=60)]
    samples = []
    for (beach_id, sample_date), group in df.groupby(["beach_id", "result_date"]):
        by_indicator = {row.indicator: row for row in group.itertuples()}
        first = group.iloc[0]
        ecoli = by_indicator.get("E. coli")
        ent = by_indicator.get("Intestinal enterococci")
        samples.append(
            {
                "beach_id": beach_id,
                "beach_name": first["beach_name"],
                "sample_date": sample_date,
                "status": first["sample_water_quality_status"] or None,
                "e_coli": ecoli.value_raw if ecoli is not None else None,
                "enterococci": ent.value_raw if ent is not None else None,
            }
        )
    return samples


def screening_areas(store: DataStore) -> list[dict]:
    """Designated shellfish waters plus transitional/coastal waterbodies fed by a connected catchment."""
    areas = []
    for f in store.features_or_empty("shellfish_waters.geojson"):
        p = f["properties"]
        areas.append(
            {
                "area_id": p["area_id"],
                "name": p["name"],
                "area_type": "Designated shellfish water",
                "geometry": f["geometry"],
                "linked": p.get("adjacent_hydrometric_area") in SCREENED_NAMES,
                "adjacent_hydrometric_area": p.get("adjacent_hydrometric_area"),
                "context": {
                    "parent_waterbody": p.get("parent_waterbody_name"),
                    "parent_waterbody_code": p.get("parent_waterbody_code"),
                    "parent_wfd_status": p.get("parent_waterbody_wfd_status"),
                    "parent_wfd_status_period": p.get("parent_waterbody_wfd_status_period"),
                },
            }
        )
    for f in store.features_or_empty("waterbodies.geojson"):
        p = f["properties"]
        # Only waterbodies fed by a connected catchment are screened; others (e.g. Bantry Bay) are out of scope.
        if p.get("AdjacentHydrometricArea") not in SCREENED_NAMES:
            continue
        areas.append(
            {
                "area_id": p["EU_CD"],
                "name": p["NAME"],
                "area_type": f"{p['waterbody_category']} waterbody",
                "geometry": f["geometry"],
                "linked": True,
                "adjacent_hydrometric_area": p.get("AdjacentHydrometricArea"),
                "context": {
                    "parent_waterbody": p["NAME"],
                    "parent_waterbody_code": p["EU_CD"],
                    "parent_wfd_status": p.get("wfd_status"),
                    "parent_wfd_status_period": p.get("wfd_status_period"),
                },
            }
        )
    return areas


def pressure_summary(store: DataStore) -> dict[str, int]:
    records = store.json_or("pressures.json", {"records": []})["records"]
    summary: dict[str, set] = {}
    for r in records:
        if r.get("intersects_study_catchment"):
            summary.setdefault(r["pressure_category"], set()).add(r["waterbody_code"])
    return {k: len(v) for k, v in sorted(summary.items())}


def run_screening(store: DataStore, as_of: datetime | None = None, cfg: ScreeningConfig | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    current = as_of is None or abs((now - as_of).total_seconds()) < 3600
    as_of = as_of or now
    cfg = cfg or ScreeningConfig()

    rainfall, rain_meta = build_rainfall_input(store, as_of, live=current)
    gauges, gauge_meta = build_gauge_inputs(store, as_of, current=current)
    samples = _bathing_samples(store, as_of)
    beaches = {
        f["properties"]["beach_id"]: f["geometry"]["coordinates"]
        for f in store.features_or_empty("bathing_locations.geojson")
    }
    pressures = pressure_summary(store)

    results = []
    for area in screening_areas(store):
        centroid = shape(area["geometry"]).representative_point()
        wq: list[WaterQualitySample] = []
        for s in samples:
            coords = beaches.get(s["beach_id"])
            if not coords:
                continue
            distance = haversine_km(centroid.x, centroid.y, coords[0], coords[1])
            if distance > WQ_CONTEXT_RADIUS_KM:
                continue
            wq.append(
                WaterQualitySample(
                    beach_id=s["beach_id"],
                    beach_name=s["beach_name"],
                    sample_date=s["sample_date"].isoformat(),
                    age_days=(as_of.date() - s["sample_date"]).days,
                    sample_status=s["status"],
                    e_coli=s["e_coli"],
                    enterococci=s["enterococci"],
                    distance_km=round(distance, 1),
                )
            )
        wq.sort(key=lambda s: (s.age_days, s.distance_km or 0))
        context = {
            **area["context"],
            "adjacent_hydrometric_area": area["adjacent_hydrometric_area"],
            "catchment_significant_pressures": pressures if area["adjacent_hydrometric_area"] == STUDY_CATCHMENT_NAME else {},
            "water_quality_selection": f"Bathing waters within {WQ_CONTEXT_RADIUS_KM:.0f} km (proximity only, "
            "not a verified hydrological connection)",
        }
        linkage_basis = (
            f"Parent waterbody EPA attribute AdjacentHydrometricArea = '{area['adjacent_hydrometric_area']}'"
            if area["adjacent_hydrometric_area"]
            else "No AdjacentHydrometricArea attribute available"
        )
        area_input = AreaInput(
            area_id=area["area_id"],
            name=area["name"],
            area_type=area["area_type"],
            linked_to_study_catchment=area["linked"],
            linkage_basis=linkage_basis,
            rainfall=rainfall,
            gauges=[g for g in gauges if g.catchment == area["adjacent_hydrometric_area"]],
            water_quality=wq,
            context=context,
        )
        result = screen_area(area_input, now, cfg)
        # Gauge readings are shared by every area in a catchment; they are returned once in shared_inputs.
        result["inputs"]["gauges"] = len(area_input.gauges)
        result["catchment"] = area["adjacent_hydrometric_area"]
        results.append(result)

    order = {"ELEVATED_SCREENING_RISK": 0, "POTENTIAL_RUNOFF_RISK": 1, "NO_ELEVATED_SIGNAL": 2, "INSUFFICIENT_DATA": 3}
    results.sort(key=lambda r: (order[r["classification"]], -(r["score"] or 0), r["name"]))
    counts: dict[str, int] = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    return {
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "mode": "CURRENT" if current else "HISTORICAL_REPLAY",
        "calculated_at": now.isoformat().replace("+00:00", "Z"),
        "counts": counts,
        "areas": results,
        "shared_inputs": {
            "rainfall": rain_meta,
            "gauges": {**gauge_meta, "readings": [asdict(g) for g in gauges]},
            "gauge_count_usable": sum(
                1 for g in gauges if g.percentile_30d is not None and g.age_hours is not None and g.age_hours <= cfg.max_gauge_age_hours
            ),
        },
        "method": {
            "config": config_as_dict(cfg),
            "documentation": "docs/RISK_METHOD.md",
            "limitations": LIMITATIONS,
        },
        "disclaimer": "Software-generated screening indicator (MODELLED_INDICATOR). Not an official "
        "public-health, bathing-water or shellfish-harvesting advisory.",
    }
