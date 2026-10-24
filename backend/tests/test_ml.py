import json
import math
from datetime import date, timedelta

import pytest

from app import main
from app.ml.features import build_features, is_elevated, rain_window
from app.ml.predict import band_for, score

CARD = {
    "model_id": "bathing-elevated-bacteria",
    "version": "test",
    "trained_at": "2026-10-17T00:00:00Z",
    "task": "t",
    "target": {"definition": "E. coli > 250 OR intestinal enterococci > 100 per 100 ml", "basis": "EU BWD"},
    "algorithm": "logistic regression",
    "evaluation": "leave-one-year-out",
    "bands": [
        {"band": "BELOW_TYPICAL", "min": 0.0, "max": 0.03},
        {"band": "TYPICAL", "min": 0.03, "max": 0.08},
        {"band": "ABOVE_TYPICAL", "min": 0.08, "max": 1.0},
    ],
    "deployed_variant": "recent",
    "deployment_rule": "r",
    "limitations": ["l"],
    "variants": {
        "recent": {
            "rain_features": ["rain_d1"],
            "numeric_features": ["rain_d1", "season_sin", "season_cos"],
            "standardisation": {"mean": {"rain_d1": 0.5, "season_sin": 0.0, "season_cos": 0.0},
                                "std": {"rain_d1": 1.0, "season_sin": 1.0, "season_cos": 1.0}},
            "intercept": -3.0,
            "coefficients": {"rain_d1": 0.8, "season_sin": 0.0, "season_cos": 0.0},
            "beach_coefficients": {"IESWBWC060_0000_0100": 0.5},
            "beach_names": {"IESWBWC060_0000_0100": "Test Beach"},
            "regularisation_C": 0.3,
            "training": {"samples": 10, "events": 1, "event_rate": 0.1, "beaches": 1,
                         "period": ["2015-01-01", "2026-09-01"], "months": list(range(1, 13))},
            "evaluation": {}, "calibration": [], "top_vs_bottom_quintile_ratio": 8.0,
            "bands_out_of_sample": [], "per_year_auc": {},
        }
    },
}


def test_target_definition():
    assert is_elevated(251, 0) is True
    assert is_elevated(250, 100) is False
    assert is_elevated(None, 101) is True
    assert is_elevated(None, None) is None


def test_rain_features_use_only_previous_complete_days():
    day = date(2025, 8, 15)
    daily = {day: 99.0, day - timedelta(days=1): 4.0}
    feats, raw = build_features(daily, day, ["rain_d1"])
    assert raw == {"rain_d1": 4.0}  # same-day rain (99 mm) is never used
    assert feats["rain_d1"] == pytest.approx(math.log1p(4.0))
    assert rain_window(daily, day, 2, 3) is None  # missing days are not treated as dry
    assert build_features(daily, day, ["rain_d1", "rain_d2_3"])[0] is None


def test_score_matches_logistic_formula_and_explains_drivers():
    variant = CARD["variants"]["recent"]
    feats = {"rain_d1": 1.5, "season_sin": 0.0, "season_cos": 0.0}
    p, drivers, beach_effect, known = score(variant, feats, "IESWBWC060_0000_0100")
    expected = 1 / (1 + math.exp(-(-3.0 + 0.8 * 1.0 + 0.5)))
    assert p == pytest.approx(expected)
    assert known and beach_effect == 0.5
    assert drivers[0]["factor"] == "Rain yesterday"
    p_unknown, _, effect, known = score(variant, feats, "UNSEEN")
    assert not known and effect == 0.0 and p_unknown < p


def test_band_edges():
    assert band_for(CARD, 0.0) == "BELOW_TYPICAL"
    assert band_for(CARD, 0.03) == "TYPICAL"
    assert band_for(CARD, 0.5) == "ABOVE_TYPICAL"
    assert band_for(CARD, 1.0) == "ABOVE_TYPICAL"


@pytest.fixture
def ml_client(client, data_dir):
    (data_dir / "models").mkdir(exist_ok=True)
    (data_dir / "models" / "bathing_model.json").write_text(json.dumps(CARD))
    return client


def test_predictions_endpoint(ml_client, now):
    day = (now - timedelta(days=200)).date()  # inside the fixture daily archive
    body = ml_client.get("/api/predictions", params={"date": day.isoformat()}).json()
    assert body["status"] == "OK"
    assert body["data_status"] == "MODELLED_INDICATOR"
    assert "Not an official" in body["disclaimer"]
    pred = body["predictions"][0]
    assert 0 < pred["probability"] < 1
    assert pred["band"] in {"BELOW_TYPICAL", "TYPICAL", "ABOVE_TYPICAL"}
    assert pred["drivers"]


def test_predictions_unavailable_without_rainfall(ml_client):
    body = ml_client.get("/api/predictions", params={"date": "2016-07-01"}).json()
    assert body["status"] == "UNAVAILABLE"
    assert all(p["probability"] is None for p in body["predictions"])


def test_predictions_reject_future_and_missing_model(ml_client, client, data_dir, now):
    future = (now + timedelta(days=3)).date().isoformat()
    assert ml_client.get("/api/predictions", params={"date": future}).status_code == 422
    (data_dir / "models" / "bathing_model.json").unlink()
    response = client.get("/api/predictions")
    assert response.status_code == 503
    assert "train_bathing_model.py" in response.json()["detail"]


def test_model_card_hides_raw_parameters(ml_client):
    body = ml_client.get("/api/model").json()
    variant = body["variants"]["recent"]
    assert "standardisation" not in variant and "beach_coefficients" not in variant
    assert variant["beach_effects"][0]["beach_name"] == "Test Beach"
    assert main.app  # app imported with ML routes
