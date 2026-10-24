from datetime import date

import pytest

from app.geo import (
    BBox,
    filter_point_features,
    irish_grid_to_lonlat,
    normalize_point_geometry,
    validate_feature_collection,
)
from app.ingest.bathing import parse_count
from app.ingest.met import merge_recent, parse_daily_rows, parse_latest_observations, parse_met_climate_csv
from app.ingest.opw import parse_latest

CORK = BBox(-9.42, 51.70, -7.78, 52.11)


def feature(geometry, **props):
    return {"type": "Feature", "geometry": geometry, "properties": props}


class TestGeometryNormalisation:
    def test_point_is_kept(self):
        geom, note = normalize_point_geometry({"type": "Point", "coordinates": [-8.47, 51.89]})
        assert geom == {"type": "Point", "coordinates": [-8.47, 51.89]}
        assert note is None

    def test_single_member_multipoint_becomes_point(self):
        geom, note = normalize_point_geometry({"type": "MultiPoint", "coordinates": [[-8.47, 51.89]]})
        assert geom["type"] == "Point" and geom["coordinates"] == [-8.47, 51.89]
        assert note is None

    def test_multi_member_multipoint_is_flagged(self):
        geom, note = normalize_point_geometry({"type": "MultiPoint", "coordinates": [[-8.47, 51.89], [-8.40, 51.80]]})
        assert geom["coordinates"] == [-8.47, 51.89]
        assert "2 members" in note

    @pytest.mark.parametrize(
        "geometry, reason",
        [
            (None, "missing geometry"),
            ({"type": "MultiPoint", "coordinates": []}, "empty MultiPoint"),
            ({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "unsupported"),
            ({"type": "Point", "coordinates": [51.89, -8.47]}, "latitude, longitude order"),
            ({"type": "Point", "coordinates": [250655, 436203]}, "outside the plausible range"),
            ({"type": "Point", "coordinates": [None, 51.9]}, "outside the plausible range"),
        ],
    )
    def test_invalid_geometries_are_rejected_with_reason(self, geometry, reason):
        geom, note = normalize_point_geometry(geometry)
        assert geom is None
        assert reason in note


class TestStudyAreaFiltering:
    def test_filters_bbox_and_deduplicates(self):
        features = [
            feature({"type": "MultiPoint", "coordinates": [[-8.47, 51.89]]}, StationID="A"),  # Cork city
            feature({"type": "MultiPoint", "coordinates": [[-9.20, 51.85]]}, StationID="B"),  # upper Lee
            feature({"type": "MultiPoint", "coordinates": [[-6.26, 53.35]]}, StationID="C"),  # Dublin
            feature({"type": "MultiPoint", "coordinates": [[-8.47, 51.89]]}, StationID="A"),  # duplicate
            feature({"type": "Point", "coordinates": [-8.3, 51.8]}, StationID=None),
            feature(None, StationID="D"),
        ]
        kept, rejected = filter_point_features(features, CORK, id_field="StationID")
        assert [f["properties"]["StationID"] for f in kept] == ["A", "B"]
        assert all(f["geometry"]["type"] == "Point" for f in kept)
        assert rejected == {
            "outside study area": 1,
            "duplicate StationID": 1,
            "missing StationID": 1,
            "missing geometry": 1,
        }

    def test_original_study_box_bug_is_fixed(self):
        # Inchigeelagh on the upper Lee (-9.13) is inside WFD Catchment 19 and must be included.
        assert CORK.contains(-9.13, 51.84)


class TestGeoJSONValidation:
    def test_valid_collection(self):
        fc = {"type": "FeatureCollection", "features": [feature({"type": "Point", "coordinates": [-8.4, 51.9]})]}
        assert validate_feature_collection(fc) == []

    def test_detects_problems(self):
        fc = {
            "type": "FeatureCollection",
            "features": [
                feature(None),
                feature({"type": "Point", "coordinates": [51.9, -8.4]}),
                {"type": "NotAFeature"},
            ],
        }
        problems = validate_feature_collection(fc)
        assert len(problems) == 3
        assert validate_feature_collection({"type": "Feature"}) == ["not a FeatureCollection"]


def test_irish_grid_conversion_matches_known_location():
    # Loughrea Lake bathing area, Irish Grid E 162397 N 215167 -> about 53.19 N, 8.56 W.
    lon, lat = irish_grid_to_lonlat(162397, 215167)
    assert lon == pytest.approx(-8.563, abs=0.01)
    assert lat == pytest.approx(53.186, abs=0.01)
    assert irish_grid_to_lonlat(None, 1) is None


MET_CSV = """Station Name: CORK AIRPORT
Station Height: 155 M

  rain     - Precipitation Amount (mm)

date,ind,maxtp,ind,mintp,igmin,gmin,ind,rain,cbl
29-sep-2014,0,17.6,0,12.8,0,9.3,0,7.5,986.0
29-sep-2026,0,17.6,0,12.8,0,9.3,0,7.5,986.0
30-sep-2026,0,16.1,0,8.8,0,9.6,0, ,987.2
"""


def test_met_daily_csv_parsing_keeps_missing_as_null():
    header, rows = parse_met_climate_csv(MET_CSV)
    parsed = parse_daily_rows(header, rows, date(2015, 1, 1))
    assert [r["date"] for r in parsed] == ["2026-09-29", "2026-09-30"]
    assert parsed[0]["rain_mm"] == 7.5
    assert parsed[1]["rain_mm"] is None


def test_met_latest_reports_convert_irish_local_time_to_utc():
    rows = parse_latest_observations(
        [{"date": "17-10-2026", "reportTime": "11:00", "rainfall": " 0.4 "}, {"date": "bad"}]
    )
    assert rows == [
        {
            "station_id": "3904",
            "station_name": "Cork Airport",
            "datetime_utc": "2026-10-17T10:00Z",  # IST (UTC+1) in October
            "rain_mm": 0.4,
            "rain_indicator": "",
            "source": "met_eireann_latest_reports",
        }
    ]


def test_merge_recent_replaces_same_hour_and_sorts():
    old = [{"datetime_utc": "2026-10-17T10:00Z", "rain_mm": "0.1"}, {"datetime_utc": "2026-10-17T08:00Z", "rain_mm": "0"}]
    new = [{"datetime_utc": "2026-10-17T10:00Z", "rain_mm": "0.3"}]
    merged = merge_recent(old, new)
    assert [r["datetime_utc"] for r in merged] == ["2026-10-17T08:00Z", "2026-10-17T10:00Z"]
    assert merged[1]["rain_mm"] == "0.3"


@pytest.mark.parametrize(
    "raw, expected",
    [("272", (272.0, None)), ("<10", (10.0, "<")), (">24196", (24196.0, ">")), ("", (None, None)), (None, (None, None)), ("n/a", (None, None))],
)
def test_bathing_count_parsing(raw, expected):
    assert parse_count(raw) == expected


def test_opw_parse_latest_excludes_voltage_and_outside_area():
    payload = {
        "features": [
            {"geometry": {"type": "Point", "coordinates": [-8.6, 51.85]},
             "properties": {"station_ref": "0000019001", "station_name": "Ballea", "sensor_ref": "0001", "value": "0.42",
                            "datetime": "2026-10-17T10:15:00Z", "url": "/0000019001/0001/"}},
            {"geometry": {"type": "Point", "coordinates": [-8.6, 51.85]},
             "properties": {"station_ref": "0000019001", "station_name": "Ballea", "sensor_ref": "0003", "value": "12.5"}},
            {"geometry": {"type": "Point", "coordinates": [-6.3, 53.3]},
             "properties": {"station_ref": "0000009001", "station_name": "Dublin", "sensor_ref": "0001", "value": "1"}},
        ]
    }
    catchment = {"type": "Polygon", "coordinates": [[[-8.8, 51.8], [-8.2, 51.8], [-8.2, 52.0], [-8.8, 52.0], [-8.8, 51.8]]]}
    features = parse_latest(payload, catchment)
    assert len(features) == 1
    props = features[0]["properties"]
    assert props["station_number"] == "19001"
    assert props["value"] == 0.42
    assert props["in_study_catchment"] is True
    assert props["data_status"] == "REAL_OBSERVATION"
