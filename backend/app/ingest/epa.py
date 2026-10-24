"""EPA Ireland GeoServer (WFS) acquisition for the Cork Harbour / River Lee study area."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import Point, mapping, shape

from app.geo import (
    SCREENED_CATCHMENTS,
    STUDY_AREA_BBOX,
    STUDY_CATCHMENT_ID,
    STUDY_CATCHMENT_NAME,
    filter_point_features,
    validate_feature_collection,
)
from app.ingest.common import (
    EPA_GEOPORTAL_LICENCE,
    EPA_WFS_URL,
    AcquisitionError,
    update_manifest,
    utc_now_iso,
    wfs_get_features,
    write_json,
)

SIMPLIFY_TOLERANCE_DEG = 0.00015  # ~10-15 m; keeps map payloads small without visible distortion


def _round_coords(obj: Any, ndigits: int = 6) -> Any:
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, (list, tuple)):
        return [_round_coords(item, ndigits) for item in obj]
    return obj


def _simplified(geometry: dict) -> dict:
    geom = shape(geometry).simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
    out = mapping(geom)
    return {"type": out["type"], "coordinates": _round_coords(out["coordinates"])}


def _collection(name: str, features: list[dict], source_layer: str, retrieved_at: str, **extra: Any) -> dict:
    collection = {
        "type": "FeatureCollection",
        "name": name,
        "source": "EPA Ireland GeoServer WFS",
        "source_layer": source_layer,
        "source_url": EPA_WFS_URL,
        "retrieved_at": retrieved_at,
        "crs": "EPSG:4326",
        "licence": EPA_GEOPORTAL_LICENCE,
        **extra,
        "features": features,
    }
    problems = validate_feature_collection(collection)
    if problems:
        raise AcquisitionError(f"{name}: GeoJSON validation failed: {problems[:5]}")
    return collection


def _write_layer(
    data_dir: Path,
    dataset_id: str,
    filename: str,
    collection: dict,
    title: str,
    data_status: str,
    notes: str,
) -> int:
    write_json(data_dir / filename, collection)
    update_manifest(
        data_dir,
        dataset_id,
        {
            "title": title,
            "file": filename,
            "publisher": "Environmental Protection Agency (EPA) Ireland",
            "source_url": f"{EPA_WFS_URL}?service=WFS&request=GetFeature&typeName={collection['source_layer']}",
            "licence": EPA_GEOPORTAL_LICENCE,
            "retrieved_at": collection["retrieved_at"],
            "crs": "EPSG:4326",
            "record_count": len(collection["features"]),
            "data_status": data_status,
            "notes": notes,
        },
    )
    return len(collection["features"])


def download_catchment(client: httpx.Client, data_dir: Path) -> dict:
    retrieved_at = utc_now_iso()
    raw = wfs_get_features(client, "EPA:WFD_Catchments", cql_filter=f"Catchment_Id='{STUDY_CATCHMENT_ID}'")
    if len(raw["features"]) != 1:
        raise AcquisitionError(f"Expected exactly one catchment {STUDY_CATCHMENT_ID}, got {len(raw['features'])}")
    feature = raw["features"][0]
    feature = {"type": "Feature", "geometry": _simplified(feature["geometry"]), "properties": feature["properties"]}
    collection = _collection("study_catchment", [feature], "EPA:WFD_Catchments", retrieved_at)
    _write_layer(
        data_dir,
        "epa_catchment",
        "catchment.geojson",
        collection,
        f"WFD Catchment {STUDY_CATCHMENT_ID}: {STUDY_CATCHMENT_NAME}",
        "REAL_REFERENCE_GEOMETRY",
        "Official EPA WFD catchment polygon used to define the study area and catchment membership. "
        "Geometry simplified (~10-15 m tolerance) for web display.",
    )

    sub_raw = wfs_get_features(client, "EPA:WFD_SubCatchments", cql_filter=f"Catchment_Id='{STUDY_CATCHMENT_ID}'")
    subs = [
        {"type": "Feature", "geometry": _simplified(f["geometry"]), "properties": f["properties"]}
        for f in sub_raw["features"]
        if f.get("geometry")
    ]
    sub_collection = _collection("study_subcatchments", subs, "EPA:WFD_SubCatchments", retrieved_at)
    _write_layer(
        data_dir,
        "epa_subcatchments",
        "subcatchments.geojson",
        sub_collection,
        f"WFD sub-catchments within Catchment {STUDY_CATCHMENT_ID}",
        "REAL_REFERENCE_GEOMETRY",
        "Official EPA WFD sub-catchment polygons. Geometry simplified for web display.",
    )
    return collection


def download_screened_catchments(client: httpx.Client, data_dir: Path) -> int:
    """Polygons of every catchment whose river gauges feed the screening (Blackwater, Lee, Bandon)."""
    retrieved_at = utc_now_iso()
    ids = ",".join(f"'{cid}'" for cid in SCREENED_CATCHMENTS)
    raw = wfs_get_features(client, "EPA:WFD_Catchments", cql_filter=f"Catchment_Id IN ({ids})")
    features = []
    for f in raw["features"]:
        geom = shape(f["geometry"]).simplify(0.001, preserve_topology=True)
        out = mapping(geom)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": out["type"], "coordinates": _round_coords(out["coordinates"], 5)},
                "properties": {"Catchment_Id": f["properties"]["Catchment_Id"], "Name": f["properties"]["Name"],
                               "Area_km2": f["properties"].get("Area_km2")},
            }
        )
    found = {f["properties"]["Catchment_Id"] for f in features}
    if found != set(SCREENED_CATCHMENTS):
        raise AcquisitionError(f"Expected catchments {sorted(SCREENED_CATCHMENTS)}, got {sorted(found)}")
    collection = _collection("screened_catchments", features, "EPA:WFD_Catchments", retrieved_at)
    return _write_layer(
        data_dir,
        "epa_screened_catchments",
        "screened_catchments.geojson",
        collection,
        "WFD catchments connected for screening (Blackwater, Lee, Bandon-Ilen)",
        "REAL_REFERENCE_GEOMETRY",
        "Official EPA catchment polygons used to assign OPW river gauges to the catchment that feeds each "
        "coastal area. Simplified (~100 m) because they are used for gauge assignment, not display.",
    )


def download_stations(client: httpx.Client, data_dir: Path, catchment: dict) -> int:
    retrieved_at = utc_now_iso()
    raw = wfs_get_features(client, "EPA:MON_WaterStations", bbox=STUDY_AREA_BBOX, page_size=1000, sort_by="StationID")
    features, rejected = filter_point_features(raw["features"], STUDY_AREA_BBOX, id_field="StationID")

    catchment_geom = shape(catchment["features"][0]["geometry"]).buffer(0)
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        props["in_study_catchment"] = bool(catchment_geom.covers(Point(lon, lat)))
        props["data_source"] = "EPA Ireland"
        props["data_status"] = "REAL_STATION_LOCATION"
        props["retrieved_at"] = retrieved_at

    features.sort(key=lambda f: f["properties"]["StationID"])
    collection = _collection(
        "cork_lee_epa_monitoring_stations",
        features,
        "EPA:MON_WaterStations",
        retrieved_at,
        study_area_bbox=STUDY_AREA_BBOX.as_list(),
        server_feature_count_in_bbox=raw.get("totalFeatures"),
        rejected_counts=rejected,
    )
    count = _write_layer(
        data_dir,
        "epa_monitoring_stations",
        "monitoring_stations.geojson",
        collection,
        "EPA water monitoring station locations (Cork Harbour / River Lee study area)",
        "REAL_STATION_LOCATION",
        "Station locations and attributes only. A station location does not imply a measured "
        "result or pollution. Server-side BBOX filter, then local validation: MultiPoint geometries "
        "normalised to Point, duplicate StationIDs and invalid coordinates rejected. "
        f"in_study_catchment is a point-in-polygon test against WFD Catchment {STUDY_CATCHMENT_ID}. "
        f"Rejections: {rejected or 'none'}.",
    )
    return count


def _status_lookup(client: httpx.Client, layer: str) -> dict[str, dict]:
    raw = wfs_get_features(client, layer, bbox=STUDY_AREA_BBOX)
    return {
        f["properties"].get("European_Code"): {
            "wfd_status": f["properties"].get("Status"),
            "wfd_status_period": f["properties"].get("Period_for_WFD_Status"),
        }
        for f in raw["features"]
    }


def download_waterbodies(client: httpx.Client, data_dir: Path) -> dict[str, dict]:
    """Transitional (estuarine) and coastal waterbodies with latest official WFD status."""
    retrieved_at = utc_now_iso()
    keep = [
        "EU_CD",
        "NAME",
        "URL",
        "CATEGORY",
        "TYPE",
        "AdjacentHydrometricArea",
        "LOCALAUTHORITY",
        "AreaKm2",
    ]
    features: list[dict] = []
    for layer, status_layer, category in (
        ("EPA:WFD_TRANSITIONALWATERBODIES_CYCLE3", "EPA:TWB_WFD_LatestStatus", "Transitional"),
        ("EPA:WFD_COASTALWATERBODIES_CYCLE3", "EPA:CWB_WFD_LatestStatus", "Coastal"),
    ):
        raw = wfs_get_features(client, layer, bbox=STUDY_AREA_BBOX)
        statuses = _status_lookup(client, status_layer)
        for f in raw["features"]:
            if not f.get("geometry"):
                continue
            props = {k: f["properties"].get(k) for k in keep}
            props["waterbody_category"] = category
            props.update(statuses.get(props["EU_CD"], {"wfd_status": None, "wfd_status_period": None}))
            props["data_status"] = "OFFICIAL_ASSESSMENT"
            features.append({"type": "Feature", "geometry": _simplified(f["geometry"]), "properties": props})

    collection = _collection(
        "transitional_coastal_waterbodies",
        features,
        "EPA:WFD_TRANSITIONALWATERBODIES_CYCLE3 + EPA:WFD_COASTALWATERBODIES_CYCLE3",
        retrieved_at,
    )
    _write_layer(
        data_dir,
        "epa_waterbodies",
        "waterbodies.geojson",
        collection,
        "WFD transitional and coastal waterbodies with latest WFD status",
        "OFFICIAL_ASSESSMENT",
        "Official WFD (Cycle 3) waterbody polygons joined by EU code to the EPA latest-status "
        "layers (TWB/CWB_WFD_LatestStatus). WFD status is a multi-year ecological assessment, "
        "not a current measurement. AdjacentHydrometricArea is the EPA attribute used for "
        "catchment-to-waterbody linkage.",
    )
    return {f["properties"]["EU_CD"]: f["properties"] for f in features}


def download_rivers(client: httpx.Client, data_dir: Path, catchment: dict) -> int:
    retrieved_at = utc_now_iso()
    raw = wfs_get_features(client, "EPA:RWB_WFD_LatestStatus", bbox=STUDY_AREA_BBOX)
    catchment_geom = shape(catchment["features"][0]["geometry"]).buffer(0.002)
    features = []
    for f in raw["features"]:
        if not f.get("geometry"):
            continue
        geom = shape(f["geometry"])
        if not catchment_geom.intersects(geom):
            continue
        props = f["properties"]
        features.append(
            {
                "type": "Feature",
                "geometry": _simplified(f["geometry"]),
                "properties": {
                    "European_Code": props.get("European_Code"),
                    "Name": props.get("Name"),
                    "wfd_status": props.get("Status"),
                    "wfd_status_period": props.get("Period_for_WFD_Status"),
                    "data_status": "OFFICIAL_ASSESSMENT",
                },
            }
        )
    collection = _collection("lee_river_waterbodies", features, "EPA:RWB_WFD_LatestStatus", retrieved_at)
    return _write_layer(
        data_dir,
        "epa_rivers",
        "rivers.geojson",
        collection,
        f"WFD river waterbodies in Catchment {STUDY_CATCHMENT_ID} with latest WFD status",
        "OFFICIAL_ASSESSMENT",
        "River waterbody lines intersecting the WFD catchment polygon (20 m buffer). Status is the "
        "official multi-year WFD ecological status, not a current measurement.",
    )


def download_shellfish_waters(client: httpx.Client, data_dir: Path, waterbodies: dict[str, dict]) -> int:
    retrieved_at = utc_now_iso()
    raw = wfs_get_features(client, "EPA:WFD_RPA_SHELLFISH", bbox=STUDY_AREA_BBOX)
    features = []
    for f in raw["features"]:
        if not f.get("geometry"):
            continue
        props = f["properties"]
        parent = waterbodies.get(props.get("WB_CD"), {})
        adjacent_area = parent.get("AdjacentHydrometricArea")
        features.append(
            {
                "type": "Feature",
                "geometry": _simplified(f["geometry"]),
                "properties": {
                    "area_id": props.get("EU_PA_Code"),
                    "name": props.get("NAME"),
                    "designation": "Shellfish Waters (WFD Register of Protected Areas)",
                    "parent_waterbody_code": props.get("WB_CD"),
                    "parent_waterbody_name": parent.get("NAME"),
                    "parent_waterbody_wfd_status": parent.get("wfd_status"),
                    "parent_waterbody_wfd_status_period": parent.get("wfd_status_period"),
                    "adjacent_hydrometric_area": adjacent_area,
                    "linked_to_study_catchment": adjacent_area == STUDY_CATCHMENT_NAME,
                    "data_status": "OFFICIAL_DESIGNATION",
                },
            }
        )
    collection = _collection("designated_shellfish_waters", features, "EPA:WFD_RPA_SHELLFISH", retrieved_at)
    return _write_layer(
        data_dir,
        "epa_shellfish_waters",
        "shellfish_waters.geojson",
        collection,
        "Designated Shellfish Waters (WFD Register of Protected Areas)",
        "OFFICIAL_DESIGNATION",
        "Designated shellfish-water protected areas. These are NOT the SFPA classified bivalve "
        "production areas and carry no harvesting classification, biotoxin or closure status. "
        "Catchment linkage uses the parent waterbody's EPA AdjacentHydrometricArea attribute.",
    )


def download_pressures(client: httpx.Client, data_dir: Path, catchment: dict) -> int:
    """Significant-pressure designations (agriculture, urban waste water, urban runoff) as context."""
    retrieved_at = utc_now_iso()
    catchment_geom = shape(catchment["features"][0]["geometry"]).buffer(0.002)
    layers = {
        "Agriculture": ["EPA:WFD_RWB_Pressures_Agriculture", "EPA:WFD_LTCWB_Pressures_Agriculture"],
        "Urban waste water": [
            "EPA:WFD_RWB_Pressures_Urban_Waste_Water",
            "EPA:WFD_LTCWB_Pressures_UrbanWasteWater",
        ],
        "Urban run-off": ["EPA:WFD_RWB_Pressures_Urban_Run_off", "EPA:WFD_LTCWB_Pressures_UrbanRunoff"],
    }
    records = []
    for category, layer_names in layers.items():
        for layer in layer_names:
            raw = wfs_get_features(client, layer, bbox=STUDY_AREA_BBOX)
            for f in raw["features"]:
                if not f.get("geometry"):
                    continue
                in_catchment = catchment_geom.intersects(shape(f["geometry"]))
                props = f["properties"]
                records.append(
                    {
                        "waterbody_code": props.get("Code"),
                        "waterbody_name": props.get("Name"),
                        "waterbody_type": props.get("WBType"),
                        "pressure_category": category,
                        "source_layer": layer,
                        "intersects_study_catchment": in_catchment,
                    }
                )
    payload = {
        "name": "wfd_significant_pressures",
        "source": "EPA Ireland GeoServer WFS",
        "retrieved_at": retrieved_at,
        "licence": EPA_GEOPORTAL_LICENCE,
        "data_status": "OFFICIAL_ASSESSMENT",
        "records": records,
    }
    write_json(data_dir / "pressures.json", payload)
    update_manifest(
        data_dir,
        "epa_pressures",
        {
            "title": "WFD significant pressures on waterbodies (agriculture, urban waste water, urban run-off)",
            "file": "pressures.json",
            "publisher": "Environmental Protection Agency (EPA) Ireland",
            "source_url": EPA_WFS_URL,
            "licence": EPA_GEOPORTAL_LICENCE,
            "retrieved_at": retrieved_at,
            "crs": "n/a (attribute table; geometry used only for catchment intersection)",
            "record_count": len(records),
            "data_status": "OFFICIAL_ASSESSMENT",
            "notes": "WFD Cycle 3 significant-pressure designations. Context only: a designated pressure "
            "is not evidence that a specific event was caused by that pressure.",
        },
    )
    return len(records)


def acquire_epa(client: httpx.Client, data_dir: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    catchment = download_catchment(client, data_dir)
    results["catchment"] = 1
    results["screened_catchments"] = download_screened_catchments(client, data_dir)
    results["stations"] = download_stations(client, data_dir, catchment)
    waterbodies = download_waterbodies(client, data_dir)
    results["waterbodies"] = len(waterbodies)
    results["rivers"] = download_rivers(client, data_dir, catchment)
    results["shellfish_waters"] = download_shellfish_waters(client, data_dir, waterbodies)
    results["pressures"] = download_pressures(client, data_dir, catchment)
    return results
