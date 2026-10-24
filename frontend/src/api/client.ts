import type {
  AlertsResponse,
  AquacultureResponse,
  BacktestResponse,
  CatchmentResponse,
  FeatureCollection,
  HydroResponse,
  ModelCard,
  PredictionsResponse,
  RainfallResponse,
  Report,
  ReportPage,
  RiskResponse,
  RiverProps,
  SourcesResponse,
  StationDetail,
  StationsResponse,
  SummaryResponse,
  WaterbodyProps,
  WaterQualityResponse,
} from "./types";

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";
const TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, params?: Params): string {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function describeError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* fall through */
  }
  return `Request failed with status ${response.status}`;
}

export async function request<T>(path: string, options: { params?: Params; init?: RequestInit; signal?: AbortSignal } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  options.signal?.addEventListener("abort", () => controller.abort());
  try {
    const response = await fetch(buildUrl(path, options.params), { ...options.init, signal: controller.signal });
    if (!response.ok) throw new ApiError(await describeError(response), response.status);
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(options.signal?.aborted ? "Request cancelled" : "The API did not respond in time", null);
    }
    throw new ApiError(`Cannot reach the RunoffPulse API at ${API_BASE_URL}. Is the backend running?`, null);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: (signal?: AbortSignal) => request<{ status: string; version: string }>("/api/health", { signal }),
  summary: (signal?: AbortSignal) => request<SummaryResponse>("/api/summary", { signal }),
  stations: (signal?: AbortSignal) => request<StationsResponse>("/api/stations", { signal }),
  station: (id: string, signal?: AbortSignal) => request<StationDetail>(`/api/stations/${encodeURIComponent(id)}`, { signal }),
  rivers: (signal?: AbortSignal) => request<FeatureCollection<RiverProps>>("/api/rivers", { signal }),
  catchment: (signal?: AbortSignal) => request<CatchmentResponse>("/api/catchment", { signal }),
  waterbodies: (signal?: AbortSignal) => request<FeatureCollection<WaterbodyProps>>("/api/waterbodies", { signal }),
  hydrometric: (signal?: AbortSignal) => request<HydroResponse>("/api/hydrometric", { signal }),
  hydroSeries: (station: string, signal?: AbortSignal) =>
    request<{ station_number: string; retrieved_at: string; values: { datetime_utc: string; value: number }[] }>(
      `/api/hydrometric/${encodeURIComponent(station)}/series`,
      { signal },
    ),
  rainfall: (params: { start?: string; end?: string; resolution?: "daily" | "hourly" }, signal?: AbortSignal) =>
    request<RainfallResponse>("/api/rainfall", { params, signal }),
  waterQuality: (
    params: { station?: string; indicator?: string; start?: string; end?: string; unit?: string },
    signal?: AbortSignal,
  ) => request<WaterQualityResponse>("/api/water-quality", { params, signal }),
  risk: (asOf?: string, signal?: AbortSignal) => request<RiskResponse>("/api/risk", { params: { as_of: asOf }, signal }),
  aquaculture: (signal?: AbortSignal) => request<AquacultureResponse>("/api/aquaculture", { signal }),
  alerts: (signal?: AbortSignal) => request<AlertsResponse>("/api/alerts", { signal }),
  predictions: (date?: string, signal?: AbortSignal) => request<PredictionsResponse>("/api/predictions", { params: { date }, signal }),
  model: (signal?: AbortSignal) => request<ModelCard>("/api/model", { signal }),
  backtest: (signal?: AbortSignal) => request<BacktestResponse>("/api/model/backtest", { signal }),
  sources: (signal?: AbortSignal) => request<SourcesResponse>("/api/sources", { signal }),
  reports: (page = 1, pageSize = 20, signal?: AbortSignal) =>
    request<ReportPage>("/api/reports", { params: { page, page_size: pageSize }, signal }),
  createReport: (form: FormData) => request<Report>("/api/reports", { init: { method: "POST", body: form } }),
  reportPhotoUrl: (id: string) => buildUrl(`/api/reports/${encodeURIComponent(id)}/photo`),
};
