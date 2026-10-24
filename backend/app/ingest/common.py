"""Shared acquisition helpers: HTTP with retries, paged WFS requests and the provenance manifest."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.geo import BBox

USER_AGENT = "RunoffPulseIreland/0.1 (environmental decision-support prototype)"
EPA_WFS_URL = "https://gis.epa.ie/geoserver/EPA/ows"
EPA_GEOPORTAL_LICENCE = "CC BY 4.0 (EPA Ireland open data; attribution: Environmental Protection Agency)"
WFS_PAGE_SIZE = 5000


class AcquisitionError(RuntimeError):
    """Raised when an upstream source cannot be retrieved or fails validation."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def get_with_retries(client: httpx.Client, url: str, params: dict | None = None, attempts: int = 3) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response
        except (httpx.HTTPError,) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise AcquisitionError(f"GET {url} failed after {attempts} attempts: {last_error}")


def wfs_get_features(
    client: httpx.Client,
    type_name: str,
    bbox: BBox | None = None,
    cql_filter: str | None = None,
    page_size: int = WFS_PAGE_SIZE,
    max_pages: int = 50,
    sort_by: str | None = None,
) -> dict[str, Any]:
    """Fetch every feature of an EPA WFS layer matching a bbox or CQL filter.

    GeoServer WFS 1.0.0 with srsName=EPSG:4326 returns GeoJSON in longitude, latitude order.
    GeoServer does not accept BBOX and CQL_FILTER together, so a bbox is expressed inside the
    CQL filter when both are given. EPA layers have no primary key, so GeoServer refuses
    startIndex paging unless a sort attribute is supplied: without sort_by a single page is
    requested and the result is rejected if it is smaller than the server's totalFeatures.
    """
    params: dict[str, Any] = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "maxFeatures": page_size,
    }
    if cql_filter and bbox:
        params["CQL_FILTER"] = (
            f"({cql_filter}) AND BBOX(Shape,{bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat},'EPSG:4326')"
        )
    elif cql_filter:
        params["CQL_FILTER"] = cql_filter
    elif bbox:
        params["bbox"] = bbox.as_wfs_param()

    features: list[dict] = []
    total: int | None = None
    if sort_by:
        params["sortBy"] = sort_by
    for page in range(max_pages if sort_by else 1):
        if sort_by:
            params["startIndex"] = page * page_size
        response = get_with_retries(client, EPA_WFS_URL, params=params)
        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            snippet = response.text[:300].replace("\n", " ")
            raise AcquisitionError(f"{type_name}: response was not JSON ({error}): {snippet}") from error
        if payload.get("type") != "FeatureCollection":
            raise AcquisitionError(f"{type_name}: response was not a GeoJSON FeatureCollection")
        batch = payload.get("features") or []
        features.extend(batch)
        total = payload.get("totalFeatures") if isinstance(payload.get("totalFeatures"), int) else total
        if len(batch) < page_size or (total is not None and len(features) >= total):
            break
    else:
        if sort_by:
            raise AcquisitionError(f"{type_name}: exceeded {max_pages} pages; refusing to continue")

    if total is not None and len(features) != total:
        raise AcquisitionError(f"{type_name}: retrieved {len(features)} features but server reported {total}")

    return {"type": "FeatureCollection", "features": features, "totalFeatures": total}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def update_manifest(data_dir: Path, dataset_id: str, entry: dict[str, Any]) -> None:
    """Record provenance for one dataset in data_dir/manifest.json (merging with other entries)."""
    manifest_path = data_dir / "manifest.json"
    manifest: dict[str, Any] = {"datasets": {}}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("datasets", {})[dataset_id] = {"id": dataset_id, **entry}
    manifest["updated_at"] = utc_now_iso()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
