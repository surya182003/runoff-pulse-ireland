# 🌊 RunoffPulse Ireland

[![Ocean Hackathon Winner](https://img.shields.io/badge/Ocean_Hackathon_Cork-3rd_Place_Winner_🥉-blue?style=for-the-badge&logo=github)](https://github.com/surya182003/runoff-pulse-ireland)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)

> **🏆 Awarded 3rd Place at Ocean Hackathon Cork!**  
> **From Rainfall to Coastal Risk, Before It Becomes a Bigger Problem.**

A decision-support prototype for Cork Harbour and the River Lee catchment (EPA WFD Catchment 19,
"Lee, Cork Harbour and Youghal Bay"). It combines real environmental data, an explainable runoff-risk
screen, aquaculture situational awareness and community reporting.

> RunoffPulse is **not** a certified pollution prediction system, a regulatory notification service, or a
> replacement for official bathing-water or shellfish-harvesting decisions (EPA, SFPA, Marine Institute).

## What's real

| Data | Source | Status |
|---|---|---|
| 668 water monitoring station locations | EPA GeoServer WFS `EPA:MON_WaterStations` | REAL_STATION_LOCATION |
| Catchment, sub-catchments, river and estuarine/coastal waterbodies with WFD status | EPA GeoServer WFS | REAL_REFERENCE_GEOMETRY / OFFICIAL_ASSESSMENT |
| Designated shellfish waters (WFD Register of Protected Areas) | EPA `EPA:WFD_RPA_SHELLFISH` | OFFICIAL_DESIGNATION |
| Daily (2015–) and hourly (2023–) rainfall, Cork Airport, plus latest hourly reports | Met Éireann (CC BY 4.0) | REAL_OBSERVATION |
| Live river levels and water temperature (53 OPW stations) | OPW waterlevel.ie | REAL_OBSERVATION (provisional) |
| Bathing-water E. coli / enterococci results (1,682), classifications, active alerts | EPA Bathing Water API (CC BY 4.0) | REAL_OBSERVATION / OFFICIAL_ADVISORY |
| Runoff-risk screening | Computed by RunoffPulse ([method](docs/RISK_METHOD.md)) | MODELLED_INDICATOR |
| Citizen reports | Users, stored in SQLite | CITIZEN_REPORTED_UNVERIFIED |

**No simulated data is used anywhere.** The following are not connected, are labelled as such in the app,
and are never estimated: EPA river/estuarine chemistry (nutrients, DO, etc.), SFPA classified production
areas and harvest status, Marine Institute biotoxins, satellite products, and tides/currents.

## AI / machine-learning prediction

The **AI Prediction** page (`/prediction`, API `/api/predictions?date=`, `/api/model`, `/api/model/backtest`)
estimates the probability that a bathing-water sample at each beach would show **elevated bacteria**: E. coli
above 250 or intestinal enterococci above 100 per 100 ml, the EU coastal "Excellent" limits.

* **Data:** 1,714 EPA samples (2015–2026) from 24 beaches within 60 km of Cork Airport, joined to Met
  Éireann rainfall. 77 samples (4.5%) were elevated.
* **Model:** L2-regularised logistic regression (scikit-learn) on the previous day's rainfall, the time of year
  and the beach. It is exported as JSON coefficients, so there are no pickle files and no scikit-learn
  dependency at runtime. Each prediction lists its main drivers.
* **Validation (leave-one-year-out, every year scored by a model that never saw it):**
  * ROC AUC 0.69 (95% CI 0.63–0.75), against 0.65 for beach history alone.
  * Samples in the top fifth of predictions were 8× as likely to be elevated as those in the bottom fifth.
  * The bands hold up out of sample: observed elevated rates were 1.7% (below typical), 4.7% (typical) and
    12.9% (above typical).
* **Not deployed:** a 7-day-rainfall variant (AUC 0.67) and gradient boosting (AUC 0.70, but worse calibrated)
  gave no real improvement.
* **Honest limits:** the signal is modest and the model covers the bathing season only. Out-of-season dates
  are flagged as indicative, and missing rainfall gives "unavailable" rather than a guess. The model is not an
  official advisory and does not cover shellfish contamination or biotoxins.

Retrain after refreshing data:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ml.txt
.\.venv\Scripts\python.exe scripts\train_bathing_model.py
```

## Prerequisites (Windows)

* Python 3.11+ (tested with 3.12.10)
* Node.js 20+ (tested with 24.20.0, npm 11)

## Setup (PowerShell, from the repository root)

```powershell
# Backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# Optional configuration
Copy-Item .env.example .env

# Frontend
cd frontend
npm install
cd ..
```

## Acquire the data

The repository ships with a snapshot acquired on 17 Oct 2026. To refresh it (takes about 1–2 minutes):

```powershell
.\.venv\Scripts\python.exe scripts\acquire_all.py
# or a subset:
.\.venv\Scripts\python.exe scripts\acquire_all.py --only met,opw
```

Each source runs independently, and a failing upstream service is reported without stopping the others.
Provenance (publisher, URL, licence, retrieval time, CRS, record count, period, notes) is written to
`backend/data/manifest.json` and shown on the **Data Sources** page. Re-running regularly also builds up the
recent hourly rainfall record, because Met Éireann's latest-report feed only covers yesterday and today.

## Run

Use two terminals:

```powershell
# Terminal 1: API on http://localhost:8000 (docs at /docs)
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Terminal 2: web app on http://localhost:5173
cd frontend
npm run dev
```

To point the frontend at a different API, create `frontend/.env.local` with `VITE_API_BASE_URL=...`.
For an offline demo, set `RUNOFFPULSE_LIVE_ENABLED=false` in `.env`. The API then serves only the acquired
snapshots and labels them as such.

## Test

```powershell
cd backend;  ..\.venv\Scripts\python.exe -m pytest      # 64 tests, offline fixtures
cd ..\frontend; npm test                                # 17 tests (vitest + Testing Library)
npm run build                                           # type-check + production build
```

## Demo walkthrough

0. **Event replays** (Overview and Coastal Risk Map buttons, or `/?scenario=sep2026`): **27 Sep 2026**
   uses real measurements from 20 mm of rain in 2 days and 30 of 62 river gauges running high, and every
   coastal area turns *High runoff risk*. **Storm Babet** shows the cap at *Possible* when no river evidence
   exists. Screening now covers 34 coastal areas fed by the Lee, Bandon and Blackwater catchments (62 river
   gauges), so no area is left "not assessed".
1. **Overview**: one plain-language status for the coast, four key numbers, a map and the list of areas.
2. **Risk Map**: toggle layers, filter station types, click a station (detail panel) or an estuary/shellfish
   water (screening evidence). Set the screening date to **2023-10-18** (Storm Babet) to replay: 82.4 mm in
   48 h makes every linked area *Potential runoff risk*. It is capped there because no river-level record
   from 2023 can corroborate it, which shows the engine refusing to overclaim.
3. **Aquaculture Watch**: designated shellfish waters with linkage, WFD status, nearby stations and
   screening. Kinsale, Oyster Haven and Ballymacoda show *Insufficient data* because they drain other
   catchments. **Export briefing** downloads a Markdown summary.
4. **Water Quality**: bathing-water bacteriology time series (log scale, censored values kept), river
   temperature, and an explicit list of what is not available.
5. **Rainfall**: archive and live reports. Days with no record appear as gaps, never as zeros.
6. **Citizen Reports**: submit with a map-picked location and an optional photo; reports stay unverified.
7. **Data Sources** and **Business Value**.

## Architecture

```
scripts/                     acquisition CLIs (acquire_all.py, download_epa_stations.py)
backend/app/ingest/          EPA WFS, Met Éireann, EPA bathing water, OPW downloaders (+ manifest)
backend/app/geo.py           geometry normalisation, coordinate validation, CRS conversion
backend/app/risk_engine.py   pure, explainable screening engine
backend/app/screening.py     assembles engine inputs (archive + cached live feeds)
backend/app/main.py          FastAPI endpoints
backend/data/                acquired datasets (GeoJSON EPSG:4326 lon/lat, CSV, manifest.json)
backend/var/                 SQLite reports DB + uploads (git-ignored)
frontend/src/                React + TypeScript + Vite + Tailwind + React Leaflet + Recharts
docs/RISK_METHOD.md          screening formula, weights, thresholds, limitations
```

API: `/api/health`, `/api/stations`, `/api/stations/{id}`, `/api/rivers`, `/api/catchment`,
`/api/waterbodies`, `/api/hydrometric`, `/api/hydrometric/{n}/series`, `/api/rainfall`,
`/api/water-quality`, `/api/risk?as_of=`, `/api/aquaculture`, `/api/alerts`, `/api/reports` (GET/POST),
`/api/reports/{id}/photo`, `/api/sources`, `/api/summary`.

## Data engineering notes

* EPA publishes stations as **MultiPoint**. The original acquisition script accepted only `Point` and
  therefore discarded every station. Its western bound (-8.65) also excluded the upper Lee. Both are fixed:
  the study area comes from the official catchment polygon, and points are normalised and validated.
* EPA GeoServer refuses `startIndex` paging without a sort key. Paging sorts by `StationID`, and any
  truncated single-page result is rejected rather than silently accepted.
* Bathing-water coordinates are Irish Grid (EPSG:29903), not ITM. This was verified against a known
  location before conversion.
* Met Éireann latest-report times are Irish local time and are converted to UTC. Missing hours are never
  treated as dry.
* OPW gauges affected by dam regulation or tides are excluded from the river-response signal, with the
  reason recorded.

## Security

No secrets are required. Requests are validated with Pydantic. CORS is restricted to the dev origin. Photo
uploads are limited to JPEG/PNG/WebP (checked by file signature) and 5 MB, and are stored under
server-generated names. User text is rendered as text, never as HTML. The local database and uploads are
git-ignored.

## Licences and attribution

EPA Ireland and Met Éireann data are used under CC BY 4.0. OPW waterlevel.ie data are attributed to the
Office of Public Works; review the waterlevel.ie terms before redistribution (not verified by this
project). Map tiles © OpenStreetMap contributors.
