"""EPA Bathing Water open data API acquisition (locations, monitoring results, active alerts).

API docs: https://data.epa.ie/api-list/bathing-water-open-data/  (CC BY 4.0)
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import httpx

from app.geo import STUDY_AREA_BBOX, haversine_km, irish_grid_to_lonlat, validate_feature_collection
from app.ingest.common import AcquisitionError, get_with_retries, update_manifest, utc_now_iso, write_json
from app.ingest.met import STATION_LAT as MET_STATION_LAT
from app.ingest.met import STATION_LON as MET_STATION_LON

TRAINING_RADIUS_KM = 60.0
TRAINING_FIELDS = [
    "monitoring_result_id",
    "beach_id",
    "beach_name",
    "lon",
    "lat",
    "distance_to_rain_gauge_km",
    "in_study_area",
    "result_date",
    "e_coli",
    "e_coli_qualifier",
    "enterococci",
    "enterococci_qualifier",
    "sample_water_quality_status",
]

BW_API = "https://data.epa.ie/bw/api/v1"
BW_LICENCE = "CC BY 4.0 (EPA Ireland bathing water open data)"
PER_PAGE = 1000
MEASUREMENT_FIELDS = [
    "monitoring_result_id",
    "beach_id",
    "beach_name",
    "result_date",
    "indicator",
    "value_raw",
    "value",
    "qualifier",
    "unit",
    "sample_water_quality_status",
]
INDICATORS = {
    "e_coli_result": "E. coli",
    "intestinal_enterococci_result": "Intestinal enterococci",
}
# The API reports counts per 100 ml without naming the method (cfu or MPN), so the unit is
# recorded generically rather than guessed.
COUNT_UNIT = "count/100 ml"
_VALUE_RE = re.compile(r"^\s*([<>]=?)?\s*([0-9]+(?:\.[0-9]+)?)\s*$")


def parse_count(raw: Any) -> tuple[float | None, str | None]:
    """Parse values such as '272', '<10' or '>24196' into (number, qualifier)."""
    if raw is None:
        return None, None
    match = _VALUE_RE.match(str(raw))
    if not match:
        return None, None
    return float(match.group(2)), match.group(1)


def _paged(client: httpx.Client, endpoint: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        payload = get_with_retries(client, f"{BW_API}/{endpoint}", params={"page": page, "per_page": PER_PAGE}).json()
        batch = payload.get("list") or []
        items.extend(batch)
        count = payload.get("count") or 0
        if not batch or len(items) >= count:
            break
        page += 1
        if page > 200:
            raise AcquisitionError(f"bathing {endpoint}: too many pages")
    return items


def acquire_bathing(client: httpx.Client, data_dir: Path) -> dict[str, Any]:
    retrieved_at = utc_now_iso()
    locations = _paged(client, "locations")
    features = []
    for loc in locations:
        lonlat = irish_grid_to_lonlat(loc.get("easting"), loc.get("northing"))
        if lonlat is None or not STUDY_AREA_BBOX.contains(*lonlat):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": list(lonlat)},
                "properties": {
                    "beach_id": loc.get("beach_id"),
                    "beach_name": loc.get("beach_name"),
                    "local_authority": loc.get("local_authority_name"),
                    "classification": loc.get("current_annual_water_quality_classification"),
                    "classification_year": loc.get("current_annual_classification_year"),
                    "short_term_pollution_risk": loc.get("short_term_pollution_risk"),
                    "all_season_restriction": loc.get("has_all_season_bathing_restriction_in_place"),
                    "last_updated": loc.get("last_updated"),
                    "data_status": "OFFICIAL_ASSESSMENT",
                    "coordinate_note": "Converted from Irish Grid (TM65, EPSG:29903) easting/northing",
                },
            }
        )
    beach_ids = {f["properties"]["beach_id"] for f in features}

    # Wider set of beaches used only to TRAIN the ML model: all identified bathing waters within
    # TRAINING_RADIUS_KM of the Cork Airport rain gauge, so rainfall remains broadly representative.
    training_beaches: dict[str, dict[str, Any]] = {}
    for loc in locations:
        lonlat = irish_grid_to_lonlat(loc.get("easting"), loc.get("northing"))
        if lonlat is None:
            continue
        distance = haversine_km(lonlat[0], lonlat[1], MET_STATION_LON, MET_STATION_LAT)
        if distance <= TRAINING_RADIUS_KM:
            training_beaches[loc.get("beach_id")] = {
                "beach_name": (loc.get("beach_name") or "").strip(),
                "lon": lonlat[0],
                "lat": lonlat[1],
                "distance_to_rain_gauge_km": round(distance, 1),
                "in_study_area": loc.get("beach_id") in beach_ids,
            }

    collection = {
        "type": "FeatureCollection",
        "name": "bathing_water_locations",
        "source": "EPA Bathing Water API",
        "retrieved_at": retrieved_at,
        "crs": "EPSG:4326",
        "licence": BW_LICENCE,
        "features": features,
    }
    problems = validate_feature_collection(collection)
    if problems:
        raise AcquisitionError(f"bathing locations invalid: {problems[:5]}")
    write_json(data_dir / "bathing_locations.geojson", collection)
    update_manifest(
        data_dir,
        "epa_bathing_locations",
        {
            "title": "Identified bathing waters in the study area",
            "file": "bathing_locations.geojson",
            "publisher": "EPA Ireland (beaches.ie)",
            "source_url": f"{BW_API}/locations",
            "licence": BW_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "EPSG:4326 (converted from Irish Grid EPSG:29903; verified against known beach positions)",
            "record_count": len(features),
            "data_status": "OFFICIAL_ASSESSMENT",
            "notes": "Annual classification is the official multi-year EU Bathing Water Directive assessment.",
        },
    )

    retrieved_at = utc_now_iso()
    measurements = _paged(client, "measurements")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    for m in measurements:
        if m.get("beach_id") not in beach_ids:
            continue
        for field, indicator in INDICATORS.items():
            key = (m.get("monitoring_result_id"), indicator)
            if key in seen:
                continue
            seen.add(key)
            value, qualifier = parse_count(m.get(field))
            rows.append(
                {
                    "monitoring_result_id": m.get("monitoring_result_id"),
                    "beach_id": m.get("beach_id"),
                    "beach_name": (m.get("beach_name") or "").strip(),
                    "result_date": m.get("result_date"),
                    "indicator": indicator,
                    "value_raw": (m.get(field) or "").strip() if m.get(field) is not None else "",
                    "value": value,
                    "qualifier": qualifier or "",
                    "unit": COUNT_UNIT,
                    "sample_water_quality_status": m.get("sample_water_quality_status") or "",
                }
            )
    rows.sort(key=lambda r: (r["result_date"] or "", r["beach_id"], r["indicator"]))
    path = data_dir / "bathing_measurements.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEASUREMENT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row[k] is None else row[k]) for k in MEASUREMENT_FIELDS})
    dates = [r["result_date"] for r in rows if r["result_date"]]
    update_manifest(
        data_dir,
        "epa_bathing_measurements",
        {
            "title": "Bathing water bacteriological results (E. coli, intestinal enterococci)",
            "file": "bathing_measurements.csv",
            "publisher": "EPA Ireland (beaches.ie)",
            "source_url": f"{BW_API}/measurements",
            "licence": BW_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "n/a (joined to bathing_locations by beach_id)",
            "record_count": len(rows),
            "period": [min(dates), max(dates)] if dates else None,
            "data_status": "REAL_OBSERVATION",
            "notes": "Sampled during the bathing season only (typically June-mid September), so results "
            "are seasonal, not continuous. Censored values (e.g. '<10') keep their qualifier. Unit "
            "recorded as count/100 ml because the API does not state cfu vs MPN.",
        },
    )

    # One row per sample for the wider training set (both indicators side by side).
    training_rows = []
    for m in measurements:
        beach = training_beaches.get(m.get("beach_id"))
        if beach is None or not m.get("result_date"):
            continue
        ecoli, ecoli_q = parse_count(m.get("e_coli_result"))
        ent, ent_q = parse_count(m.get("intestinal_enterococci_result"))
        training_rows.append(
            {
                "monitoring_result_id": m.get("monitoring_result_id"),
                "beach_id": m.get("beach_id"),
                **beach,
                "result_date": m.get("result_date"),
                "e_coli": ecoli,
                "e_coli_qualifier": ecoli_q or "",
                "enterococci": ent,
                "enterococci_qualifier": ent_q or "",
                "sample_water_quality_status": m.get("sample_water_quality_status") or "",
            }
        )
    training_rows.sort(key=lambda r: (r["result_date"], r["beach_id"]))
    training_path = data_dir / "bathing_training_samples.csv"
    with training_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_FIELDS)
        writer.writeheader()
        for row in training_rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in TRAINING_FIELDS})
    update_manifest(
        data_dir,
        "epa_bathing_training_samples",
        {
            "title": f"Bathing water results within {TRAINING_RADIUS_KM:.0f} km of Cork Airport (ML training set)",
            "file": "bathing_training_samples.csv",
            "publisher": "EPA Ireland (beaches.ie)",
            "source_url": f"{BW_API}/measurements",
            "licence": BW_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "EPSG:4326 (converted from Irish Grid EPSG:29903)",
            "record_count": len(training_rows),
            "beach_count": len({r["beach_id"] for r in training_rows}),
            "data_status": "REAL_OBSERVATION",
            "notes": "Used only to train and evaluate the bathing-water ML model (scripts/train_bathing_model.py). "
            f"Beaches within {TRAINING_RADIUS_KM:.0f} km of the Met Éireann Cork Airport gauge so that one rain "
            "gauge is broadly representative.",
        },
    )

    retrieved_at = utc_now_iso()
    alerts = _paged(client, "alerts")
    write_json(
        data_dir / "bathing_alerts.json",
        {"retrieved_at": retrieved_at, "source": f"{BW_API}/alerts", "alerts": alerts},
    )
    update_manifest(
        data_dir,
        "epa_bathing_alerts",
        {
            "title": "Active bathing water alerts / incidents (national)",
            "file": "bathing_alerts.json",
            "publisher": "EPA Ireland (beaches.ie)",
            "source_url": f"{BW_API}/alerts",
            "licence": BW_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "n/a",
            "record_count": len(alerts),
            "data_status": "OFFICIAL_ADVISORY",
            "notes": "Only currently active alerts are published by the API. Zero records means no "
            "active alert at retrieval time, not a statement that water is safe.",
        },
    )
    return {"bathing_locations": len(features), "bathing_measurements": len(rows), "bathing_alerts": len(alerts)}
