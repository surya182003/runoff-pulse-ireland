"""RunoffPulse Ireland API."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from shapely.geometry import Point, shape

from app import __version__
from app.config import get_settings
from app.data_store import DataStore, DatasetMissing, get_store
from app.geo import STUDY_AREA_BBOX, STUDY_CATCHMENT_ID, STUDY_CATCHMENT_NAME, haversine_km
import pandas as pd

from app.live import met_latest_hourly, opw_latest
from app.ml.predict import ModelUnavailable, model_card, predict_for_date
from app.rainfall import STATION, combined_hourly, daily_series, latest_observation, window_stats
from app.reports_db import ReportStore, sniff_image_type
from app.schemas import ReportCategory, ReportCreate, ReportPage
from app.screening import EXCLUDED_GAUGES, run_screening

app = FastAPI(
    title="RunoffPulse Ireland API",
    version=__version__,
    description="Environmental decision-support prototype for Cork Harbour and the River Lee catchment. "
    "Screening outputs are not official advisories.",
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_report_store: ReportStore | None = None
_risk_cache: dict[str, tuple[float, dict]] = {}
_risk_lock = threading.Lock()
RISK_CACHE_SECONDS = 120


def store() -> DataStore:
    return get_store()


def report_store() -> ReportStore:
    global _report_store
    if _report_store is None:
        s = get_settings()
        _report_store = ReportStore(s.db_path, s.upload_dir)
    return _report_store


def set_report_store(value: ReportStore | None) -> None:
    global _report_store
    _report_store = value


def clear_risk_cache() -> None:
    with _risk_lock:
        _risk_cache.clear()


@app.exception_handler(DatasetMissing)
async def dataset_missing_handler(_: Request, exc: DatasetMissing) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": f"Dataset '{exc.args[0]}' has not been acquired. Run scripts/acquire_all.py.",
            "dataset": exc.args[0],
        },
    )


def _feature_collection(features: list[dict], **meta: Any) -> dict:
    return {"type": "FeatureCollection", "features": features, **meta}


def _layer_meta(ds: DataStore, filename: str) -> dict:
    layer = ds.geojson(filename)
    return {k: v for k, v in layer.items() if k not in ("features", "type")}


# --------------------------------------------------------------------------------------- health
@app.get("/api/health")
def health(ds: DataStore = Depends(store)) -> dict:
    required = ["monitoring_stations.geojson", "catchment.geojson", "rainfall_daily.csv"]
    missing = [name for name in required if not ds.exists(name)]
    return {
        "status": "ok" if not missing else "degraded",
        "app": "RunoffPulse Ireland",
        "version": __version__,
        "time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "live_feeds_enabled": get_settings().live_enabled,
        "missing_datasets": missing,
    }


# ------------------------------------------------------------------------------------- stations
@app.get("/api/stations")
def stations(
    station_type: list[str] | None = Query(None, description="e.g. RIVER_STATION, TRANSITIONAL_STATION"),
    in_catchment: bool | None = Query(None, description="Only stations inside (true) / outside (false) the WFD catchment polygon"),
    q: str | None = Query(None, max_length=100, description="Case-insensitive name or ID search"),
    ds: DataStore = Depends(store),
) -> dict:
    layer = ds.geojson("monitoring_stations.geojson")
    features = layer["features"]
    if station_type:
        wanted = {s.upper() for s in station_type}
        features = [f for f in features if f["properties"].get("StationType") in wanted]
    if in_catchment is not None:
        features = [f for f in features if f["properties"].get("in_study_catchment") is in_catchment]
    if q:
        needle = q.lower()
        features = [
            f
            for f in features
            if needle in (f["properties"].get("StationName") or "").lower()
            or needle in (f["properties"].get("StationID") or "").lower()
        ]
    types: dict[str, int] = {}
    for f in layer["features"]:
        t = f["properties"].get("StationType") or "UNKNOWN"
        types[t] = types.get(t, 0) + 1
    return _feature_collection(
        features,
        meta={**_layer_meta(ds, "monitoring_stations.geojson"), "station_types": types, "returned": len(features)},
    )


@app.get("/api/stations/{station_id}")
def station_detail(station_id: str, ds: DataStore = Depends(store)) -> dict:
    layer = ds.geojson("monitoring_stations.geojson")
    match = next((f for f in layer["features"] if f["properties"].get("StationID") == station_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found in the study area")
    lon, lat = match["geometry"]["coordinates"]
    props = match["properties"]

    nearby_gauges = []
    seen: set[str] = set()
    for f in opw_latest()["features"]:
        p = f["properties"]
        if p["station_number"] in seen:
            continue
        d = haversine_km(lon, lat, *f["geometry"]["coordinates"])
        if d <= 5:
            seen.add(p["station_number"])
            nearby_gauges.append({"station_number": p["station_number"], "station_name": p["station_name"],
                                  "distance_km": round(d, 2), "url": p["station_url"]})
    nearby_gauges.sort(key=lambda g: g["distance_km"])

    nearby_bathing = []
    for f in ds.features_or_empty("bathing_locations.geojson"):
        d = haversine_km(lon, lat, *f["geometry"]["coordinates"])
        if d <= 5:
            nearby_bathing.append({**f["properties"], "distance_km": round(d, 2)})
    nearby_bathing.sort(key=lambda b: b["distance_km"])

    wb = props.get("WBWFDWISECODE")
    return {
        "station": match,
        "observations": [],
        "observations_note": "EPA chemistry/ecology results for this station are not connected to RunoffPulse "
        "yet (no open machine-readable API was identified). No values are shown rather than estimates.",
        "links": {
            "catchments_ie_waterbody": f"https://www.catchments.ie/data/#/waterbody/{wb}" if wb else None,
            "epa_geoportal": "https://gis.epa.ie/EPAMaps/Water",
        },
        "nearby_hydrometric_gauges": nearby_gauges[:5],
        "nearby_bathing_waters": nearby_bathing[:5],
        "proximity_note": "Nearby features are selected by straight-line distance (<= 5 km). Proximity does "
        "not establish hydrological connectivity.",
    }


# ------------------------------------------------------------------------------- spatial layers
@app.get("/api/rivers")
def rivers(ds: DataStore = Depends(store)) -> dict:
    layer = ds.geojson("rivers.geojson")
    return _feature_collection(layer["features"], meta=_layer_meta(ds, "rivers.geojson"))


@app.get("/api/catchment")
def catchment(ds: DataStore = Depends(store)) -> dict:
    return {
        "catchment": ds.geojson("catchment.geojson"),
        "subcatchments": ds.json_or("subcatchments.geojson", {"type": "FeatureCollection", "features": []}),
        "study_area_bbox": STUDY_AREA_BBOX.as_list(),
        "catchment_id": STUDY_CATCHMENT_ID,
        "catchment_name": STUDY_CATCHMENT_NAME,
    }


@app.get("/api/waterbodies")
def waterbodies(ds: DataStore = Depends(store)) -> dict:
    layer = ds.geojson("waterbodies.geojson")
    return _feature_collection(layer["features"], meta=_layer_meta(ds, "waterbodies.geojson"))


@app.get("/api/hydrometric")
def hydrometric(ds: DataStore = Depends(store)) -> dict:
    latest = opw_latest()
    features = []
    for f in latest["features"]:
        p = dict(f["properties"])
        p["excluded_from_screening"] = EXCLUDED_GAUGES.get(p["station_number"])
        features.append({**f, "properties": p})
    return _feature_collection(
        features,
        meta={
            "mode": latest["mode"],
            "retrieved_at": latest["retrieved_at"],
            "error": latest["error"],
            "source": "OPW waterlevel.ie",
            "data_status": "REAL_OBSERVATION",
            "note": "Provisional real-time readings, not quality-controlled.",
        },
    )


@app.get("/api/hydrometric/{station_number}/series")
def hydrometric_series(station_number: str, ds: DataStore = Depends(store)) -> dict:
    if not station_number.isdigit() or len(station_number) > 6:
        raise HTTPException(status_code=422, detail="station_number must be numeric")
    payload = ds.json_or(f"opw_series/{station_number}_0001.json", None)
    if payload is None:
        raise HTTPException(status_code=404, detail="No level series acquired for this station")
    return {**payload, "data_status": "REAL_OBSERVATION", "parameter": "Water level (sensor 0001)"}


# ------------------------------------------------------------------------------------- rainfall
def _parse_range(start: date | None, end: date | None, default_days: int, max_days: int | None = None) -> tuple[date, date]:
    end = end or datetime.now(timezone.utc).date()
    start = start or end - timedelta(days=default_days)
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    if max_days and (end - start).days > max_days:
        raise HTTPException(status_code=422, detail=f"range too long for this resolution (max {max_days} days)")
    return start, end


@app.get("/api/rainfall")
def rainfall(
    start: date | None = None,
    end: date | None = None,
    resolution: str = Query("daily", pattern="^(daily|hourly)$"),
    ds: DataStore = Depends(store),
) -> dict:
    live = met_latest_hourly()
    hourly = combined_hourly(ds, live.get("frame"))
    now = datetime.now(timezone.utc)
    if resolution == "daily":
        start_d, end_d = _parse_range(start, end, default_days=90)
        records = daily_series(ds, hourly, start_d, end_d)
    else:
        start_d, end_d = _parse_range(start, end, default_days=7, max_days=31)
        lo = datetime.combine(start_d, datetime.min.time(), timezone.utc)
        hi = datetime.combine(end_d + timedelta(days=1), datetime.min.time(), timezone.utc)
        sub = hourly[(hourly["datetime_utc"] > lo) & (hourly["datetime_utc"] <= hi)]
        records = [
            {
                "datetime_utc": t.isoformat().replace("+00:00", "Z"),
                "rain_mm": None if v != v else float(v),
                "source": s,
            }
            for t, v, s in zip(sub["datetime_utc"], sub["rain_mm"], sub["source"])
        ]
    latest = latest_observation(hourly, now)
    manifest = ds.manifest().get("datasets", {})
    return {
        "station": STATION,
        "resolution": resolution,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "unit": "mm",
        "data_status": "REAL_OBSERVATION",
        "records": records,
        "latest_observation": None
        if latest is None
        else {
            "datetime_utc": latest["datetime_utc"].isoformat().replace("+00:00", "Z"),
            "rain_mm": None if latest["rain_mm"] != latest["rain_mm"] else float(latest["rain_mm"]),
            "source": latest["source"],
            "age_hours": round((now - latest["datetime_utc"].to_pydatetime()).total_seconds() / 3600, 1),
        },
        "windows": {
            "last_24h": window_stats(hourly, now, 24).as_dict(),
            "last_48h": window_stats(hourly, now, 48).as_dict(),
        },
        "live_feed": {"mode": live.get("mode"), "retrieved_at": live.get("retrieved_at"), "error": live.get("error")},
        "archive_periods": {
            key: manifest[key].get("period") for key in ("met_rainfall_daily", "met_rainfall_hourly", "met_rainfall_recent") if key in manifest
        },
        "notes": [
            "Daily values: Met Éireann quality-controlled climate archive (00-24 UTC).",
            "After the archive ends, daily totals are computed only for days with all 24 hourly reports; "
            "incomplete days are shown with a null total, never as zero.",
            "Latest hourly reports are provisional and are superseded by the archive when it is published.",
        ],
    }


# -------------------------------------------------------------------------------- water quality
@app.get("/api/water-quality")
def water_quality(
    station: str | None = Query(None, description="Bathing water beach_id"),
    indicator: str | None = Query(None, description="'E. coli' or 'Intestinal enterococci'"),
    start: date | None = None,
    end: date | None = None,
    unit: str | None = None,
    limit: int = Query(2000, ge=1, le=10000),
    ds: DataStore = Depends(store),
) -> dict:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    df = ds.bathing_measurements()
    if station:
        df = df[df["beach_id"] == station]
    if indicator:
        df = df[df["indicator"].str.lower() == indicator.lower()]
    if unit:
        df = df[df["unit"] == unit]
    if start:
        df = df[df["result_date"] >= start]
    if end:
        df = df[df["result_date"] <= end]
    df = df.sort_values(["result_date", "beach_id", "indicator"])
    total = len(df)
    df = df.tail(limit)
    records = [
        {
            "station_id": r.beach_id,
            "station_name": r.beach_name,
            "observed_date": r.result_date.isoformat() if r.result_date else None,
            "measurement": r.indicator,
            "value": None if r.value != r.value else float(r.value),
            "value_raw": r.value_raw,
            "qualifier": r.qualifier or None,
            "unit": r.unit,
            "sample_status": r.sample_water_quality_status or None,
            "source": "EPA Bathing Water API",
            "data_status": "REAL_OBSERVATION",
        }
        for r in df.itertuples()
    ]
    beaches = [
        {**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
        for f in ds.features_or_empty("bathing_locations.geojson")
    ]
    all_df = ds.bathing_measurements()
    latest_by_beach = (
        all_df.dropna(subset=["result_date"]).groupby("beach_id")["result_date"].max().to_dict() if not all_df.empty else {}
    )
    for b in beaches:
        last = latest_by_beach.get(b["beach_id"])
        b["latest_sample_date"] = last.isoformat() if last else None

    temps = [
        {**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
        for f in opw_latest()["features"]
        if f["properties"]["sensor_ref"] == "0002"
    ]
    return {
        "records": records,
        "total_matching": total,
        "returned": len(records),
        "stations": beaches,
        "indicators": sorted(all_df["indicator"].unique().tolist()) if not all_df.empty else [],
        "units": sorted(all_df["unit"].unique().tolist()) if not all_df.empty else [],
        "river_water_temperature": temps,
        "not_connected": [
            {
                "measurement": "Nitrate, ortho-phosphate, ammonia, dissolved oxygen, chlorophyll, turbidity",
                "reason": "EPA river/estuary chemistry results are not exposed through an open API identified "
                "for this prototype (catchments.ie offers manual downloads). No values are estimated.",
            }
        ],
        "notes": [
            "Bathing water samples are taken during the bathing season (about June to mid-September).",
            "Values like '<10' are censored results below the laboratory reporting limit; the qualifier is preserved.",
            "Unit is count per 100 ml as reported by EPA (the API does not state cfu or MPN).",
        ],
    }


# ----------------------------------------------------------------------------------------- risk
def _parse_as_of(as_of: str | None) -> datetime | None:
    if not as_of:
        return None
    try:
        if len(as_of) == 10:
            parsed = datetime.combine(date.fromisoformat(as_of), datetime.max.time().replace(microsecond=0), timezone.utc)
        else:
            parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="as_of must be an ISO date or datetime")
    now = datetime.now(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        if len(as_of) == 10 and parsed.date() == now.date():
            return None
        raise HTTPException(status_code=422, detail="as_of cannot be in the future (no forecasting is performed)")
    return parsed


def get_risk(ds: DataStore, as_of: datetime | None) -> dict:
    key = as_of.isoformat() if as_of else "current"
    with _risk_lock:
        hit = _risk_cache.get(key)
        if hit and time.monotonic() - hit[0] < RISK_CACHE_SECONDS:
            return hit[1]
    result = run_screening(ds, as_of)
    with _risk_lock:
        _risk_cache[key] = (time.monotonic(), result)
    return result


@app.get("/api/risk")
def risk(
    as_of: str | None = Query(None, description="ISO date/datetime for historical replay; omit for current"),
    ds: DataStore = Depends(store),
) -> dict:
    return get_risk(ds, _parse_as_of(as_of))


# ---------------------------------------------------------------------------------- aquaculture
@app.get("/api/aquaculture")
def aquaculture(ds: DataStore = Depends(store)) -> dict:
    shellfish = ds.json_or("shellfish_waters.geojson", None)
    screening = get_risk(ds, None)
    by_id = {a["area_id"]: a for a in screening["areas"]}
    stations = ds.features_or_empty("monitoring_stations.geojson")
    station_geoms = [(f, Point(*f["geometry"]["coordinates"])) for f in stations]

    areas = []
    for f in (shellfish or {"features": []})["features"]:
        props = f["properties"]
        geom = shape(f["geometry"])
        near = []
        for sf, pt in station_geoms:
            d_deg = geom.distance(pt)
            if d_deg <= 0.03:  # ~2-3 km
                near.append(
                    {
                        "StationID": sf["properties"]["StationID"],
                        "StationName": sf["properties"]["StationName"],
                        "StationType": sf["properties"]["StationType"],
                        "inside_area": d_deg == 0,
                        "approx_distance_km": round(d_deg * 85, 1),
                    }
                )
        near.sort(key=lambda s: s["approx_distance_km"])
        areas.append(
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    **props,
                    "screening": by_id.get(props["area_id"]),
                    "nearby_monitoring_stations": near[:12],
                    "official_advisory_status": "NOT_CONNECTED",
                },
            }
        )

    production = ds.json_or("production_areas.geojson", None)
    return {
        "shellfish_waters": _feature_collection(areas, meta=_layer_meta(ds, "shellfish_waters.geojson") if shellfish else {}),
        "shellfish_waters_available": shellfish is not None,
        "production_areas": {
            "available": production is not None,
            "features": production["features"] if production else [],
            "note": "SFPA classified bivalve mollusc production areas (harvest classes A/B/C) are not yet loaded. "
            "Place an authoritative GeoJSON at backend/data/production_areas.geojson to display it here."
            if production is None
            else "Loaded from backend/data/production_areas.geojson",
        },
        "official_advisories": {
            "status": "NOT_CONNECTED",
            "message": "No authoritative shellfish advisory feed is connected. RunoffPulse never infers closures. "
            "Check the Sea-Fisheries Protection Authority (sfpa.ie) and Marine Institute HABs/biotoxin "
            "bulletins for official harvesting status.",
            "sources": [
                {"name": "Sea-Fisheries Protection Authority (SFPA)", "url": "https://www.sfpa.ie/"},
                {"name": "Marine Institute HABs & biotoxin monitoring", "url": "https://www.marine.ie/site-area/data-services/interactive-maps/harmful-algal-blooms-and-biotoxin-monitoring"},
            ],
        },
        "screening_as_of": screening["as_of"],
        "disclaimer": "Designated shellfish waters (WFD Register of Protected Areas) are shown for situational "
        "awareness. Screening results are software indicators and do not declare any area safe or unsafe.",
    }


# ----------------------------------------------------------------------------- ML predictions
@app.get("/api/predictions")
def predictions(
    day: date | None = Query(None, alias="date", description="Prediction date (default: today, UTC)"),
    ds: DataStore = Depends(store),
) -> dict:
    today = datetime.now(timezone.utc).date()
    day = day or today
    if day > today:
        raise HTTPException(status_code=422, detail="date cannot be in the future (no weather forecast is used)")
    try:
        live_frame = met_latest_hourly().get("frame") if (today - day).days <= 2 else None
        return predict_for_date(ds, day, live_frame)
    except ModelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.get("/api/model")
def model_info(ds: DataStore = Depends(store)) -> dict:
    try:
        return model_card(ds)
    except ModelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.get("/api/model/backtest")
def model_backtest(ds: DataStore = Depends(store)) -> dict:
    """Out-of-sample (leave-one-year-out) predictions vs observed outcomes, for the study-area beaches."""
    path = ds.path("models/bathing_backtest.csv")
    if not path.exists():
        raise HTTPException(status_code=503, detail="No backtest available. Run scripts/train_bathing_model.py.")
    df = pd.read_csv(path)
    study = {f["properties"]["beach_id"] for f in ds.features_or_empty("bathing_locations.geojson")}
    df = df[df["beach_id"].isin(study)].sort_values("date")
    return {
        "records": [
            {"date": r.date, "beach_id": r.beach_id, "beach_name": r.beach_name, "observed_elevated": bool(r.y),
             "p_out_of_sample": float(r.p_out_of_sample), "rain_d1_mm": None if r.raw_rain_d1 != r.raw_rain_d1 else float(r.raw_rain_d1)}
            for r in df.itertuples()
        ],
        "note": "Each probability comes from a model trained without that sample's year (leave-one-year-out).",
    }


# --------------------------------------------------------------------------------------- alerts
@app.get("/api/alerts")
def alerts(ds: DataStore = Depends(store)) -> dict:
    screening = get_risk(ds, None)
    screening_alerts = [
        {
            "type": "SCREENING_ALERT",
            "issued_by": "RunoffPulse software (not an official warning)",
            "area_id": a["area_id"],
            "area_name": a["name"],
            "classification": a["classification"],
            "score": a["score"],
            "evidence": a["evidence"],
            "next_step": a["next_step"],
            "calculated_at": a["calculated_at"],
        }
        for a in screening["areas"]
        if a["classification"] in ("POTENTIAL_RUNOFF_RISK", "ELEVATED_SCREENING_RISK")
    ]
    raw = ds.json_or("bathing_alerts.json", {"alerts": [], "retrieved_at": None})
    beach_ids = {f["properties"]["beach_id"] for f in ds.features_or_empty("bathing_locations.geojson")}
    official = [a for a in raw["alerts"] if a.get("beach_id") in beach_ids]
    return {
        "screening_alerts": screening_alerts,
        "official_alerts": official,
        "official_alerts_retrieved_at": raw.get("retrieved_at"),
        "official_alerts_national_count": len(raw["alerts"]),
        "delivery": {
            "external_notifications": "DISABLED",
            "note": "Alert delivery (email/SMS) is not enabled: it requires an authoritative trigger, "
            "recipient configuration and a delivery provider.",
        },
    }


# -------------------------------------------------------------------------------------- reports
@app.get("/api/reports", response_model=ReportPage)
def list_reports(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> ReportPage:
    items, total = report_store().list(page, page_size)
    return ReportPage(items=items, page=page, page_size=page_size, total=total)


@app.post("/api/reports", status_code=201)
async def create_report(
    category: ReportCategory = Form(...),
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    observed_at: str = Form(...),
    photo: UploadFile | None = File(None),
) -> dict:
    try:
        report = ReportCreate(
            category=category, description=description, latitude=latitude, longitude=longitude, observed_at=observed_at
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": e["loc"], "msg": e["msg"]} for e in error.errors(include_url=False, include_context=False)],
        )

    data: bytes | None = None
    content_type: str | None = None
    if photo is not None and photo.filename:
        limit = get_settings().max_upload_bytes
        data = await photo.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"Photo exceeds {limit // (1024 * 1024)} MB limit")
        content_type = sniff_image_type(data)
        if content_type is None:
            raise HTTPException(status_code=415, detail="Photo must be a JPEG, PNG or WebP image")
    created = report_store().create(report, data, content_type)
    return created.model_dump()


@app.get("/api/reports/{report_id}/photo")
def report_photo(report_id: str) -> FileResponse:
    if not report_id.isalnum() or len(report_id) != 32:
        raise HTTPException(status_code=404, detail="Not found")
    found = report_store().photo(report_id)
    if not found:
        raise HTTPException(status_code=404, detail="Not found")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"X-Content-Type-Options": "nosniff"})


# -------------------------------------------------------------------------------------- sources
@app.get("/api/sources")
def sources(ds: DataStore = Depends(store)) -> dict:
    manifest = ds.manifest()
    opw = opw_latest()
    met = met_latest_hourly()
    return {
        "datasets": sorted(manifest.get("datasets", {}).values(), key=lambda d: d["id"]),
        "manifest_updated_at": manifest.get("updated_at"),
        "live_feeds": [
            {"id": "opw_live", "title": "OPW waterlevel.ie latest readings", "mode": opw["mode"],
             "retrieved_at": opw["retrieved_at"], "error": opw["error"], "data_status": "REAL_OBSERVATION"},
            {"id": "met_live", "title": "Met Éireann latest hourly reports (Cork)", "mode": met["mode"],
             "retrieved_at": met["retrieved_at"], "error": met["error"], "data_status": "REAL_OBSERVATION"},
        ],
        "derived": [
            {"id": "runoff_screening", "title": "Runoff-risk screening", "data_status": "MODELLED_INDICATOR",
             "notes": "Computed on request from the datasets above. See docs/RISK_METHOD.md."},
            {"id": "ml_bathing_model", "title": "ML prediction: elevated bathing-water bacteria",
             "data_status": "MODELLED_INDICATOR",
             "notes": "Logistic regression trained on EPA bathing results and Met Éireann rainfall; "
             "leave-one-year-out validated. See /api/model."},
            {"id": "citizen_reports", "title": "Citizen reports", "data_status": "CITIZEN_REPORTED_UNVERIFIED",
             "notes": "Stored locally in SQLite; unverified until reviewed."},
        ],
        "not_connected": [
            {"title": "EPA river/estuarine chemistry time series (nutrients, DO, etc.)",
             "reason": "No open API identified; manual downloads via catchments.ie."},
            {"title": "SFPA classified shellfish production areas and harvest status",
             "reason": "Not integrated; interface accepts backend/data/production_areas.geojson."},
            {"title": "Marine Institute HABs/biotoxin results", "reason": "Not integrated in the MVP."},
            {"title": "Sentinel-2/Sentinel-3 satellite products",
             "reason": "Planned; requires a documented, validated coastal-water method."},
            {"title": "Tides and currents", "reason": "Not modelled; no transport or dilution claims are made."},
        ],
        "data_status_definitions": DATA_STATUS_DEFINITIONS,
    }


DATA_STATUS_DEFINITIONS = {
    "REAL_OBSERVATION": "A measured value from an authoritative monitoring source, with its observation time.",
    "REAL_STATION_LOCATION": "The real location and attributes of a monitoring station; implies no measured result.",
    "REAL_REFERENCE_GEOMETRY": "Official reference geometry (e.g. catchment boundaries).",
    "OFFICIAL_ASSESSMENT": "An official multi-year classification (e.g. WFD status, bathing water class).",
    "OFFICIAL_DESIGNATION": "An official legal/protected-area designation.",
    "OFFICIAL_ADVISORY": "An advisory or alert published by the responsible authority.",
    "MODELLED_INDICATOR": "Computed by RunoffPulse from observations using a documented method; not an observation.",
    "SIMULATED_DEMO": "Synthetic data for demonstration only (none is currently used).",
    "CITIZEN_REPORTED_UNVERIFIED": "Submitted by a member of the public and not yet reviewed.",
}


# -------------------------------------------------------------------------------------- summary
@app.get("/api/summary")
def summary(ds: DataStore = Depends(store)) -> dict:
    stations_layer = ds.json_or("monitoring_stations.geojson", {"features": []})
    station_types: dict[str, int] = {}
    for f in stations_layer["features"]:
        t = f["properties"].get("StationType") or "UNKNOWN"
        station_types[t] = station_types.get(t, 0) + 1

    live = met_latest_hourly()
    hourly = combined_hourly(ds, live.get("frame"))
    now = datetime.now(timezone.utc)
    latest = latest_observation(hourly, now)
    w24 = window_stats(hourly, now, 24)

    wq_count = 0
    wq_latest = None
    try:
        df = ds.bathing_measurements()
        usable = df[df["value"].notna()]
        wq_count = int(len(usable))
        wq_latest = max(usable["result_date"]).isoformat() if wq_count else None
    except DatasetMissing:
        pass

    screening = get_risk(ds, None)
    opw = opw_latest()
    opw_stations = {f["properties"]["station_number"] for f in opw["features"]}
    _, report_total = report_store().list(1, 1)
    manifest = ds.manifest().get("datasets", {})

    return {
        "monitoring_stations": {"total": len(stations_layer["features"]), "by_type": station_types,
                                "data_status": "REAL_STATION_LOCATION"},
        "latest_rainfall": None
        if latest is None
        else {
            "datetime_utc": latest["datetime_utc"].isoformat().replace("+00:00", "Z"),
            "rain_mm": None if latest["rain_mm"] != latest["rain_mm"] else float(latest["rain_mm"]),
            "age_hours": round((now - latest["datetime_utc"].to_pydatetime()).total_seconds() / 3600, 1),
            "last_24h": w24.as_dict(),
            "station": STATION["name"],
            "data_status": "REAL_OBSERVATION",
        },
        "water_quality": {"usable_observations": wq_count, "latest_sample_date": wq_latest,
                          "data_status": "REAL_OBSERVATION"},
        "screening": {
            "counts": screening["counts"],
            "areas_flagged": sum(screening["counts"].get(k, 0) for k in ("POTENTIAL_RUNOFF_RISK", "ELEVATED_SCREENING_RISK")),
            "definition": "Areas flagged = POTENTIAL_RUNOFF_RISK or ELEVATED_SCREENING_RISK from the screening "
            "heuristic. A flag means 'review warranted', not confirmed pollution.",
            "calculated_at": screening["calculated_at"],
            "data_status": "MODELLED_INDICATOR",
        },
        "hydrometric": {"stations": len(opw_stations), "mode": opw["mode"], "retrieved_at": opw["retrieved_at"]},
        "citizen_reports": {"total": report_total, "data_status": "CITIZEN_REPORTED_UNVERIFIED"},
        "freshness": [
            {"id": d["id"], "title": d["title"], "retrieved_at": d.get("retrieved_at"), "period": d.get("period"),
             "data_status": d.get("data_status")}
            for d in sorted(manifest.values(), key=lambda d: d["id"])
        ],
    }
