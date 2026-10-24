from datetime import datetime, timezone

import pytest

from app.risk_engine import (
    ELEVATED_SCREENING_RISK,
    INSUFFICIENT_DATA,
    NO_ELEVATED_SIGNAL,
    POTENTIAL_RUNOFF_RISK,
    AreaInput,
    GaugeInput,
    RainfallInput,
    WaterQualitySample,
    screen_area,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def rain(total48=1.0, pct=0.4, max_hourly=0.5, coverage=1.0, age=1.0):
    return RainfallInput("Test gauge", total48 / 2, total48, coverage, max_hourly, "2026-10-17T11:00Z", age, pct)


def gauge(pct, age=0.5, number="19001"):
    return GaugeInput(number, "G", 1.0, "2026-10-17T11:30Z", age, pct, 2880)


def area(linked=True, rainfall=None, gauges=(), wq=()):
    return AreaInput("A1", "Area", "Designated shellfish water", linked, "test basis",
                     rainfall, list(gauges), list(wq), {"adjacent_hydrometric_area": "X"})


def wq_sample(status, age_days=2):
    return WaterQualitySample("B1", "Beach", "2026-10-15", age_days, status, "100", "10", 3.0)


def test_unlinked_area_is_insufficient_even_with_heavy_rain():
    result = screen_area(area(linked=False, rainfall=rain(60, 0.999, 10)), NOW)
    assert result["classification"] == INSUFFICIENT_DATA
    assert result["score"] is None
    assert any("Not fed by a monitored river catchment" in m for m in result["missing_inputs"])
    assert result["summary"].startswith("Not assessed")


@pytest.mark.parametrize(
    "rainfall, message",
    [
        (None, "No rainfall observations"),
        (rain(coverage=0.5), "Rainfall record incomplete"),
        (rain(age=12), "h old"),
    ],
)
def test_missing_or_stale_rainfall_is_insufficient(rainfall, message):
    result = screen_area(area(rainfall=rainfall, gauges=[gauge(0.9), gauge(0.9)]), NOW)
    assert result["classification"] == INSUFFICIENT_DATA
    assert result["confidence"] == "NONE"
    assert any(message in m for m in result["missing_inputs"])


def test_dry_conditions_give_no_elevated_signal():
    result = screen_area(area(rainfall=rain(), gauges=[gauge(0.4), gauge(0.5)]), NOW)
    assert result["classification"] == NO_ELEVATED_SIGNAL
    assert result["summary"] == "Little rain (1 mm in 2 days) and rivers at normal levels. Runoff is unlikely to be elevated."
    assert result["score"] == 0.0
    assert result["confidence"] == "MEDIUM"  # rainfall + river, no water quality


def test_rainfall_alone_is_capped_at_potential():
    result = screen_area(area(rainfall=rain(80, 0.999, 9)), NOW)
    assert result["components"]["river_response"] is None
    assert result["score"] >= 0.6
    assert result["classification"] == POTENTIAL_RUNOFF_RISK
    assert result["confidence"] == "LOW"
    assert any("capped" in e for e in result["evidence"])


def test_corroborated_heavy_rain_is_elevated():
    result = screen_area(area(rainfall=rain(40, 0.99, 6), gauges=[gauge(0.97), gauge(0.95, number="19020")]), NOW)
    assert result["classification"] == ELEVATED_SCREENING_RISK
    assert result["components"]["river_response"] > 0.5
    assert result["is_official_advisory"] is False
    assert result["data_status"] == "MODELLED_INDICATOR"


def test_moderate_rain_gives_potential():
    # rainfall (0.8 - 0.5) / 0.5 = 0.6; river median 0.45 -> (0.5*0.6 + 0.35*0.45) / 0.85 = 0.538
    result = screen_area(area(rainfall=rain(12, 0.8, 2.5), gauges=[gauge(0.7), gauge(0.75)]), NOW)
    assert result["classification"] == POTENTIAL_RUNOFF_RISK
    assert result["score"] == pytest.approx(0.538, abs=0.001)


def test_stale_or_too_few_gauges_are_not_used():
    result = screen_area(area(rainfall=rain(), gauges=[gauge(0.99), gauge(0.99, age=10)]), NOW)
    assert result["components"]["river_response"] is None
    assert any("River response unavailable" in m for m in result["missing_inputs"])


def test_poor_bathing_sample_counts_and_old_sample_is_ignored():
    recent = screen_area(area(rainfall=rain(), wq=[wq_sample("Poor")]), NOW)
    assert recent["components"]["water_quality"] == 1.0
    old = screen_area(area(rainfall=rain(), wq=[wq_sample("Poor", age_days=30)]), NOW)
    assert old["components"]["water_quality"] is None


def test_score_is_renormalised_over_available_components():
    result = screen_area(area(rainfall=rain(40, 0.99, 6), wq=[wq_sample("Excellent")]), NOW)
    # rainfall 0.98 (w 0.5) and water quality 0.0 (w 0.15) -> 0.49 / 0.65
    assert result["score"] == pytest.approx(0.98 * 0.5 / 0.65, abs=0.01)
    assert result["weights"]["river_response"] == 0.35


def test_result_documents_inputs_and_time():
    result = screen_area(area(rainfall=rain(), gauges=[gauge(0.5), gauge(0.5)]), NOW)
    assert result["calculated_at"] == "2026-10-17T12:00:00Z"
    assert result["inputs"]["rainfall"]["total_48h_mm"] == 1.0
    assert result["next_step"]
    assert result["linkage"] == {"linked": True, "basis": "test basis"}
