"""OPW waterlevel.ie hydrometric acquisition (near-real-time river levels and water temperature).

Source: https://waterlevel.ie (Office of Public Works). Readings are provisional, unvalidated
real-time data published as-is by OPW.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import Point, shape

from app.geo import STUDY_AREA_BBOX, STUDY_CATCHMENT_NAME, normalize_point_geometry
from app.ingest.common import get_with_retries, update_manifest, utc_now_iso, write_json

OPW_BASE = "https://waterlevel.ie"
OPW_LATEST = f"{OPW_BASE}/geojson/latest/"
OPW_LICENCE = (
    "Not verified by RunoffPulse: review the waterlevel.ie disclaimer/terms before redistribution. "
    "Attribution: Office of Public Works (OPW)"
)
# Sensor 0003 is logger battery voltage and is deliberately excluded.
SENSORS = {
    "0001": {"parameter": "Water level", "unit": "m (local staff gauge datum)"},
    "0002": {"parameter": "Water temperature", "unit": "°C"},
    "OD": {"parameter": "Water level (Ordnance Datum)", "unit": "m OD Malin"},
}


def load_screened_catchments(data_dir: Path) -> list[tuple[str, dict]]:
    """(name, geometry) for every connected catchment; falls back to the study catchment alone."""
    for filename in ("screened_catchments.geojson", "catchment.geojson"):
        path = data_dir / filename
        if path.exists():
            fc = json.loads(path.read_text(encoding="utf-8"))
            return [(f["properties"]["Name"], f["geometry"]) for f in fc["features"]]
    return []


def parse_latest(
    payload: dict, catchment_geometry: dict | None, screened: list[tuple[str, dict]] | None = None
) -> list[dict]:
    """Keep sensors in the study area or in any connected catchment, tagging which catchment each is in."""
    catchment = shape(catchment_geometry).buffer(0) if catchment_geometry else None
    polygons = [(name, shape(geom).buffer(0)) for name, geom in (screened or [])]
    features = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        sensor = props.get("sensor_ref")
        if sensor not in SENSORS:
            continue
        geometry, _ = normalize_point_geometry(feature.get("geometry"))
        if geometry is None:
            continue
        lon, lat = geometry["coordinates"]
        point = Point(lon, lat)
        in_study = bool(catchment and catchment.covers(point))
        catchment_name = next((name for name, poly in polygons if poly.covers(point)), None)
        if catchment_name is None and in_study:
            catchment_name = STUDY_CATCHMENT_NAME
        if not STUDY_AREA_BBOX.contains(lon, lat) and catchment_name is None:
            continue
        try:
            value = float(props.get("value"))
        except (TypeError, ValueError):
            value = None
        station_ref = str(props.get("station_ref", ""))
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "station_ref": station_ref,
                    "station_number": station_ref.lstrip("0"),
                    "station_name": props.get("station_name"),
                    "sensor_ref": sensor,
                    "parameter": SENSORS[sensor]["parameter"],
                    "unit": SENSORS[sensor]["unit"],
                    "value": value,
                    "observed_at": props.get("datetime"),
                    "err_code": props.get("err_code"),
                    "in_study_catchment": in_study,
                    "catchment_name": catchment_name,
                    "data_status": "REAL_OBSERVATION",
                    "source": "OPW waterlevel.ie",
                    "station_url": f"{OPW_BASE}{props.get('url', '')}",
                },
            }
        )
    return features


def parse_series_csv(text: str) -> list[dict[str, Any]]:
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            value = float(row["value"])
            moment = datetime.strptime(row["datetime"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        rows.append({"datetime_utc": moment.strftime("%Y-%m-%dT%H:%MZ"), "value": value})
    return rows


def acquire_opw(client: httpx.Client, data_dir: Path) -> dict[str, Any]:
    retrieved_at = utc_now_iso()
    catchment_path = data_dir / "catchment.geojson"
    catchment_geometry = None
    if catchment_path.exists():
        catchment_geometry = json.loads(catchment_path.read_text(encoding="utf-8"))["features"][0]["geometry"]

    features = parse_latest(
        get_with_retries(client, OPW_LATEST).json(), catchment_geometry, load_screened_catchments(data_dir)
    )
    write_json(
        data_dir / "opw_latest.geojson",
        {
            "type": "FeatureCollection",
            "name": "opw_latest_snapshot",
            "source": OPW_LATEST,
            "retrieved_at": retrieved_at,
            "crs": "EPSG:4326",
            "licence": OPW_LICENCE,
            "features": features,
        },
    )

    # 30-day 15-minute level series for each in-catchment level sensor (used for the
    # river-response percentile in the risk screen).
    series_dir = data_dir / "opw_series"
    series_dir.mkdir(parents=True, exist_ok=True)
    series_count = 0
    for feature in features:
        props = feature["properties"]
        if props["sensor_ref"] != "0001" or not props["catchment_name"]:
            continue
        number = props["station_number"]
        url = f"{OPW_BASE}/data/month/{number}_0001.csv"
        try:
            rows = parse_series_csv(get_with_retries(client, url, attempts=2).text)
        except Exception:
            continue
        if rows:
            write_json(
                series_dir / f"{number}_0001.json",
                {"station_number": number, "source": url, "retrieved_at": retrieved_at, "unit": "m", "values": rows},
            )
            series_count += 1

    stations = {f["properties"]["station_ref"] for f in features}
    update_manifest(
        data_dir,
        "opw_water_levels",
        {
            "title": "OPW hydrometric stations: latest water level and temperature (snapshot)",
            "file": "opw_latest.geojson (+ opw_series/*.json 30-day level series)",
            "publisher": "Office of Public Works (OPW), waterlevel.ie",
            "source_url": OPW_LATEST,
            "licence": OPW_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "EPSG:4326",
            "record_count": len(features),
            "station_count": len(stations),
            "series_count": series_count,
            "data_status": "REAL_OBSERVATION",
            "notes": "Provisional real-time data, not quality-controlled. The API also serves this feed live "
            "(cached); this file is the fallback snapshot. Logger voltage (sensor 0003) excluded.",
        },
    )
    return {"opw_sensors": len(features), "opw_stations": len(stations), "opw_series": series_count}
