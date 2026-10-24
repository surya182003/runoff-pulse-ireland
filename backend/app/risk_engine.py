"""Explainable runoff-risk SCREENING engine.

This is a transparent screening heuristic, not a calibrated pollution or transport model.
It answers one question: "do current observations suggest that rainfall-driven runoff from a
linked catchment *may* be elevated for this coastal area, so that a person should review it?"

Method (all thresholds are in ScreeningConfig and are reported with every result)
-------------------------------------------------------------------------------
1. Gatekeeping (necessary inputs). If either is missing -> INSUFFICIENT_DATA:
   a. Catchment linkage: the area's parent waterbody must carry the EPA attribute
      AdjacentHydrometricArea equal to the study catchment. Spatial proximity alone is never
      accepted as linkage.
   b. Recent rainfall: >= min_rain_coverage of hourly values present in the last 48 h and the
      newest value no older than max_rain_age_hours.

2. Components, each normalised to 0..1:
   R  rainfall      = max( max(0, (P48 - 0.5) / 0.5),  clamp((Imax - 2 mm) / 6 mm) )
                      P48  = empirical percentile of the 48 h total among all two-day totals in
                             the Cork Airport daily archive (2015-present)
                      Imax = largest hourly total in the last 24 h
                      -> anything at or below a median two-day total contributes nothing.
   F  river response = median over usable linked gauges of max(0, (Pg - 0.5) / 0.5)
                      Pg = percentile of the gauge's latest level within its own last-30-day
                           15-minute record. Requires >= min_gauges usable gauges.
   W  water quality = worst recent official per-sample bathing-water status within
                      max_wq_age_days: Poor -> 1.0, Sufficient -> 0.5, Good/Excellent -> 0.0.

3. Score S = sum(w_i * c_i) / sum(w_i) over AVAILABLE components only
   (weights: rainfall 0.50, river 0.35, water quality 0.15). Missing components are listed,
   never imputed.

4. Classification:
   S >= 0.60 AND corroborated (F >= 0.5 or W >= 0.5)  -> ELEVATED_SCREENING_RISK
   S >= 0.30                                          -> POTENTIAL_RUNOFF_RISK
   otherwise                                          -> NO_ELEVATED_SIGNAL
   Rainfall alone can therefore never produce ELEVATED_SCREENING_RISK.

5. Confidence = HIGH / MEDIUM / LOW for 3 / 2 / 1 available components.

Why these weights: rainfall is the driver and the only input available for every linked area;
river level is the most direct observed evidence that runoff is actually reaching the
drainage network; bathing-water bacteriology is the closest coastal outcome measure but is
seasonal and sparse, so it is corroborating rather than dominant. The weights and thresholds
are expert-judgement starting points that should be calibrated against historical event and
monitoring records before any operational use.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NO_ELEVATED_SIGNAL = "NO_ELEVATED_SIGNAL"
POTENTIAL_RUNOFF_RISK = "POTENTIAL_RUNOFF_RISK"
ELEVATED_SCREENING_RISK = "ELEVATED_SCREENING_RISK"

ENGINE_VERSION = "screening-heuristic-1.0"

LIMITATIONS = [
    "Screening heuristic only: not a calibrated model, not a prediction of pollutant concentrations, "
    "and not an official public-health, bathing or shellfish-harvesting advisory.",
    "Catchment linkage is at WFD catchment level (EPA AdjacentHydrometricArea attribute). It does not "
    "establish a flow path, travel time or dilution to a specific coastal area.",
    "No tidal, current, mixing or pollutant-transport process is modelled.",
    "Rainfall comes from a single gauge (Cork Airport, 155 m) and may not represent rainfall across the "
    "whole catchment, especially the upper Lee.",
    "OPW water levels are provisional real-time data. Dam-regulated and tidal gauges are excluded.",
    "Bathing-water samples are seasonal (about June to mid-September) and are usually unavailable.",
    "A WFD significant pressure (e.g. agriculture) is context only and is not evidence of the cause of "
    "any event.",
]


@dataclass
class ScreeningConfig:
    min_rain_coverage: float = 0.75
    max_rain_age_hours: float = 6.0
    max_gauge_age_hours: float = 3.0
    min_gauges: int = 2
    max_wq_age_days: int = 7
    weight_rainfall: float = 0.50
    weight_river: float = 0.35
    weight_water_quality: float = 0.15
    potential_threshold: float = 0.30
    elevated_threshold: float = 0.60
    corroboration_threshold: float = 0.50
    intensity_floor_mm: float = 2.0
    intensity_span_mm: float = 6.0


@dataclass
class RainfallInput:
    station_name: str
    total_24h_mm: float | None
    total_48h_mm: float | None
    coverage_48h: float
    max_hourly_24h_mm: float | None
    latest_observation_utc: str | None
    latest_age_hours: float | None
    percentile_48h: float | None
    climatology_years: str | None = None


@dataclass
class GaugeInput:
    station_number: str
    station_name: str
    latest_level_m: float | None
    observed_at: str | None
    age_hours: float | None
    percentile_30d: float | None
    series_points: int
    catchment: str = ""


@dataclass
class WaterQualitySample:
    beach_id: str
    beach_name: str
    sample_date: str
    age_days: int
    sample_status: str | None
    e_coli: str | None
    enterococci: str | None
    distance_km: float | None = None


@dataclass
class AreaInput:
    area_id: str
    name: str
    area_type: str
    linked_to_study_catchment: bool
    linkage_basis: str
    rainfall: RainfallInput | None
    gauges: list[GaugeInput] = field(default_factory=list)
    water_quality: list[WaterQualitySample] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def rainfall_component(rain: RainfallInput, cfg: ScreeningConfig) -> float:
    pct_part = 0.0
    if rain.percentile_48h is not None:
        pct_part = clamp01((rain.percentile_48h - 0.5) / 0.5)
    intensity_part = 0.0
    if rain.max_hourly_24h_mm is not None:
        intensity_part = clamp01((rain.max_hourly_24h_mm - cfg.intensity_floor_mm) / cfg.intensity_span_mm)
    return max(pct_part, intensity_part)


WQ_STATUS_SCORE = {"poor": 1.0, "sufficient": 0.5, "good": 0.0, "excellent": 0.0}


def screen_area(area: AreaInput, calculated_at: datetime, cfg: ScreeningConfig | None = None) -> dict[str, Any]:
    cfg = cfg or ScreeningConfig()
    evidence: list[str] = []
    missing: list[str] = []
    components: dict[str, float | None] = {"rainfall": None, "river_response": None, "water_quality": None}

    # --- Gate 1: linkage -----------------------------------------------------------------
    if not area.linked_to_study_catchment:
        missing.append(
            "Not fed by a monitored river catchment (EPA records this area's catchment as "
            f"'{area.context.get('adjacent_hydrometric_area') or 'unknown'}')."
        )

    # --- Gate 2: rainfall ------------------------------------------------------------------
    rain = area.rainfall
    rain_ok = False
    if rain is None or rain.total_48h_mm is None:
        missing.append("No rainfall observations in the last 48 hours.")
    elif rain.coverage_48h < cfg.min_rain_coverage:
        missing.append(
            f"Rainfall record incomplete: {rain.coverage_48h:.0%} of the last 48 hourly values present "
            f"(minimum {cfg.min_rain_coverage:.0%})."
        )
    elif rain.latest_age_hours is None or rain.latest_age_hours > cfg.max_rain_age_hours:
        missing.append(
            f"Latest rainfall observation is {rain.latest_age_hours:.1f} h old (maximum {cfg.max_rain_age_hours:.0f} h)."
            if rain.latest_age_hours is not None
            else "Rainfall observation time unknown."
        )
    else:
        rain_ok = True
        components["rainfall"] = round(rainfall_component(rain, cfg), 3)
        pct = f", {rain.percentile_48h:.0%} percentile of two-day totals" if rain.percentile_48h is not None else ""
        evidence.append(
            f"{rain.station_name}: {rain.total_48h_mm:.1f} mm in 48 h{pct}; "
            f"{rain.total_24h_mm or 0:.1f} mm in 24 h; max hourly {rain.max_hourly_24h_mm or 0:.1f} mm."
        )

    # --- River response --------------------------------------------------------------------
    usable_gauges = [
        g
        for g in area.gauges
        if g.percentile_30d is not None and g.age_hours is not None and g.age_hours <= cfg.max_gauge_age_hours
    ]
    if area.linked_to_study_catchment:
        if len(usable_gauges) >= cfg.min_gauges:
            parts = [clamp01((g.percentile_30d - 0.5) / 0.5) for g in usable_gauges]
            components["river_response"] = round(float(median(parts)), 3)
            high = [g for g in usable_gauges if g.percentile_30d >= 0.9]
            evidence.append(
                f"{len(usable_gauges)} linked OPW river gauges usable; median level percentile "
                f"{median(g.percentile_30d for g in usable_gauges):.0%} of their last 30 days; "
                f"{len(high)} above their 30-day 90th percentile."
            )
        else:
            missing.append(
                f"River response unavailable: {len(usable_gauges)} usable linked gauges "
                f"(need {cfg.min_gauges}; readings must be <= {cfg.max_gauge_age_hours:.0f} h old with a 30-day record)."
            )

    # --- Water quality ---------------------------------------------------------------------
    recent_wq = [s for s in area.water_quality if 0 <= s.age_days <= cfg.max_wq_age_days]
    scored = [(WQ_STATUS_SCORE.get((s.sample_status or "").strip().lower()), s) for s in recent_wq]
    scored = [(v, s) for v, s in scored if v is not None]
    if scored:
        worst_value, worst = max(scored, key=lambda item: item[0])
        components["water_quality"] = worst_value
        evidence.append(
            f"Bathing water {worst.beach_name} sampled {worst.sample_date}: official sample status "
            f"'{worst.sample_status}' (E. coli {worst.e_coli}, enterococci {worst.enterococci} per 100 ml)."
        )
    else:
        missing.append(
            f"No official bathing-water sample within {cfg.max_wq_age_days} days (sampling is seasonal)."
        )

    weights = {
        "rainfall": cfg.weight_rainfall,
        "river_response": cfg.weight_river,
        "water_quality": cfg.weight_water_quality,
    }
    available = {k: v for k, v in components.items() if v is not None}
    score: float | None = None

    if not area.linked_to_study_catchment or not rain_ok:
        classification = INSUFFICIENT_DATA
    else:
        total_weight = sum(weights[k] for k in available)
        score = round(sum(weights[k] * v for k, v in available.items()) / total_weight, 3)
        corroborated = any(
            (components[k] or 0) >= cfg.corroboration_threshold for k in ("river_response", "water_quality")
        )
        if score >= cfg.elevated_threshold and corroborated:
            classification = ELEVATED_SCREENING_RISK
        elif score >= cfg.potential_threshold:
            classification = POTENTIAL_RUNOFF_RISK
            if score >= cfg.elevated_threshold:
                evidence.append(
                    "Score reached the elevated threshold but no river-response or water-quality signal "
                    "corroborates it, so the result is capped at POTENTIAL_RUNOFF_RISK."
                )
        else:
            classification = NO_ELEVATED_SIGNAL

    summary = plain_summary(classification, components, rain, area.linked_to_study_catchment, rain_ok)
    confidence = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(len(available), "NONE")
    if classification == INSUFFICIENT_DATA:
        confidence = "NONE"

    return {
        "area_id": area.area_id,
        "name": area.name,
        "area_type": area.area_type,
        "classification": classification,
        "summary": summary,
        "score": score,
        "confidence": confidence,
        "components": components,
        "weights": weights,
        "evidence": evidence,
        "missing_inputs": missing,
        "next_step": NEXT_STEPS[classification],
        "linkage": {"linked": area.linked_to_study_catchment, "basis": area.linkage_basis},
        "inputs": {
            "rainfall": asdict(rain) if rain else None,
            "gauges": [asdict(g) for g in area.gauges],
            "water_quality": [asdict(s) for s in area.water_quality[:5]],
        },
        "context": area.context,
        "calculated_at": calculated_at.isoformat().replace("+00:00", "Z"),
        "engine_version": ENGINE_VERSION,
        "data_status": "MODELLED_INDICATOR",
        "is_official_advisory": False,
    }


NEXT_STEPS = {
    INSUFFICIENT_DATA: "No assessment possible right now. Check the official monitoring source directly.",
    NO_ELEVATED_SIGNAL: "No extra action suggested. Continue routine monitoring.",
    POTENTIAL_RUNOFF_RISK: "Keep watch: check rainfall and river trends over the next day, and review official "
    "shellfish (SFPA) and bathing-water (beaches.ie) notices.",
    ELEVATED_SCREENING_RISK: "Review now: confirm with official sources and consider extra sampling or "
    "precautions under your own procedures. This is not an official closure or warning.",
}


def _rain_phrase(r: float | None, rain: RainfallInput | None) -> str:
    total = f" ({rain.total_48h_mm:.0f} mm in 2 days)" if rain and rain.total_48h_mm is not None else ""
    if r is None:
        return "no recent rainfall record"
    if r >= 0.5:
        return f"heavy rain{total}"
    if r > 0.15:
        return f"moderate rain{total}"
    return f"little rain{total}"


def _river_phrase(f: float | None) -> str:
    if f is None:
        return "river levels unavailable"
    if f >= 0.5:
        return "rivers running high"
    if f >= 0.2:
        return "rivers slightly raised"
    return "rivers at normal levels"


def plain_summary(classification: str, components: dict, rain: RainfallInput | None, linked: bool, rain_ok: bool) -> str:
    """One plain-English sentence explaining the result, for non-specialist readers."""
    if not linked:
        return "Not assessed: this area is fed by a river catchment that RunoffPulse does not monitor yet."
    if not rain_ok:
        return "Not assessed: the recent rainfall record is incomplete."
    detail = f"{_rain_phrase(components['rainfall'], rain).capitalize()} and {_river_phrase(components['river_response'])}"
    if components.get("water_quality") is not None and components["water_quality"] >= 0.5:
        detail += ", and a nearby beach recently failed its bacteria test"
    return {
        NO_ELEVATED_SIGNAL: f"{detail}. Runoff is unlikely to be elevated.",
        POTENTIAL_RUNOFF_RISK: f"{detail}. Runoff may be reaching this area.",
        ELEVATED_SCREENING_RISK: f"{detail}. Runoff is likely reaching this area.",
    }[classification]


def config_as_dict(cfg: ScreeningConfig | None = None) -> dict[str, Any]:
    return asdict(cfg or ScreeningConfig())
