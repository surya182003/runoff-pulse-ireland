# RunoffPulse runoff-risk screening method (screening-heuristic-1.0)

Implementation: `backend/app/risk_engine.py` (pure engine) and `backend/app/screening.py` (input assembly).
Every `/api/risk` response includes the configuration, inputs, evidence, missing inputs and limitations used.

## What it is, and what it is not

The screen answers one question: *do current observations suggest that rainfall-driven runoff from a linked
catchment may be elevated for this coastal area, so that a person should review it?*

It is **not** a calibrated model, a pollutant-concentration prediction, a transport/dilution model, a source
attribution, or an official bathing, public-health or shellfish-harvesting advisory.

## Screening areas

* EPA designated **Shellfish Waters** (WFD Register of Protected Areas) in the study area.
* EPA WFD **transitional and coastal waterbodies** whose `AdjacentHydrometricArea` is
  "Lee, Cork Harbour and Youghal Bay".

## Step 1: necessary inputs (otherwise `INSUFFICIENT_DATA`)

| Input | Requirement | Why |
|---|---|---|
| Catchment linkage | Parent waterbody's EPA attribute `AdjacentHydrometricArea` equals the study catchment (WFD Catchment 19). | An authoritative attribute, not spatial proximity. Areas linked to other catchments (e.g. Kinsale → Bandon-Ilen) are not screened because their catchments are not gauged in this dataset. |
| Recent rainfall | ≥ 75 % of hourly values present in the last 48 h; newest value ≤ 6 h old. | Missing hours are never treated as dry. |

## Step 2: components (each 0–1)

**Rainfall R** (Met Éireann Cork Airport, hourly):

```
R = max( max(0, (P48 − 0.5) / 0.5),  clamp((Imax − 2 mm) / 6 mm, 0, 1) )
```

* `P48` is the empirical percentile of the last-48 h total among all consecutive two-day totals in the
  Cork Airport daily archive (2015 to present). A total at or below the median contributes nothing; the
  wettest two-day totals on record approach 1.
* `Imax` is the largest hourly total in the last 24 h. It captures short, intense bursts: 2 mm/h contributes
  0 and 8 mm/h or more contributes 1.

**River response F** (OPW waterlevel.ie, provisional real-time):

```
F = median over usable gauges of max(0, (Pg − 0.5) / 0.5)
```

* `Pg` is the percentile of a gauge's latest level within its own last-30-day, 15-minute record.
* Usable means the gauge is inside the WFD Catchment 19 polygon, its reading is ≤ 3 h old and it has ≥ 10
  days of record in the window. At least 2 usable gauges are required.
* Excluded: dam-regulated reservoir and tailrace gauges (Inniscarra and Carrigadrohid headraces, Inniscarra
  tailrace), tidal city-quay gauges (St Patrick's Quay, Pope's Quay, Mercy Hospital), and a backup duplicate
  sensor. The reasons are returned by the API.

**Water quality W** (EPA bathing-water results):

The worst official per-sample status within 7 days at bathing waters within 10 km of the area:
Poor → 1.0, Sufficient → 0.5, Good/Excellent → 0.0. The 10 km radius is a **proximity** selection and is
labelled as such. This input is corroborating only; samples are seasonal (about June to mid-September).

## Step 3: score

```
S = Σ wᵢ·cᵢ / Σ wᵢ   over available components only
weights: rainfall 0.50, river response 0.35, water quality 0.15
```

Missing components are excluded and listed, never imputed.

Weight rationale: rainfall is the driver and the only input available for every linked area. River level is
the most direct observed evidence that runoff is reaching the drainage network. Bathing-water bacteriology
is the closest coastal outcome measure but is sparse and seasonal. These are expert-judgement starting
values, not fitted parameters.

## Step 4: classification

| Condition | Class |
|---|---|
| Step 1 fails | `INSUFFICIENT_DATA` |
| S ≥ 0.60 **and** (F ≥ 0.5 or W ≥ 0.5) | `ELEVATED_SCREENING_RISK` |
| S ≥ 0.30 | `POTENTIAL_RUNOFF_RISK` |
| otherwise | `NO_ELEVATED_SIGNAL` |

Rainfall alone can never produce `ELEVATED_SCREENING_RISK`: it needs corroboration from an observed river
or water-quality signal. `NO_ELEVATED_SIGNAL` is not a statement that water quality is good.

Confidence is HIGH, MEDIUM or LOW for 3, 2 or 1 available components (NONE when insufficient).

## Historical replay

`/api/risk?as_of=YYYY-MM-DD` re-runs the screen at the end of that day (UTC) using the archived hourly
rainfall (2023 onward). River levels exist only for the last 30 days, so most replays run on rainfall only
and are capped at `POTENTIAL_RUNOFF_RISK`. Example: on 2023-10-18 (Storm Babet), Cork Airport recorded
82.4 mm in the 48 h to the end of that day, at or above every calendar two-day total in the 2015–present
daily archive.

## Limitations

* Single rain gauge (Cork Airport, 155 m), which may not represent the upper Lee.
* Linkage is at catchment level and implies no flow path, travel time or dilution to a specific area.
* No tides, currents, mixing or pollutant transport are modelled.
* OPW data is provisional and the 30-day percentile is a short baseline (season-dependent).
* WFD significant pressures (e.g. agriculture) are shown as context and are never used to attribute cause.

## Calibration path

Before operational use, the weights and thresholds should be calibrated against historical records:
EPA bathing-water exceedances, Uisce Éireann overflow events, SFPA classification changes and
Marine Institute results, using multi-year OPW level records rather than a 30-day window.
