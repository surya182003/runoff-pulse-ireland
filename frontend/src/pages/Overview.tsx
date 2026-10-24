import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CircleMarker, Tooltip as MapTooltip } from "react-leaflet";
import { ArrowRight, CloudRain, Database, ShieldAlert, Waves } from "lucide-react";
import { api } from "../api/client";
import type { AreaScreening, Classification, RiskResponse } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, ClassificationBadge, CLASSIFICATION_META, ErrorState, LoadingState, PageHeader, StatTile } from "../components/ui";
import { BaseMap, pointLatLng } from "../components/map/MapParts";
import { CatchmentLayer, ShellfishLayer, WaterbodyLayer } from "../components/map/Layers";
import { PredictionBadge } from "../components/PredictionBadge";
import { ScenarioTabs } from "../components/ScenarioTabs";
import { SCENARIOS } from "../lib/events";
import { areaName, areaType, formatDate, formatDateTime } from "../lib/format";

const SEVERITY: Classification[] = ["ELEVATED_SCREENING_RISK", "POTENTIAL_RUNOFF_RISK", "NO_ELEVATED_SIGNAL", "INSUFFICIENT_DATA"];

function overallStatus(r: RiskResponse): Classification {
  return SEVERITY.find((c) => (r.counts[c] ?? 0) > 0) ?? "INSUFFICIENT_DATA";
}

function headline(r: RiskResponse): string {
  const total = r.areas.length;
  const attention = (r.counts.ELEVATED_SCREENING_RISK ?? 0) + (r.counts.POTENTIAL_RUNOFF_RISK ?? 0);
  const high = r.shared_inputs.gauges.readings.filter((g) => (g.percentile_30d ?? 0) >= 0.9).length;
  const rain = r.shared_inputs.rainfall.window_48h.total_mm;
  const rainText = rain === null ? "Rainfall data is incomplete" : rain >= 15 ? `Heavy rain (${rain.toFixed(0)} mm in 2 days)` : rain >= 5 ? `Moderate rain (${rain.toFixed(0)} mm in 2 days)` : `Little rain (${rain.toFixed(1)} mm in 2 days)`;
  const riverText = high === 0 ? "rivers are at normal levels" : `${high} river gauges are running high`;
  const areaText = attention === 0 ? `none of the ${total} coastal areas need extra attention` : `${attention} of ${total} coastal areas need attention`;
  return `${rainText}, ${riverText}, and ${areaText}.`;
}

function StatusHero({ r, description }: { r: RiskResponse; description: string }) {
  const status = overallStatus(r);
  const meta = CLASSIFICATION_META[status];
  const Icon = meta.Icon;
  const replay = r.mode === "HISTORICAL_REPLAY";
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl" style={{ background: `${meta.fill}1f`, color: meta.color }}>
          <Icon className="h-7 w-7" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {replay ? `Replay · ${formatDate(r.as_of)}` : "Cork Harbour & coast · now"}
          </div>
          <div className="mt-0.5 text-2xl font-semibold tracking-tight" style={{ color: meta.color }}>
            {status === "NO_ELEVATED_SIGNAL" ? "Normal conditions" : status === "INSUFFICIENT_DATA" ? "Not assessed" : meta.label}
          </div>
          <p className="mt-1 text-sm text-slate-700">{headline(r)}</p>
          {replay && <p className="mt-1 text-xs text-slate-500">{description}</p>}
        </div>
        <Link to="/map" className="btn-secondary shrink-0 self-start sm:self-center">
          Open coastal map <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </section>
  );
}

function AreaList({ areas }: { areas: AreaScreening[] }) {
  const attention = areas.filter((a) => a.classification === "ELEVATED_SCREENING_RISK" || a.classification === "POTENTIAL_RUNOFF_RISK");
  const shown = attention.length ? attention : areas;
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">
        {attention.length ? `${attention.length} areas need attention:` : "All coastal areas are normal. Examples:"}
      </p>
      <ul className="max-h-[300px] divide-y divide-slate-100 overflow-y-auto">
        {shown.slice(0, 40).map((a) => (
          <li key={a.area_id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
            <span className="min-w-0">
              <span className="block truncate font-medium text-navy-900">{areaName(a.name)}</span>
              <span className="text-slate-500">{areaType(a.area_type)}</span>
            </span>
            <ClassificationBadge value={a.classification} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Overview() {
  // ?scenario=sep2026 opens a replay directly (handy for demos and screenshots).
  const [scenario, setScenario] = useState(
    () => SCENARIOS.find((s) => s.id === new URLSearchParams(window.location.search).get("scenario")) ?? SCENARIOS[0],
  );
  const risk = useApi((s) => api.risk(scenario.asOf, s), [scenario.id]);
  const prediction = useApi((s) => api.predictions(scenario.asOf, s), [scenario.id]);
  const catchment = useApi((s) => api.catchment(s));
  const waterbodies = useApi((s) => api.waterbodies(s));
  const aquaculture = useApi((s) => api.aquaculture(s));
  const hydro = useApi((s) => api.hydrometric(s));
  const alerts = useApi((s) => api.alerts(s));
  const sources = useApi((s) => api.sources(s));

  const screening = useMemo(() => new Map<string, AreaScreening>((risk.data?.areas ?? []).map((a) => [a.area_id, a])), [risk.data]);
  const shellfish = useMemo(() => {
    if (!aquaculture.data) return null;
    const fc = aquaculture.data.shellfish_waters;
    return { ...fc, features: fc.features.map((f) => ({ ...f, properties: { ...f.properties, screening: screening.get(f.properties.area_id) ?? null } })) };
  }, [aquaculture.data, screening]);
  const gaugeLevels = useMemo(() => new Map((risk.data?.shared_inputs.gauges.readings ?? []).map((g) => [g.station_number, g])), [risk.data]);

  const r = risk.data;
  const readings = r?.shared_inputs.gauges.readings.filter((g) => g.percentile_30d !== null) ?? [];
  const highRivers = readings.filter((g) => (g.percentile_30d ?? 0) >= 0.9).length;
  const attention = r ? (r.counts.ELEVATED_SCREENING_RISK ?? 0) + (r.counts.POTENTIAL_RUNOFF_RISK ?? 0) : 0;
  const topBeach = prediction.data?.predictions.find((p) => p.probability !== null);

  return (
    <>
      <PageHeader
        title="Coastal water status"
        subtitle="Rainfall, rivers and coastal waters around Cork Harbour, Kinsale and Youghal, combined to show where land runoff may be reaching the sea."
        actions={<ScenarioTabs value={scenario} onChange={setScenario} />}
      />

      {risk.loading && !r ? (
        <LoadingState label="Checking conditions…" />
      ) : risk.error ? (
        <ErrorState message={risk.error} onRetry={risk.reload} />
      ) : r ? (
        <>
          <StatusHero r={r} description={scenario.description} />

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Rain, last 2 days"
              icon={<CloudRain className="h-3.5 w-3.5" />}
              value={r.shared_inputs.rainfall.window_48h.total_mm === null ? "—" : `${r.shared_inputs.rainfall.window_48h.total_mm} mm`}
              sub="Met Éireann, Cork Airport"
            />
            <StatTile
              label="Rivers running high"
              icon={<Waves className="h-3.5 w-3.5" />}
              value={readings.length ? `${highRivers} of ${readings.length}` : "—"}
              sub={readings.length ? "OPW river gauges above their usual 30-day range" : "No river records for this date"}
            />
            <StatTile
              label="Coastal areas needing attention"
              icon={<ShieldAlert className="h-3.5 w-3.5" />}
              value={`${attention} of ${r.areas.length}`}
              sub="Estuaries, bays and shellfish waters"
            />
            <StatTile
              label="Beach water forecast (AI)"
              value={topBeach?.probability != null ? `${(topBeach.probability * 100).toFixed(0)}%` : "—"}
              sub={
                topBeach?.probability != null
                  ? `Highest chance of a failed bacteria test: ${topBeach.beach_name}${prediction.data?.status === "OUT_OF_SEASON" ? " (off-season estimate)" : ""}`
                  : "Not available for this date"
              }
            />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
            <Card title="Coastal areas and rivers" bodyClassName="p-3">
              <BaseMap height={440} center={[51.82, -8.25]} zoom={10}>
                {catchment.data && <CatchmentLayer data={catchment.data} showSub={false} />}
                {waterbodies.data && (
                  <WaterbodyLayer
                    data={{ ...waterbodies.data, features: waterbodies.data.features.filter((f) => screening.has(f.properties.EU_CD)) }}
                    screening={screening}
                  />
                )}
                {shellfish && <ShellfishLayer data={shellfish} />}
                {hydro.data?.features
                  .filter((f) => f.properties.sensor_ref === "0001" && gaugeLevels.has(f.properties.station_number))
                  .map((f) => {
                    const ll = pointLatLng(f.geometry);
                    const g = gaugeLevels.get(f.properties.station_number)!;
                    if (!ll) return null;
                    const high = (g.percentile_30d ?? 0) >= 0.9;
                    return (
                      <CircleMarker key={f.properties.station_ref} center={ll} radius={high ? 6 : 4}
                        pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: high ? "#d03b3b" : "#2a78d6", fillOpacity: 0.95 }}>
                        <MapTooltip>
                          {f.properties.station_name}: {g.percentile_30d === null ? "no level record" : high ? "running high" : "normal level"}
                        </MapTooltip>
                      </CircleMarker>
                    );
                  })}
              </BaseMap>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 px-1 text-[11px] text-slate-600">
                {(["NO_ELEVATED_SIGNAL", "POTENTIAL_RUNOFF_RISK", "ELEVATED_SCREENING_RISK"] as Classification[]).map((c) => (
                  <span key={c} className="flex items-center gap-1.5">
                    <span className="h-2.5 w-3.5 rounded-sm" style={{ background: CLASSIFICATION_META[c].fill }} /> {CLASSIFICATION_META[c].label}
                  </span>
                ))}
                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#2a78d6]" /> River gauge, normal</span>
                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#d03b3b]" /> River gauge, high</span>
              </div>
            </Card>
            <Card title="Coastal areas">
              <AreaList areas={r.areas} />
            </Card>
          </div>
        </>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Beach water forecast (AI)" actions={<Link to="/prediction" className="text-xs font-medium text-ocean-600 hover:underline">Open</Link>}>
          <Async state={prediction} loadingLabel="Running model…">
            {(p) =>
              p.status === "UNAVAILABLE" ? (
                <p className="text-xs text-slate-600">{p.message}</p>
              ) : (
                <div className="space-y-2 text-xs">
                  {p.predictions.slice(0, 3).map((b) => (
                    <div key={b.beach_id} className="flex items-center justify-between gap-2">
                      <span className="truncate text-slate-700">{b.beach_name}</span>
                      <span className="flex items-center gap-2">
                        <span className="tabular font-semibold text-navy-900">{b.probability !== null ? `${(b.probability * 100).toFixed(0)}%` : "—"}</span>
                        {b.band && <PredictionBadge band={b.band} />}
                      </span>
                    </div>
                  ))}
                  <p className="text-[11px] text-slate-500">Chance a water sample would fail the EU bacteria limit{p.status === "OUT_OF_SEASON" ? " (off-season: rough guide only)" : ""}.</p>
                </div>
              )
            }
          </Async>
        </Card>
        <Card title="Official alerts">
          <Async state={alerts}>
            {(a) => (
              <div className="space-y-1.5 text-xs text-slate-700">
                <p>
                  <strong className="text-navy-900">{a.official_alerts.length}</strong> active EPA bathing-water alerts in the area.
                </p>
                <p className="text-slate-500">
                  RunoffPulse flags are early warnings for review. Official decisions stay with the EPA, HSE and the Sea-Fisheries Protection Authority.
                </p>
              </div>
            )}
          </Async>
        </Card>
        <Card title="Data" actions={<Link to="/sources" className="text-xs font-medium text-ocean-600 hover:underline">Sources</Link>}>
          <div className="flex gap-3 text-xs text-slate-700">
            <Database className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden />
            <div className="space-y-1">
              <p>Live and archived open data from <strong>EPA</strong>, <strong>Met Éireann</strong>, <strong>OPW</strong> and <strong>beaches.ie</strong>. No simulated values.</p>
              <p className="text-slate-500">Last updated {formatDateTime(sources.data?.live_feeds[0]?.retrieved_at ?? sources.data?.manifest_updated_at)}</p>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
