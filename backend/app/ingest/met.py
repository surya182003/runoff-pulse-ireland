"""Met Éireann rainfall acquisition for Cork Airport (station 3904).

Sources (CC BY 4.0, Met Éireann):
* Daily climate archive:  https://clidata.met.ie/cli/climate_data/webdata/dly3904.csv
* Hourly climate archive: https://clidata.met.ie/cli/climate_data/webdata/hly3904.csv
* Latest hourly reports:  https://prodapi.met.ie/observations/cork/{yesterday,today}

The archive files lag by a few weeks. The latest-report API covers only yesterday and today,
so every acquisition run appends its snapshot to rainfall_recent_hourly.csv; the recent window
therefore fills in over time rather than being back-filled with invented values.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import httpx

from app.ingest.common import AcquisitionError, get_with_retries, update_manifest, utc_now_iso

MET_LICENCE = "CC BY 4.0 (Met Éireann; data has been modified: filtered to the study period)"
STATION_ID = "3904"
STATION_NAME = "Cork Airport"
STATION_LON, STATION_LAT = -8.486, 51.847
DAILY_URL = f"https://clidata.met.ie/cli/climate_data/webdata/dly{STATION_ID}.csv"
HOURLY_URL = f"https://clidata.met.ie/cli/climate_data/webdata/hly{STATION_ID}.csv"
LATEST_URLS = {
    "yesterday": "https://prodapi.met.ie/observations/cork/yesterday",
    "today": "https://prodapi.met.ie/observations/cork/today",
}
DAILY_START = date(2015, 1, 1)
HOURLY_START = date(2023, 1, 1)
IRISH_TZ = ZoneInfo("Europe/Dublin")

DAILY_FIELDS = ["station_id", "station_name", "date", "rain_mm", "rain_indicator"]
HOURLY_FIELDS = ["station_id", "station_name", "datetime_utc", "rain_mm", "rain_indicator", "source"]


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_met_climate_csv(text: str) -> tuple[list[str], list[list[str]]]:
    """Split a Met Éireann climate CSV into (header, rows), skipping the descriptive preamble."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("date,"):
            reader = csv.reader(lines[index:])
            header = next(reader)
            return header, [row for row in reader if row and row[0].strip()]
    raise AcquisitionError("Met Éireann CSV header (date,...) not found")


def parse_daily_rows(header: list[str], rows: Iterable[list[str]], start: date) -> list[dict[str, Any]]:
    # In dly files "rain" is preceded by its indicator column (irrd/"ind").
    rain_idx = header.index("rain")
    ind_idx = rain_idx - 1
    out = []
    for row in rows:
        try:
            day = datetime.strptime(row[0].strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        if day < start:
            continue
        out.append(
            {
                "station_id": STATION_ID,
                "station_name": STATION_NAME,
                "date": day.isoformat(),
                "rain_mm": _parse_float(row[rain_idx]) if rain_idx < len(row) else None,
                "rain_indicator": row[ind_idx].strip() if ind_idx < len(row) else None,
            }
        )
    return out


def parse_hourly_rows(header: list[str], rows: Iterable[list[str]], start: date) -> list[dict[str, Any]]:
    rain_idx = header.index("rain")
    ind_idx = rain_idx - 1
    out = []
    for row in rows:
        try:
            moment = datetime.strptime(row[0].strip(), "%d-%b-%Y %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if moment.date() < start:
            continue
        out.append(
            {
                "station_id": STATION_ID,
                "station_name": STATION_NAME,
                "datetime_utc": moment.strftime("%Y-%m-%dT%H:%MZ"),
                "rain_mm": _parse_float(row[rain_idx]) if rain_idx < len(row) else None,
                "rain_indicator": row[ind_idx].strip() if ind_idx < len(row) else None,
                "source": "met_eireann_hourly_archive",
            }
        )
    return out


def parse_latest_observations(payload: list[dict]) -> list[dict[str, Any]]:
    """Parse prodapi latest-report rows.

    reportTime/date are Irish local clock time (as shown on met.ie latest reports); they are
    converted to UTC with the Europe/Dublin zone so they align with the UTC archive.
    """
    out = []
    for item in payload:
        try:
            local = datetime.strptime(f"{item['date']} {item['reportTime']}", "%d-%m-%Y %H:%M")
        except (KeyError, ValueError):
            continue
        moment = local.replace(tzinfo=IRISH_TZ).astimezone(timezone.utc)
        out.append(
            {
                "station_id": STATION_ID,
                "station_name": STATION_NAME,
                "datetime_utc": moment.strftime("%Y-%m-%dT%H:%MZ"),
                "rain_mm": _parse_float(str(item.get("rainfall", ""))),
                "rain_indicator": "",
                "source": "met_eireann_latest_reports",
            }
        )
    return out


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def merge_recent(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge by timestamp; newer snapshots replace earlier values for the same hour."""
    merged = {row["datetime_utc"]: row for row in existing}
    for row in new:
        merged[row["datetime_utc"]] = row
    return [merged[key] for key in sorted(merged)]


def acquire_met(client: httpx.Client, data_dir: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    base_entry = {
        "publisher": "Met Éireann",
        "licence": MET_LICENCE,
        "crs": "EPSG:4326 (station point)",
        "data_status": "REAL_OBSERVATION",
        "station": {"id": STATION_ID, "name": STATION_NAME, "lon": STATION_LON, "lat": STATION_LAT},
    }

    retrieved_at = utc_now_iso()
    header, rows = parse_met_climate_csv(get_with_retries(client, DAILY_URL).text)
    daily = parse_daily_rows(header, rows, DAILY_START)
    if not daily:
        raise AcquisitionError("No daily rainfall rows parsed")
    _write_csv(data_dir / "rainfall_daily.csv", DAILY_FIELDS, daily)
    update_manifest(
        data_dir,
        "met_rainfall_daily",
        {
            **base_entry,
            "title": "Daily rainfall, Cork Airport (Met Éireann climate archive)",
            "file": "rainfall_daily.csv",
            "source_url": DAILY_URL,
            "retrieved_at": retrieved_at,
            "record_count": len(daily),
            "period": [daily[0]["date"], daily[-1]["date"]],
            "notes": "Precipitation amount (mm), 00-24 UTC. Filtered from 2015-01-01. Blank values kept "
            "as null. Indicator codes: https://www.met.ie/cms/assets/uploads/2018/05/KeyDly_Rain.txt",
        },
    )
    results["rainfall_daily"] = len(daily)

    retrieved_at = utc_now_iso()
    header, rows = parse_met_climate_csv(get_with_retries(client, HOURLY_URL).text)
    hourly = parse_hourly_rows(header, rows, HOURLY_START)
    _write_csv(data_dir / "rainfall_hourly.csv", HOURLY_FIELDS, hourly)
    update_manifest(
        data_dir,
        "met_rainfall_hourly",
        {
            **base_entry,
            "title": "Hourly rainfall, Cork Airport (Met Éireann climate archive)",
            "file": "rainfall_hourly.csv",
            "source_url": HOURLY_URL,
            "retrieved_at": retrieved_at,
            "record_count": len(hourly),
            "period": [hourly[0]["datetime_utc"], hourly[-1]["datetime_utc"]] if hourly else None,
            "notes": "Hourly precipitation (mm), UTC. Filtered from 2023-01-01. Indicator codes: "
            "https://www.met.ie/cms/assets/uploads/2018/05/KeyHourly.txt",
        },
    )
    results["rainfall_hourly"] = len(hourly)

    retrieved_at = utc_now_iso()
    latest: list[dict[str, Any]] = []
    for url in LATEST_URLS.values():
        response = get_with_retries(client, url)
        payload = response.json()
        if not isinstance(payload, list):
            raise AcquisitionError(f"Unexpected latest-observation payload from {url}")
        latest.extend(parse_latest_observations(payload))
    recent_path = data_dir / "rainfall_recent_hourly.csv"
    recent = merge_recent(_read_csv(recent_path), latest)
    _write_csv(recent_path, HOURLY_FIELDS, recent)
    update_manifest(
        data_dir,
        "met_rainfall_recent",
        {
            **base_entry,
            "title": "Latest hourly reports, Cork Airport (Met Éireann)",
            "file": "rainfall_recent_hourly.csv",
            "source_url": ", ".join(LATEST_URLS.values()),
            "retrieved_at": retrieved_at,
            "record_count": len(recent),
            "period": [recent[0]["datetime_utc"], recent[-1]["datetime_utc"]] if recent else None,
            "notes": "Snapshots of the yesterday/today latest-report feed, appended on every acquisition "
            "run. Report times are Irish local time converted to UTC. These are provisional, "
            "unquality-controlled reports; the climate archive supersedes them when available. "
            "Gaps between the archive end and the first snapshot are left as gaps.",
        },
    )
    results["rainfall_recent_hourly"] = len(recent)
    return results
