"""Offline fixtures: a small synthetic data directory so tests never touch upstream services.

These fixtures are test data only. They are written to a temporary directory and are never
served by the running application.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["RUNOFFPULSE_LIVE_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import live, main  # noqa: E402
from app.data_store import DataStore, set_store  # noqa: E402
from app.geo import STUDY_CATCHMENT_NAME  # noqa: E402
from app.reports_db import ReportStore  # noqa: E402

SQUARE = {"type": "Polygon", "coordinates": [[[-8.8, 51.8], [-8.2, 51.8], [-8.2, 52.0], [-8.8, 52.0], [-8.8, 51.8]]]}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _fc(features, **extra):
    return {"type": "FeatureCollection", "retrieved_at": "2026-01-01T00:00:00Z", **extra, "features": features}


def _poly(lon, lat, d=0.01):
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}


def build_data_dir(root: Path, now: datetime, rain_per_hour: float = 0.0, gauge_level: float = 1.0) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "catchment.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "geometry": SQUARE, "properties": {"Catchment_Id": "19", "Name": STUDY_CATCHMENT_NAME}}
    ])))
    stations = [
        ("RS19L030500", "Lee at Inniscarra", "RIVER_STATION", -8.65, 51.90, True),
        ("TW060LE4001", "Lough Mahon", "TRANSITIONAL_STATION", -8.33, 51.88, True),
        ("CW050LE9001", "Outer Harbour", "COASTAL_STATION", -8.27, 51.79, False),
    ]
    (root / "monitoring_stations.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"StationID": sid, "StationName": name, "StationType": st, "WBWFDWISECODE": "IE_SW_060_0750",
                        "in_study_catchment": inside, "data_status": "REAL_STATION_LOCATION"}}
        for sid, name, st, lon, lat, inside in stations
    ], name="test_stations")))
    (root / "shellfish_waters.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "geometry": _poly(-8.25, 51.85), "properties": {
            "area_id": "IEPA2_0047", "name": "Linked Area", "adjacent_hydrometric_area": STUDY_CATCHMENT_NAME,
            "linked_to_study_catchment": True, "parent_waterbody_name": "Cork Harbour", "parent_waterbody_code": "IE_SW_060_0000",
            "parent_waterbody_wfd_status": "Good", "parent_waterbody_wfd_status_period": "SW 2019-2024", "data_status": "OFFICIAL_DESIGNATION"}},
        {"type": "Feature", "geometry": _poly(-8.50, 51.70), "properties": {
            "area_id": "IEPA2_0062", "name": "Unlinked Area", "adjacent_hydrometric_area": "Dunmanus-Bantry-Kenmare",
            "linked_to_study_catchment": False, "parent_waterbody_name": "Lower Bandon Estuary", "parent_waterbody_code": "IE_SW_080_0100",
            "parent_waterbody_wfd_status": "Poor", "parent_waterbody_wfd_status_period": "SW 2019-2024", "data_status": "OFFICIAL_DESIGNATION"}},
    ])))
    (root / "waterbodies.geojson").write_text(json.dumps(_fc([])))
    (root / "rivers.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-8.7, 51.9], [-8.5, 51.9]]},
         "properties": {"European_Code": "IE_SW_19L010100", "Name": "LEE_010", "wfd_status": "Good"}}
    ])))
    (root / "pressures.json").write_text(json.dumps({"records": [
        {"waterbody_code": "IE_SW_19L010100", "pressure_category": "Agriculture", "intersects_study_catchment": True}
    ]}))

    with (root / "rainfall_daily.csv").open("w", newline="") as h:
        w = csv.writer(h)
        w.writerow(["station_id", "station_name", "date", "rain_mm", "rain_indicator"])
        start = (now - timedelta(days=400)).date()
        for i in range(380):
            day = start + timedelta(days=i)
            w.writerow(["3904", "Cork Airport", day.isoformat(), "" if i == 5 else f"{(i % 10) * 1.5:.1f}", "0"])
    with (root / "rainfall_hourly.csv").open("w", newline="") as h:
        w = csv.writer(h)
        w.writerow(["station_id", "station_name", "datetime_utc", "rain_mm", "rain_indicator", "source"])
        top = now.replace(minute=0, second=0, microsecond=0)
        for i in range(72, 0, -1):
            w.writerow(["3904", "Cork Airport", _iso(top - timedelta(hours=i - 1)), rain_per_hour, "0", "met_eireann_hourly_archive"])

    (root / "bathing_locations.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-8.26, 51.84]},
         "properties": {"beach_id": "IESWBWC060_0000_0100", "beach_name": "Test Beach", "classification": "Good Quality"}}
    ])))
    with (root / "bathing_measurements.csv").open("w", newline="") as h:
        w = csv.writer(h)
        w.writerow(["monitoring_result_id", "beach_id", "beach_name", "result_date", "indicator", "value_raw", "value",
                    "qualifier", "unit", "sample_water_quality_status"])
        w.writerow([1, "IESWBWC060_0000_0100", "Test Beach", "2025-07-01", "E. coli", "<10", 10, "<", "count/100 ml", "Excellent"])
        w.writerow([1, "IESWBWC060_0000_0100", "Test Beach", "2025-07-01", "Intestinal enterococci", "5", 5, "", "count/100 ml", "Excellent"])
        w.writerow([2, "IESWBWC060_0000_0100", "Test Beach", "2025-08-15", "E. coli", "1200", 1200, "", "count/100 ml", "Poor"])
        w.writerow([2, "IESWBWC060_0000_0100", "Test Beach", "2025-08-15", "Intestinal enterococci", "400", 400, "", "count/100 ml", "Poor"])
    (root / "bathing_alerts.json").write_text(json.dumps({"retrieved_at": "2026-01-01T00:00:00Z", "alerts": []}))

    gauges = [("19001", "Ballea", -8.60, 51.85), ("19020", "Ballyedmond", -8.40, 51.95), ("19094", "Inniscarra Headrace", -8.65, 51.90)]
    opw_features = []
    series_dir = root / "opw_series"
    series_dir.mkdir(exist_ok=True)
    for number, name, lon, lat in gauges:
        opw_features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
            "station_ref": f"00000{number}", "station_number": number, "station_name": name, "sensor_ref": "0001",
            "parameter": "Water level", "unit": "m", "value": gauge_level, "observed_at": _iso(now - timedelta(minutes=30)),
            "in_study_catchment": True, "data_status": "REAL_OBSERVATION", "station_url": "https://waterlevel.ie/"}})
        values = [{"datetime_utc": _iso(now - timedelta(minutes=15 * k)), "value": 0.5 + (k % 100) / 200}
                  for k in range(2880, 0, -1)]
        (series_dir / f"{number}_0001.json").write_text(json.dumps({"station_number": number, "values": values}))
    (root / "opw_latest.geojson").write_text(json.dumps(_fc(opw_features)))
    (root / "manifest.json").write_text(json.dumps({"datasets": {
        "epa_monitoring_stations": {"id": "epa_monitoring_stations", "title": "Stations", "retrieved_at": "2026-01-01T00:00:00Z",
                                    "data_status": "REAL_STATION_LOCATION", "licence": "CC BY 4.0"}
    }}))
    return root


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def data_dir(tmp_path: Path, now: datetime) -> Path:
    return build_data_dir(tmp_path / "data", now)


@pytest.fixture
def client(tmp_path: Path, data_dir: Path):
    set_store(DataStore(data_dir))
    main.set_report_store(ReportStore(tmp_path / "var" / "test.sqlite3", tmp_path / "var" / "uploads"))
    main.clear_risk_cache()
    live.clear_cache()
    with TestClient(main.app) as test_client:
        yield test_client
    set_store(None)
    main.set_report_store(None)
    main.clear_risk_cache()
