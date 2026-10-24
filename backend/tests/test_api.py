from datetime import datetime, timedelta, timezone

from app import main
from app.reports_db import ReportStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def valid_report(**overrides):
    data = {
        "category": "FOAM",
        "description": "Brown foam along the shoreline near the slipway.",
        "latitude": "51.85",
        "longitude": "-8.29",
        "observed_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }
    data.update(overrides)
    return data


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["live_feeds_enabled"] is False


def test_stations_geojson_and_filters(client):
    body = client.get("/api/stations").json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    assert body["meta"]["station_types"]["RIVER_STATION"] == 1
    rivers = client.get("/api/stations", params={"station_type": "river_station"}).json()
    assert [f["properties"]["StationID"] for f in rivers["features"]] == ["RS19L030500"]
    outside = client.get("/api/stations", params={"in_catchment": "false"}).json()
    assert [f["properties"]["StationID"] for f in outside["features"]] == ["CW050LE9001"]
    search = client.get("/api/stations", params={"q": "mahon"}).json()
    assert len(search["features"]) == 1


def test_station_detail_and_404(client):
    body = client.get("/api/stations/RS19L030500").json()
    assert body["station"]["properties"]["StationName"] == "Lee at Inniscarra"
    assert body["observations"] == []
    assert "not connected" in body["observations_note"]
    assert "Proximity does not establish" in body["proximity_note"]
    assert client.get("/api/stations/NOPE").status_code == 404


def test_rivers_and_catchment(client):
    assert len(client.get("/api/rivers").json()["features"]) == 1
    assert client.get("/api/catchment").json()["catchment_id"] == "19"


def test_rainfall_daily_filters_and_missing_values(client, now):
    start = (now - timedelta(days=398)).date()
    end = start + timedelta(days=9)
    body = client.get("/api/rainfall", params={"start": start.isoformat(), "end": end.isoformat()}).json()
    archive = [r for r in body["records"] if r["source"] == "met_eireann_daily_archive"]
    assert len(archive) == 10
    assert all(start.isoformat() <= r["date"] <= end.isoformat() for r in archive)
    assert any(r["rain_mm"] is None for r in archive)  # the blank day stays null
    assert body["data_status"] == "REAL_OBSERVATION"
    assert body["windows"]["last_24h"]["coverage"] >= 0.95


def test_rainfall_missing_days_are_explicit_gaps(client, now):
    # Fixture archive ends ~20 days ago and hourly data covers only the last 3 days.
    start = (now - timedelta(days=30)).date()
    body = client.get("/api/rainfall", params={"start": start.isoformat(), "end": now.date().isoformat()}).json()
    dates = [r["date"] for r in body["records"]]
    assert len(dates) == len(set(dates)) == 31  # every day present exactly once
    gaps = [r for r in body["records"] if r["source"] == "none"]
    assert gaps and all(r["rain_mm"] is None and r["complete"] is False for r in gaps)


def test_rainfall_validation_errors(client):
    assert client.get("/api/rainfall", params={"start": "2026-02-01", "end": "2026-01-01"}).status_code == 422
    assert client.get("/api/rainfall", params={"resolution": "hourly", "start": "2026-01-01", "end": "2026-03-01"}).status_code == 422
    assert client.get("/api/rainfall", params={"resolution": "weekly"}).status_code == 422
    assert client.get("/api/rainfall", params={"start": "not-a-date"}).status_code == 422


def test_water_quality_filters(client):
    body = client.get("/api/water-quality", params={"indicator": "E. coli"}).json()
    assert body["total_matching"] == 2
    assert {r["measurement"] for r in body["records"]} == {"E. coli"}
    censored = body["records"][0]
    assert censored["value_raw"] == "<10" and censored["qualifier"] == "<"
    dated = client.get("/api/water-quality", params={"start": "2025-08-01", "end": "2025-08-31"}).json()
    assert dated["total_matching"] == 2 and all(r["observed_date"] == "2025-08-15" for r in dated["records"])
    assert client.get("/api/water-quality", params={"station": "UNKNOWN"}).json()["records"] == []
    assert body["not_connected"]


def test_risk_screening_current(client):
    body = client.get("/api/risk").json()
    by_id = {a["area_id"]: a for a in body["areas"]}
    assert by_id["IEPA2_0062"]["classification"] == "INSUFFICIENT_DATA"
    linked = by_id["IEPA2_0047"]
    assert linked["classification"] in {"NO_ELEVATED_SIGNAL", "POTENTIAL_RUNOFF_RISK", "ELEVATED_SCREENING_RISK"}
    assert linked["score"] is not None
    assert linked["data_status"] == "MODELLED_INDICATOR"
    # The dam-regulated headrace gauge is excluded with a reason.
    excluded = body["shared_inputs"]["gauges"]["excluded_gauges"]
    assert [g["station_number"] for g in excluded] == ["19094"]
    assert body["method"]["limitations"]
    assert "Not an official" in body["disclaimer"]


def test_risk_elevates_with_heavy_rain_and_high_rivers(tmp_path, now):
    from conftest import build_data_dir
    from fastapi.testclient import TestClient

    from app.data_store import DataStore, set_store

    set_store(DataStore(build_data_dir(tmp_path / "wet", now, rain_per_hour=1.5, gauge_level=5.0)))
    main.clear_risk_cache()
    try:
        body = TestClient(main.app).get("/api/risk").json()
    finally:
        set_store(None)
        main.clear_risk_cache()
    linked = next(a for a in body["areas"] if a["area_id"] == "IEPA2_0047")
    assert linked["classification"] == "ELEVATED_SCREENING_RISK"
    assert linked["components"]["river_response"] == 1.0


def test_risk_as_of_validation(client):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert client.get("/api/risk", params={"as_of": future}).status_code == 422
    assert client.get("/api/risk", params={"as_of": "yesterday"}).status_code == 422
    replay = client.get("/api/risk", params={"as_of": "2024-01-15"}).json()
    assert replay["mode"] == "HISTORICAL_REPLAY"
    assert all(a["classification"] == "INSUFFICIENT_DATA" for a in replay["areas"])  # no fixture data then


def test_aquaculture_never_infers_official_status(client):
    body = client.get("/api/aquaculture").json()
    assert body["official_advisories"]["status"] == "NOT_CONNECTED"
    assert body["production_areas"]["available"] is False
    props = body["shellfish_waters"]["features"][0]["properties"]
    assert props["official_advisory_status"] == "NOT_CONNECTED"
    assert props["screening"]["is_official_advisory"] is False


def test_alerts_distinguish_screening_and_official(client):
    body = client.get("/api/alerts").json()
    assert body["official_alerts"] == []
    assert body["delivery"]["external_notifications"] == "DISABLED"
    for alert in body["screening_alerts"]:
        assert "not an official" in alert["issued_by"]


def test_report_create_list_and_persist(client, tmp_path):
    created = client.post("/api/reports", data=valid_report())
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["verification_status"] == "UNVERIFIED"
    assert report["data_status"] == "CITIZEN_REPORTED_UNVERIFIED"
    assert report["has_photo"] is False

    page = client.get("/api/reports", params={"page": 1, "page_size": 10}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == report["id"]

    # Persistence: a fresh store on the same database sees the report.
    reopened = ReportStore(tmp_path / "var" / "test.sqlite3", tmp_path / "var" / "uploads")
    assert reopened.get(report["id"]).description.startswith("Brown foam")


def test_report_with_photo(client):
    created = client.post("/api/reports", data=valid_report(), files={"photo": ("x.png", PNG, "image/png")})
    assert created.status_code == 201
    report = created.json()
    assert report["has_photo"] is True
    photo = client.get(f"/api/reports/{report['id']}/photo")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/png"


def test_report_validation(client):
    assert client.post("/api/reports", data=valid_report(category="SPILL")).status_code == 422
    assert client.post("/api/reports", data=valid_report(description="short")).status_code == 422
    assert client.post("/api/reports", data=valid_report(latitude="48.85", longitude="2.35")).status_code == 422
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/api/reports", data=valid_report(observed_at=future)).status_code == 422
    fake = client.post("/api/reports", data=valid_report(), files={"photo": ("x.png", b"<script>", "image/png")})
    assert fake.status_code == 415
    assert client.get("/api/reports", params={"page": 0}).status_code == 422
    assert client.get("/api/reports/../../etc/photo").status_code == 404


def test_report_photo_size_limit(client, monkeypatch):
    monkeypatch.setenv("RUNOFFPULSE_MAX_UPLOAD_BYTES", "100")
    big = client.post("/api/reports", data=valid_report(), files={"photo": ("x.png", PNG + b"\x00" * 200, "image/png")})
    assert big.status_code == 413


def test_sources_and_summary(client):
    sources = client.get("/api/sources").json()
    assert sources["datasets"][0]["licence"] == "CC BY 4.0"
    assert "SIMULATED_DEMO" in sources["data_status_definitions"]
    assert sources["not_connected"]
    summary = client.get("/api/summary").json()
    assert summary["monitoring_stations"]["total"] == 3
    assert summary["water_quality"]["usable_observations"] == 4
    assert summary["latest_rainfall"]["data_status"] == "REAL_OBSERVATION"
    assert "not confirmed pollution" in summary["screening"]["definition"]


def test_missing_dataset_returns_503(client, data_dir):
    (data_dir / "rivers.geojson").unlink()
    response = client.get("/api/rivers")
    assert response.status_code == 503
    assert "acquire_all.py" in response.json()["detail"]


def test_cors_restricted_to_dev_origin(client):
    allowed = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers
