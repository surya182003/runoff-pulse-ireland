// Mock API responses for component tests only. Never imported by application code.
import { vi } from "vitest";

const rainWindow = (h: number) => ({
  window_hours: h,
  total_mm: 0.3,
  hours_with_data: h,
  coverage: 1,
  max_hourly_mm: 0.1,
  start_utc: "2026-10-15T10:00:00Z",
  end_utc: "2026-10-17T10:00:00Z",
});

export const area = {
  area_id: "IEPA2_0047",
  name: "Rostellan South",
  area_type: "Designated shellfish water",
  classification: "NO_ELEVATED_SIGNAL",
  summary: "Little rain (0 mm in 2 days) and rivers at normal levels. Runoff is unlikely to be elevated.",
  catchment: "Lee, Cork Harbour and Youghal Bay",
  score: 0.15,
  confidence: "MEDIUM",
  components: { rainfall: 0, river_response: 0.36, water_quality: null },
  weights: { rainfall: 0.5, river_response: 0.35, water_quality: 0.15 },
  evidence: ["Met Éireann Cork Airport: 0.3 mm in 48 h."],
  missing_inputs: ["No official bathing-water sample within 7 days (sampling is seasonal)."],
  next_step: "No action suggested by this screen.",
  linkage: { linked: true, basis: "Parent waterbody EPA attribute AdjacentHydrometricArea = 'Lee, Cork Harbour and Youghal Bay'" },
  inputs: { rainfall: null, gauges: 2, water_quality: [] },
  context: { parent_waterbody: "Cork Harbour", parent_wfd_status: "Good", parent_wfd_status_period: "SW 2019-2024" },
  calculated_at: "2026-10-17T10:00:00Z",
  engine_version: "screening-heuristic-1.0",
  data_status: "MODELLED_INDICATOR",
  is_official_advisory: false,
};

const square = { type: "Polygon", coordinates: [[[-8.25, 51.84], [-8.23, 51.84], [-8.23, 51.86], [-8.25, 51.86], [-8.25, 51.84]]] };

export const stations = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-8.47, 51.89] },
      properties: { StationID: "RS19L030500", StationName: "Lee at Test Bridge", StationType: "RIVER_STATION", in_study_catchment: true, data_status: "REAL_STATION_LOCATION" },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-8.33, 51.88] },
      properties: { StationID: "TW060LE4001", StationName: "Lough Mahon Test", StationType: "TRANSITIONAL_STATION", in_study_catchment: false, data_status: "REAL_STATION_LOCATION" },
    },
    { type: "Feature", geometry: null, properties: { StationID: "BAD", StationName: "No geometry", StationType: "RIVER_STATION", in_study_catchment: false, data_status: "REAL_STATION_LOCATION" } },
  ],
  meta: { station_types: { RIVER_STATION: 2, TRANSITIONAL_STATION: 1 }, returned: 3 },
};

const metrics = (auc: number) => ({ roc_auc: auc, roc_auc_95ci: [auc - 0.06, auc + 0.06], average_precision: 0.09, brier: 0.042, log_loss: 0.17 });

export const fixtures: Record<string, unknown> = {
  "/api/predictions": {
    date: "2025-08-15",
    status: "OK",
    message: "Prediction within the model's training conditions.",
    model_id: "bathing-elevated-bacteria",
    model_version: "20261017",
    variant: "recent",
    inputs: { rainfall_mm: { rain_d1: 12.4 }, rain_station: "Met Éireann Cork Airport" },
    predictions: [
      {
        beach_id: "B1", beach_name: "Garryvoe", lon: -8.0, lat: 51.86, probability: 0.184, band: "ABOVE_TYPICAL",
        drivers: [{ factor: "Rain yesterday", log_odds: 0.6 }, { factor: "Beach history", log_odds: 0.4 }],
        observed: { e_coli: "620", enterococci: "40", elevated: true, sample_status: "Poor" }, backtest_out_of_sample_probability: 0.16,
      },
      {
        beach_id: "B2", beach_name: "Fountainstown", lon: -8.31, lat: 51.77, probability: 0.021, band: "BELOW_TYPICAL",
        drivers: [{ factor: "Beach history", log_odds: -0.3 }], observed: null, backtest_out_of_sample_probability: null,
      },
    ],
    target: { definition: "E. coli > 250 OR intestinal enterococci > 100 per 100 ml", basis: "EU BWD" },
    bands: [],
    data_status: "MODELLED_INDICATOR",
    disclaimer: "Machine-learning estimate. Not an official bathing-water advisory and not a measurement.",
    calculated_at: "2026-10-17T10:00:00Z",
  },
  "/api/model": {
    model_id: "bathing-elevated-bacteria", version: "20261017", trained_at: "2026-10-17T10:00:00Z", task: "t",
    target: { definition: "d", basis: "b" }, algorithm: "logistic regression", evaluation: "Leave-one-year-out cross-validation",
    bands: [], deployed_variant: "recent", deployment_rule: "r", limitations: ["Single rain gauge."],
    compared_variants: { full: { rain_features: [], evaluation: { logistic_regression: metrics(0.67) }, decision: "Not deployed" } },
    variants: {
      recent: {
        rain_features: ["rain_d1"], numeric_features: [], intercept: -3, coefficients: { rain_d1: 0.27, season_sin: -0.48, season_cos: 0.02 },
        regularisation_C: 0.3,
        training: { samples: 1714, events: 77, event_rate: 0.045, beaches: 24, period: ["2015-05-27", "2026-09-07"], months: [5, 6, 7, 8, 9] },
        evaluation: { baseline_beach_rate: metrics(0.65), logistic_regression: metrics(0.69), gradient_boosting: metrics(0.7) },
        calibration: [{ mean_predicted: 0.01, observed_rate: 0.009, n: 343 }, { mean_predicted: 0.1, observed_rate: 0.088, n: 343 }],
        top_vs_bottom_quintile_ratio: 8,
        bands_out_of_sample: [
          { band: "BELOW_TYPICAL", range: [0, 0.03], n: 691, events: 12, observed_rate: 0.017 },
          { band: "ABOVE_TYPICAL", range: [0.08, 1], n: 209, events: 27, observed_rate: 0.129 },
        ],
        per_year_auc: {}, beach_effects: [{ beach_id: "B1", beach_name: "Garryvoe", log_odds: 1.0 }],
      },
    },
  },
  "/api/model/backtest": {
    records: [
      { date: "2025-08-15", beach_id: "B1", beach_name: "Garryvoe", observed_elevated: true, p_out_of_sample: 0.16, rain_d1_mm: 12.4 },
      { date: "2025-08-01", beach_id: "B2", beach_name: "Fountainstown", observed_elevated: false, p_out_of_sample: 0.02, rain_d1_mm: 0 },
    ],
    note: "Each probability comes from a model trained without that sample's year.",
  },
  "/api/health": { status: "ok", version: "0.1.0" },
  "/api/summary": {
    monitoring_stations: { total: 668, by_type: { RIVER_STATION: 490, TRANSITIONAL_STATION: 80 }, data_status: "REAL_STATION_LOCATION" },
    latest_rainfall: { datetime_utc: "2026-10-17T10:00:00Z", rain_mm: 0, age_hours: 0.8, last_24h: rainWindow(24), station: "Cork Airport", data_status: "REAL_OBSERVATION" },
    water_quality: { usable_observations: 1682, latest_sample_date: "2026-09-07", data_status: "REAL_OBSERVATION" },
    screening: { counts: { NO_ELEVATED_SIGNAL: 21, INSUFFICIENT_DATA: 3 }, areas_flagged: 0, definition: "x", calculated_at: "2026-10-17T10:00:00Z", data_status: "MODELLED_INDICATOR" },
    hydrometric: { stations: 53, mode: "LIVE", retrieved_at: "2026-10-17T10:00:00Z" },
    citizen_reports: { total: 0, data_status: "CITIZEN_REPORTED_UNVERIFIED" },
    freshness: [{ id: "epa_monitoring_stations", title: "EPA stations", retrieved_at: "2026-10-17T10:00:00Z", period: null, data_status: "REAL_STATION_LOCATION" }],
  },
  "/api/rainfall": {
    station: { id: "3904", name: "Cork Airport", lon: -8.486, lat: 51.847 },
    resolution: "daily",
    start: "2026-08-18",
    end: "2026-10-17",
    unit: "mm",
    data_status: "REAL_OBSERVATION",
    records: [
      { date: "2026-09-29", rain_mm: 7.5, hours_with_data: null, source: "met_eireann_daily_archive", complete: true },
      { date: "2026-10-16", rain_mm: null, hours_with_data: 12, source: "met_eireann_hourly_reports", complete: false },
    ],
    latest_observation: { datetime_utc: "2026-10-17T10:00:00Z", rain_mm: 0, source: "met_eireann_latest_reports", age_hours: 0.8 },
    windows: { last_24h: rainWindow(24), last_48h: rainWindow(48) },
    live_feed: { mode: "LIVE", retrieved_at: "2026-10-17T10:00:00Z", error: null },
    archive_periods: { met_rainfall_daily: ["2015-01-01", "2026-09-30"] },
    notes: ["Daily values: Met Éireann archive."],
  },
  "/api/risk": {
    as_of: "2026-10-17T10:00:00Z",
    mode: "CURRENT",
    calculated_at: "2026-10-17T10:00:00Z",
    counts: { NO_ELEVATED_SIGNAL: 1 },
    areas: [area],
    shared_inputs: {
      rainfall: { mode: "LIVE", live_error: null, window_24h: rainWindow(24), window_48h: rainWindow(48) },
      gauges: { mode: "LIVE", retrieved_at: null, error: null, excluded_gauges: [], readings: [] },
      gauge_count_usable: 28,
    },
    method: { config: {}, documentation: "docs/RISK_METHOD.md", limitations: ["Screening heuristic only."] },
    disclaimer: "Software-generated screening indicator. Not an official advisory.",
  },
  "/api/stations": stations,
  "/api/stations/RS19L030500": {
    station: stations.features[0],
    observations: [],
    observations_note: "EPA chemistry results are not connected.",
    links: { catchments_ie_waterbody: null, epa_geoportal: "https://gis.epa.ie" },
    nearby_hydrometric_gauges: [],
    nearby_bathing_waters: [],
    proximity_note: "Proximity does not establish hydrological connectivity.",
  },
  "/api/catchment": {
    catchment: { type: "FeatureCollection", features: [{ type: "Feature", geometry: square, properties: { Name: "Lee", Catchment_Id: "19", Area_km2: 1 } }] },
    subcatchments: { type: "FeatureCollection", features: [] },
    study_area_bbox: [-9.42, 51.7, -7.78, 52.11],
    catchment_id: "19",
    catchment_name: "Lee, Cork Harbour and Youghal Bay",
  },
  "/api/rivers": { type: "FeatureCollection", features: [] },
  "/api/waterbodies": { type: "FeatureCollection", features: [] },
  "/api/hydrometric": { type: "FeatureCollection", features: [], meta: { mode: "LIVE", retrieved_at: null, error: null, note: "" } },
  "/api/aquaculture": {
    shellfish_waters: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: square,
          properties: {
            area_id: "IEPA2_0047",
            name: "Rostellan South",
            designation: "Shellfish Waters (WFD Register of Protected Areas)",
            parent_waterbody_code: "IE_SW_060_0000",
            parent_waterbody_name: "Cork Harbour",
            parent_waterbody_wfd_status: "Good",
            parent_waterbody_wfd_status_period: "SW 2019-2024",
            adjacent_hydrometric_area: "Lee, Cork Harbour and Youghal Bay",
            linked_to_study_catchment: true,
            screening: area,
            nearby_monitoring_stations: [],
            official_advisory_status: "NOT_CONNECTED",
          },
        },
      ],
    },
    shellfish_waters_available: true,
    production_areas: { available: false, features: [], note: "SFPA classified production areas are not yet loaded." },
    official_advisories: { status: "NOT_CONNECTED", message: "No authoritative shellfish advisory feed is connected.", sources: [] },
    screening_as_of: "2026-10-17T10:00:00Z",
    disclaimer: "x",
  },
  "/api/alerts": {
    screening_alerts: [],
    official_alerts: [],
    official_alerts_retrieved_at: "2026-10-17T10:00:00Z",
    official_alerts_national_count: 0,
    delivery: { external_notifications: "DISABLED", note: "" },
  },
  "/api/reports": { items: [], page: 1, page_size: 20, total: 0 },
  "/api/water-quality": {
    records: [],
    total_matching: 0,
    returned: 0,
    stations: [{ beach_id: "B1", beach_name: "Fountainstown", classification: "Good Quality", classification_year: 2025, lon: -8.31, lat: 51.77, latest_sample_date: "2026-09-07" }],
    indicators: ["E. coli", "Intestinal enterococci"],
    units: ["count/100 ml"],
    river_water_temperature: [],
    not_connected: [{ measurement: "Nitrate, ortho-phosphate", reason: "No open API identified." }],
    notes: [],
  },
  "/api/sources": {
    datasets: [
      {
        id: "epa_monitoring_stations",
        title: "EPA water monitoring station locations",
        publisher: "EPA Ireland",
        licence: "CC BY 4.0",
        retrieved_at: "2026-10-17T10:38:46Z",
        record_count: 668,
        data_status: "REAL_STATION_LOCATION",
        crs: "EPSG:4326",
        file: "monitoring_stations.geojson",
        notes: "Station locations only.",
      },
    ],
    manifest_updated_at: null,
    live_feeds: [{ id: "opw_live", title: "OPW latest", mode: "LIVE", retrieved_at: null, error: null, data_status: "REAL_OBSERVATION" }],
    derived: [],
    not_connected: [{ title: "SFPA production areas", reason: "Not integrated." }],
    data_status_definitions: { SIMULATED_DEMO: "Synthetic data for demonstration only.", REAL_OBSERVATION: "Measured." },
  },
};

export type Override = Record<string, unknown | ((init?: RequestInit) => Response | Promise<Response>)>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Install a fetch mock that answers by URL path; overrides take precedence. */
export function mockApi(overrides: Override = {}) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(typeof input === "string" ? input : input.toString()).pathname;
    const handler = path in overrides ? overrides[path] : fixtures[path];
    if (typeof handler === "function") return (handler as (init?: RequestInit) => Response)(init);
    if (handler === undefined) return json({ detail: `No fixture for ${path}` }, 404);
    return json(handler);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
