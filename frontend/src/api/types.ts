// Typed shapes of the RunoffPulse API responses (backend/app/main.py).

export type DataStatus =
  | "REAL_OBSERVATION"
  | "REAL_STATION_LOCATION"
  | "REAL_REFERENCE_GEOMETRY"
  | "OFFICIAL_ASSESSMENT"
  | "OFFICIAL_DESIGNATION"
  | "OFFICIAL_ADVISORY"
  | "MODELLED_INDICATOR"
  | "SIMULATED_DEMO"
  | "CITIZEN_REPORTED_UNVERIFIED";

export type Classification =
  | "INSUFFICIENT_DATA"
  | "NO_ELEVATED_SIGNAL"
  | "POTENTIAL_RUNOFF_RISK"
  | "ELEVATED_SCREENING_RISK";

export interface Geometry {
  type: string;
  coordinates: unknown;
}

export interface Feature<P = Record<string, unknown>> {
  type: "Feature";
  geometry: Geometry | null;
  properties: P;
}

export interface FeatureCollection<P = Record<string, unknown>, M = Record<string, unknown>> {
  type: "FeatureCollection";
  features: Feature<P>[];
  meta?: M;
}

export interface StationProps {
  StationID: string;
  StationName: string;
  StationType: string;
  EntityName?: string;
  WBWFDWISECODE?: string;
  TypeofWaterMonitored?: string;
  LocalAuthority?: string;
  EPAStationTypeWFDs?: string;
  in_study_catchment: boolean;
  data_status: DataStatus;
  retrieved_at?: string;
}

export interface StationsResponse extends FeatureCollection<StationProps> {
  meta: { station_types: Record<string, number>; returned: number; retrieved_at?: string; licence?: string };
}

export interface StationDetail {
  station: Feature<StationProps>;
  observations: unknown[];
  observations_note: string;
  links: { catchments_ie_waterbody: string | null; epa_geoportal: string };
  nearby_hydrometric_gauges: { station_number: string; station_name: string; distance_km: number; url: string }[];
  nearby_bathing_waters: { beach_id: string; beach_name: string; classification: string | null; distance_km: number }[];
  proximity_note: string;
}

export interface HydroProps {
  station_ref: string;
  station_number: string;
  station_name: string;
  sensor_ref: string;
  parameter: string;
  unit: string;
  value: number | null;
  observed_at: string | null;
  in_study_catchment: boolean;
  catchment_name?: string | null;
  station_url: string;
  excluded_from_screening?: string | null;
}

export interface HydroResponse extends FeatureCollection<HydroProps> {
  meta: { mode: string; retrieved_at: string | null; error: string | null; note: string };
}

export interface RiverProps {
  European_Code: string;
  Name: string;
  wfd_status: string | null;
  wfd_status_period: string | null;
}

export interface WaterbodyProps {
  EU_CD: string;
  NAME: string;
  waterbody_category: string;
  wfd_status: string | null;
  wfd_status_period: string | null;
  AdjacentHydrometricArea: string | null;
  URL?: string;
}

export interface CatchmentResponse {
  catchment: FeatureCollection<{ Name: string; Catchment_Id: string; Area_km2: number }>;
  subcatchments: FeatureCollection<{ Name: string; Subcatchment_Id: string }>;
  study_area_bbox: number[];
  catchment_id: string;
  catchment_name: string;
}

export interface RainWindow {
  window_hours: number;
  total_mm: number | null;
  hours_with_data: number;
  coverage: number;
  max_hourly_mm: number | null;
  start_utc: string;
  end_utc: string;
}

export interface DailyRain {
  date: string;
  rain_mm: number | null;
  hours_with_data: number | null;
  source: string;
  complete: boolean;
}

export interface HourlyRain {
  datetime_utc: string;
  rain_mm: number | null;
  source: string;
}

export interface RainfallResponse {
  station: { id: string; name: string; lon: number; lat: number };
  resolution: "daily" | "hourly";
  start: string;
  end: string;
  unit: string;
  data_status: DataStatus;
  records: (DailyRain | HourlyRain)[];
  latest_observation: { datetime_utc: string; rain_mm: number | null; source: string; age_hours: number } | null;
  windows: { last_24h: RainWindow; last_48h: RainWindow };
  live_feed: { mode: string; retrieved_at: string | null; error: string | null };
  archive_periods: Record<string, string[] | null>;
  notes: string[];
}

export interface WQRecord {
  station_id: string;
  station_name: string;
  observed_date: string | null;
  measurement: string;
  value: number | null;
  value_raw: string;
  qualifier: string | null;
  unit: string;
  sample_status: string | null;
  source: string;
  data_status: DataStatus;
}

export interface BathingStation {
  beach_id: string;
  beach_name: string;
  classification: string | null;
  classification_year: number | null;
  lon: number;
  lat: number;
  latest_sample_date: string | null;
}

export interface WaterQualityResponse {
  records: WQRecord[];
  total_matching: number;
  returned: number;
  stations: BathingStation[];
  indicators: string[];
  units: string[];
  river_water_temperature: (HydroProps & { lon: number; lat: number })[];
  not_connected: { measurement: string; reason: string }[];
  notes: string[];
}

export interface RainfallInput {
  station_name: string;
  total_24h_mm: number | null;
  total_48h_mm: number | null;
  coverage_48h: number;
  max_hourly_24h_mm: number | null;
  latest_observation_utc: string | null;
  latest_age_hours: number | null;
  percentile_48h: number | null;
}

export interface GaugeReading {
  station_number: string;
  station_name: string;
  latest_level_m: number | null;
  observed_at: string | null;
  age_hours: number | null;
  percentile_30d: number | null;
  series_points: number;
  catchment?: string;
}

export interface AreaScreening {
  area_id: string;
  name: string;
  area_type: string;
  classification: Classification;
  summary: string;
  catchment?: string | null;
  score: number | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  components: { rainfall: number | null; river_response: number | null; water_quality: number | null };
  weights: Record<string, number>;
  evidence: string[];
  missing_inputs: string[];
  next_step: string;
  linkage: { linked: boolean; basis: string };
  inputs: { rainfall: RainfallInput | null; gauges: number; water_quality: unknown[] };
  context: {
    parent_waterbody?: string | null;
    parent_wfd_status?: string | null;
    parent_wfd_status_period?: string | null;
    adjacent_hydrometric_area?: string | null;
    catchment_significant_pressures?: Record<string, number>;
    water_quality_selection?: string;
  };
  calculated_at: string;
  engine_version: string;
  data_status: DataStatus;
  is_official_advisory: false;
}

export interface RiskResponse {
  as_of: string;
  mode: "CURRENT" | "HISTORICAL_REPLAY";
  calculated_at: string;
  counts: Partial<Record<Classification, number>>;
  areas: AreaScreening[];
  shared_inputs: {
    rainfall: { mode: string; live_error: string | null; window_24h: RainWindow; window_48h: RainWindow };
    gauges: {
      mode: string;
      retrieved_at: string | null;
      error: string | null;
      excluded_gauges: { station_number: string; station_name: string; reason: string }[];
      readings: GaugeReading[];
    };
    gauge_count_usable: number;
  };
  method: { config: Record<string, number>; documentation: string; limitations: string[] };
  disclaimer: string;
}

export interface ShellfishProps {
  area_id: string;
  name: string;
  designation: string;
  parent_waterbody_code: string;
  parent_waterbody_name: string | null;
  parent_waterbody_wfd_status: string | null;
  parent_waterbody_wfd_status_period: string | null;
  adjacent_hydrometric_area: string | null;
  linked_to_study_catchment: boolean;
  screening: AreaScreening | null;
  nearby_monitoring_stations: {
    StationID: string;
    StationName: string;
    StationType: string;
    inside_area: boolean;
    approx_distance_km: number;
  }[];
  official_advisory_status: string;
}

export interface AquacultureResponse {
  shellfish_waters: FeatureCollection<ShellfishProps>;
  shellfish_waters_available: boolean;
  production_areas: { available: boolean; features: Feature[]; note: string };
  official_advisories: { status: string; message: string; sources: { name: string; url: string }[] };
  screening_as_of: string;
  disclaimer: string;
}

export type ReportCategory = "UNUSUAL_COLOUR" | "FOAM" | "DEBRIS" | "UNUSUAL_ODOUR" | "OTHER";

export interface Report {
  id: string;
  category: ReportCategory;
  description: string;
  latitude: number;
  longitude: number;
  observed_at: string;
  created_at: string;
  has_photo: boolean;
  verification_status: string;
  data_status: DataStatus;
}

export interface ReportPage {
  items: Report[];
  page: number;
  page_size: number;
  total: number;
}

export interface DatasetEntry {
  id: string;
  title: string;
  file?: string;
  publisher?: string;
  source_url?: string;
  licence?: string;
  retrieved_at?: string;
  crs?: string;
  record_count?: number;
  period?: string[] | null;
  data_status?: DataStatus;
  notes?: string;
}

export interface SourcesResponse {
  datasets: DatasetEntry[];
  manifest_updated_at: string | null;
  live_feeds: { id: string; title: string; mode: string; retrieved_at: string | null; error: string | null; data_status: DataStatus }[];
  derived: { id: string; title: string; data_status: DataStatus; notes: string }[];
  not_connected: { title: string; reason: string }[];
  data_status_definitions: Record<DataStatus, string>;
}

export interface SummaryResponse {
  monitoring_stations: { total: number; by_type: Record<string, number>; data_status: DataStatus };
  latest_rainfall: {
    datetime_utc: string;
    rain_mm: number | null;
    age_hours: number;
    last_24h: RainWindow;
    station: string;
    data_status: DataStatus;
  } | null;
  water_quality: { usable_observations: number; latest_sample_date: string | null; data_status: DataStatus };
  screening: {
    counts: Partial<Record<Classification, number>>;
    areas_flagged: number;
    definition: string;
    calculated_at: string;
    data_status: DataStatus;
  };
  hydrometric: { stations: number; mode: string; retrieved_at: string | null };
  citizen_reports: { total: number; data_status: DataStatus };
  freshness: { id: string; title: string; retrieved_at: string | null; period: string[] | null; data_status: DataStatus }[];
}

export type PredictionBand = "BELOW_TYPICAL" | "TYPICAL" | "ABOVE_TYPICAL";

export interface BeachPrediction {
  beach_id: string;
  beach_name: string;
  lon: number;
  lat: number;
  probability: number | null;
  band: PredictionBand | null;
  drivers: { factor: string; log_odds: number }[];
  beach_in_training?: boolean;
  observed: { e_coli: string | null; enterococci: string | null; elevated: boolean | null; sample_status: string | null } | null;
  backtest_out_of_sample_probability: number | null;
}

export interface PredictionsResponse {
  date: string;
  status: "OK" | "OUT_OF_SEASON" | "UNAVAILABLE";
  message: string;
  model_id: string;
  model_version: string;
  variant: string | null;
  inputs: { rainfall_mm: Record<string, number | null>; rain_station: string };
  predictions: BeachPrediction[];
  target: { definition: string; basis: string };
  bands: { band: PredictionBand; min: number; max: number }[];
  data_status: DataStatus;
  disclaimer: string;
  calculated_at: string;
}

export interface ModelMetrics {
  roc_auc: number;
  roc_auc_95ci: [number, number];
  average_precision: number;
  brier: number;
  log_loss: number;
  brier_skill_vs_baseline?: number;
}

export interface ModelCard {
  model_id: string;
  version: string;
  trained_at: string;
  task: string;
  target: { definition: string; basis: string };
  algorithm: string;
  evaluation: string;
  bands: { band: PredictionBand; min: number; max: number }[];
  deployed_variant: string;
  deployment_rule: string;
  limitations: string[];
  compared_variants?: Record<string, { rain_features: string[]; evaluation: Record<string, ModelMetrics>; decision: string }>;
  variants: Record<
    string,
    {
      rain_features: string[];
      numeric_features: string[];
      intercept: number;
      coefficients: Record<string, number>;
      regularisation_C: number;
      training: { samples: number; events: number; event_rate: number; beaches: number; period: [string, string]; months: number[] };
      evaluation: { baseline_beach_rate: ModelMetrics; logistic_regression: ModelMetrics; gradient_boosting: ModelMetrics };
      calibration: { mean_predicted: number; observed_rate: number; n: number }[];
      top_vs_bottom_quintile_ratio: number;
      bands_out_of_sample: { band: PredictionBand; range: [number, number]; n: number; events: number; observed_rate: number | null }[];
      per_year_auc: Record<string, number>;
      beach_effects: { beach_id: string; beach_name: string; log_odds: number }[];
    }
  >;
}

export interface BacktestResponse {
  records: { date: string; beach_id: string; beach_name: string; observed_elevated: boolean; p_out_of_sample: number; rain_d1_mm: number | null }[];
  note: string;
}

export interface AlertsResponse {
  screening_alerts: {
    type: string;
    issued_by: string;
    area_id: string;
    area_name: string;
    classification: Classification;
    score: number | null;
    evidence: string[];
    next_step: string;
    calculated_at: string;
  }[];
  official_alerts: Record<string, unknown>[];
  official_alerts_retrieved_at: string | null;
  official_alerts_national_count: number;
  delivery: { external_notifications: string; note: string };
}
