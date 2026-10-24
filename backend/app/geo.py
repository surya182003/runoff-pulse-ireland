"""Pure geospatial helpers: geometry normalisation, coordinate validation and study-area filtering.

All output geometry is GeoJSON in EPSG:4326 with [longitude, latitude] order (RFC 7946).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from shapely.geometry import Point, shape

# Plausibility envelope for the island of Ireland plus near-shore waters. Used to detect
# swapped axes or projected coordinates that were mislabelled as EPSG:4326.
IRELAND_LON_RANGE = (-11.0, -5.0)
IRELAND_LAT_RANGE = (51.0, 55.6)


@dataclass(frozen=True)
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    def as_wfs_param(self) -> str:
        return f"{self.min_lon},{self.min_lat},{self.max_lon},{self.max_lat},EPSG:4326"

    def as_list(self) -> list[float]:
        return [self.min_lon, self.min_lat, self.max_lon, self.max_lat]


# Study area: the extent of EPA WFD Catchment 19 "Lee, Cork Harbour and Youghal Bay"
# (-9.358, 51.762, -7.847, 52.051 in EPSG:4326, retrieved from EPA:WFD_Catchments),
# expanded by ~0.06 deg so that harbour-mouth and near-shore coastal stations are included.
# This box is only a retrieval envelope; catchment membership is decided with the polygon.
STUDY_AREA_BBOX = BBox(-9.42, 51.70, -7.78, 52.11)
STUDY_CATCHMENT_ID = "19"
STUDY_CATCHMENT_NAME = "Lee, Cork Harbour and Youghal Bay"
# Catchments whose river gauges are connected for screening. Coastal areas are linked to one of these
# through the EPA "AdjacentHydrometricArea" attribute of their waterbody.
SCREENED_CATCHMENTS = {
    "18": "Blackwater (Munster)",
    "19": STUDY_CATCHMENT_NAME,
    "20": "Bandon-Ilen",
}


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_plausible_irish_lonlat(lon: Any, lat: Any) -> bool:
    if not (is_finite_number(lon) and is_finite_number(lat)):
        return False
    return (
        IRELAND_LON_RANGE[0] <= lon <= IRELAND_LON_RANGE[1]
        and IRELAND_LAT_RANGE[0] <= lat <= IRELAND_LAT_RANGE[1]
    )


def normalize_point_geometry(geometry: dict | None) -> tuple[dict | None, str | None]:
    """Return (Point geometry, note) for a Point or MultiPoint geometry.

    EPA WFS publishes monitoring stations as single-member MultiPoints. A MultiPoint with
    one member is converted losslessly to a Point. A MultiPoint with several members is
    represented by its first member and the returned note says so. Anything invalid
    returns (None, reason) so the caller can count and report the rejection.
    """
    if not geometry or not isinstance(geometry, dict):
        return None, "missing geometry"

    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Point":
        candidate = coords
        note = None
    elif gtype == "MultiPoint":
        if not coords:
            return None, "empty MultiPoint"
        candidate = coords[0]
        note = None if len(coords) == 1 else f"MultiPoint with {len(coords)} members; first used"
    else:
        return None, f"unsupported geometry type {gtype!r}"

    if not isinstance(candidate, (list, tuple)) or len(candidate) < 2:
        return None, "malformed coordinates"

    lon, lat = candidate[0], candidate[1]
    if not is_plausible_irish_lonlat(lon, lat):
        if is_plausible_irish_lonlat(lat, lon):
            return None, "coordinates appear to be in latitude, longitude order"
        return None, "coordinates outside the plausible range for Ireland"

    return {"type": "Point", "coordinates": [round(float(lon), 7), round(float(lat), 7)]}, note


def filter_point_features(
    features: Iterable[dict],
    bbox: BBox,
    id_field: str | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Normalise point features, keep those inside bbox and drop duplicate identifiers.

    Returns the kept features and a dict of rejection counts keyed by reason.
    """
    kept: list[dict] = []
    seen_ids: set[str] = set()
    rejected: dict[str, int] = {}

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for feature in features:
        geometry, note = normalize_point_geometry(feature.get("geometry"))
        if geometry is None:
            reject(note or "invalid geometry")
            continue

        lon, lat = geometry["coordinates"]
        if not bbox.contains(lon, lat):
            reject("outside study area")
            continue

        properties = dict(feature.get("properties") or {})
        if id_field:
            identifier = properties.get(id_field)
            if identifier in (None, ""):
                reject(f"missing {id_field}")
                continue
            if identifier in seen_ids:
                reject(f"duplicate {id_field}")
                continue
            seen_ids.add(identifier)

        if note:
            properties["geometry_note"] = note
        kept.append({"type": "Feature", "geometry": geometry, "properties": properties})

    return kept, rejected


def validate_feature_collection(collection: Any) -> list[str]:
    """Return a list of problems with a GeoJSON FeatureCollection (empty when valid)."""
    problems: list[str] = []
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        return ["not a FeatureCollection"]
    features = collection.get("features")
    if not isinstance(features, list):
        return ["features is not a list"]
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            problems.append(f"feature {index}: not a Feature")
            continue
        geometry = feature.get("geometry")
        if geometry is None:
            problems.append(f"feature {index}: null geometry")
            continue
        try:
            geom = shape(geometry)
        except Exception as error:  # shapely raises several error types
            problems.append(f"feature {index}: unreadable geometry ({error})")
            continue
        if geom.is_empty:
            problems.append(f"feature {index}: empty geometry")
            continue
        min_lon, min_lat, max_lon, max_lat = geom.bounds
        if not (
            is_plausible_irish_lonlat(min_lon, min_lat) and is_plausible_irish_lonlat(max_lon, max_lat)
        ):
            problems.append(f"feature {index}: coordinates outside Ireland lon/lat envelope")
    return problems


@lru_cache(maxsize=4)
def _to_wgs84(source_crs: str):
    from pyproj import Transformer

    return Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)


def irish_grid_to_lonlat(easting: Any, northing: Any, source_crs: str = "EPSG:29903") -> tuple[float, float] | None:
    """Convert Irish Grid (TM65, EPSG:29903, default) or ITM (EPSG:2157) easting/northing to lon/lat."""
    if not (is_finite_number(easting) and is_finite_number(northing)):
        return None
    lon, lat = _to_wgs84(source_crs).transform(float(easting), float(northing))
    if not is_plausible_irish_lonlat(lon, lat):
        return None
    return round(lon, 7), round(lat, 7)


def point_in_any(lon: float, lat: float, geometries: Iterable[dict]) -> bool:
    point = Point(lon, lat)
    return any(shape(geometry).covers(point) for geometry in geometries)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))
