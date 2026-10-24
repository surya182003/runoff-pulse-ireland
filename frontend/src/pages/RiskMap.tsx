import { useMemo, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import { api } from "../api/client";
import type { AreaScreening, Classification } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, ClassificationBadge, CLASSIFICATION_META, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { BaseMap, LegendSwatch, pointLatLng, STATION_TYPE_STYLE } from "../components/map/MapParts";
import {
  BathingMarkers,
  CatchmentLayer,
  GaugeMarkers,
  ReportMarkers,
  RiverLayer,
  ShellfishLayer,
  StationMarkers,
  WaterbodyLayer,
} from "../components/map/Layers";
import { ScreeningPanel } from "../components/ScreeningPanel";
import { ScenarioTabs } from "../components/ScenarioTabs";
import { SCENARIOS, type Scenario } from "../lib/events";
import { areaName, formatDate, isoDate } from "../lib/format";

const LAYERS = [
  { id: "screening", label: "Estuaries & bays (risk colour)" },
  { id: "shellfish", label: "Shellfish waters" },
  { id: "rivers", label: "Rivers" },
  { id: "gauges", label: "River & tide gauges (live)" },
  { id: "bathing", label: "Bathing beaches" },
  { id: "stations", label: "EPA monitoring stations" },
  { id: "catchment", label: "River Lee catchment boundary" },
  { id: "reports", label: "Community reports" },
] as const;
type LayerId = (typeof LAYERS)[number]["id"];

function StationPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const state = useApi((s) => api.station(id, s), [id]);
  return (
    <Card
      title="Monitoring station"
      actions={
        <button type="button" aria-label="Close station detail" className="btn-secondary px-2 py-1" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </button>
      }
    >
      <Async state={state}>
        {(d) => {
          const p = d.station.properties;
          return (
            <div className="space-y-3 text-sm">
              <div>
                <div className="font-semibold text-navy-900">{p.StationName}</div>
                <div className="text-xs text-slate-500">
                  {STATION_TYPE_STYLE[p.StationType]?.label ?? p.StationType} station · {p.StationID}
                </div>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <dt className="text-slate-500">Water body</dt>
                <dd>{p.EntityName ?? "—"}</dd>
                <dt className="text-slate-500">Water type</dt>
                <dd>{p.TypeofWaterMonitored ?? "—"}</dd>
                <dt className="text-slate-500">Operated for</dt>
                <dd>{p.LocalAuthority ?? "—"}</dd>
              </dl>
              {d.nearby_hydrometric_gauges.length > 0 && (
                <div className="text-xs">
                  <div className="mb-1 font-semibold">Nearest river gauges</div>
                  <ul className="space-y-0.5 text-slate-700">
                    {d.nearby_hydrometric_gauges.slice(0, 3).map((g) => (
                      <li key={g.station_number}>
                        {g.station_name} · {g.distance_km} km
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-[11px] text-slate-500">Lab results for this station are not yet connected, so none are shown.</p>
              {d.links.catchments_ie_waterbody && (
                <a className="inline-flex items-center gap-1 text-xs font-medium text-ocean-600 hover:underline" href={d.links.catchments_ie_waterbody} target="_blank" rel="noreferrer">
                  Official waterbody page (catchments.ie) <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          );
        }}
      </Async>
    </Card>
  );
}

export default function RiskMap() {
  const [visible, setVisible] = useState<Record<LayerId, boolean>>({
    screening: true,
    shellfish: true,
    rivers: true,
    gauges: true,
    bathing: true,
    stations: false,
    catchment: true,
    reports: true,
  });
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set(Object.keys(STATION_TYPE_STYLE)));
  const [scenario, setScenario] = useState<Scenario>(SCENARIOS[0]);
  const [customDate, setCustomDate] = useState("");
  const [selectedStation, setSelectedStation] = useState<string | null>(null);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const asOf = customDate || scenario.asOf;

  const stations = useApi((s) => api.stations(s));
  const catchment = useApi((s) => api.catchment(s));
  const rivers = useApi((s) => api.rivers(s));
  const waterbodies = useApi((s) => api.waterbodies(s));
  const aquaculture = useApi((s) => api.aquaculture(s));
  const hydro = useApi((s) => api.hydrometric(s));
  const wq = useApi((s) => api.waterQuality({ start: isoDate(new Date()) }, s));
  const reports = useApi((s) => api.reports(1, 100, s));
  const risk = useApi((s) => api.risk(asOf || undefined, s), [asOf]);

  const screening = useMemo(() => new Map<string, AreaScreening>((risk.data?.areas ?? []).map((a) => [a.area_id, a])), [risk.data]);
  const shellfishWithScreening = useMemo(() => {
    if (!aquaculture.data) return null;
    return {
      ...aquaculture.data.shellfish_waters,
      features: aquaculture.data.shellfish_waters.features.map((f) => ({
        ...f,
        properties: { ...f.properties, screening: screening.get(f.properties.area_id) ?? null },
      })),
    };
  }, [aquaculture.data, screening]);
  const filteredStations = useMemo(
    () => (stations.data?.features ?? []).filter((f) => typeFilter.has(f.properties.StationType) && pointLatLng(f.geometry) !== null),
    [stations.data, typeFilter],
  );
  const selectedAreaData = selectedArea ? screening.get(selectedArea) : undefined;
  const toggle = (id: LayerId) => setVisible((v) => ({ ...v, [id]: !v[id] }));
  const layerError = [stations, catchment, rivers, waterbodies, aquaculture, hydro].find((s) => s.error);
  const attention = (risk.data?.areas ?? []).filter((a) => a.classification === "ELEVATED_SCREENING_RISK" || a.classification === "POTENTIAL_RUNOFF_RISK");

  return (
    <>
      <PageHeader
        title="Coastal Risk Map"
        subtitle="Each estuary, bay and shellfish water is coloured by how likely land runoff is to be reaching it. Click an area to see why."
        actions={
          <ScenarioTabs
            value={scenario}
            onChange={(s) => {
              setCustomDate("");
              setScenario(s);
            }}
          />
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[250px_1fr_360px]">
        <div className="space-y-4">
          <Card title="Show on map">
            <div className="space-y-1.5">
              {LAYERS.map((l) => (
                <label key={l.id} className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" className="h-4 w-4 accent-navy-900" checked={visible[l.id]} onChange={() => toggle(l.id)} />
                  {l.label}
                </label>
              ))}
            </div>
            <details className="mt-3 border-t border-slate-100 pt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600">Station types</summary>
              <div className="mt-2 space-y-1.5">
                {Object.entries(STATION_TYPE_STYLE).map(([type, s]) => (
                  <label key={type} className="flex cursor-pointer items-center justify-between gap-2 text-xs text-slate-700">
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-navy-900"
                        checked={typeFilter.has(type)}
                        onChange={() =>
                          setTypeFilter((prev) => {
                            const next = new Set(prev);
                            if (next.has(type)) next.delete(type);
                            else next.add(type);
                            return next;
                          })
                        }
                      />
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
                      {s.label}
                    </span>
                    <span className="tabular text-slate-400">{stations.data?.meta.station_types[type] ?? 0}</span>
                  </label>
                ))}
              </div>
            </details>
            <details className="mt-2 border-t border-slate-100 pt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600">Replay any date</summary>
              <label className="label mt-2" htmlFor="asof">Date (2023 onwards)</label>
              <input id="asof" type="date" className="input" max={isoDate(new Date())} min="2023-01-02" value={customDate} onChange={(e) => setCustomDate(e.target.value)} />
            </details>
          </Card>
        </div>

        <div className="min-w-0 space-y-3">
          {layerError && <ErrorState message={`Some map layers failed to load: ${layerError.error}`} onRetry={layerError.reload} />}
          {asOf && risk.data && (
            <div className="rounded-lg border border-ocean-100 bg-ocean-50 px-3 py-2 text-xs text-navy-800">
              Showing a replay for <strong>{formatDate(risk.data.as_of)}</strong>.{" "}
              {customDate ? "Built from recorded measurements for that day." : scenario.description}
            </div>
          )}
          <BaseMap height={600} center={[51.83, -8.25]} zoom={10}>
            {visible.catchment && catchment.data && <CatchmentLayer data={catchment.data} showSub={false} />}
            {visible.rivers && rivers.data && <RiverLayer data={rivers.data} />}
            {visible.screening && waterbodies.data && (
              <WaterbodyLayer
                data={{ ...waterbodies.data, features: waterbodies.data.features.filter((f) => screening.has(f.properties.EU_CD)) }}
                screening={screening}
                onSelect={setSelectedArea}
              />
            )}
            {visible.shellfish && shellfishWithScreening && <ShellfishLayer data={shellfishWithScreening} onSelect={setSelectedArea} />}
            {visible.bathing && wq.data && <BathingMarkers stations={wq.data.stations} />}
            {visible.stations && <StationMarkers features={filteredStations} selectedId={selectedStation} onSelect={setSelectedStation} />}
            {visible.gauges && hydro.data && <GaugeMarkers features={hydro.data.features} />}
            {visible.reports && reports.data && <ReportMarkers reports={reports.data.items} />}
          </BaseMap>
          <div className="card flex flex-wrap gap-x-5 gap-y-2 px-4 py-3" aria-label="Map legend">
            {(["NO_ELEVATED_SIGNAL", "POTENTIAL_RUNOFF_RISK", "ELEVATED_SCREENING_RISK", "INSUFFICIENT_DATA"] as Classification[]).map((k) => (
              <LegendSwatch key={k} shape="area" color={CLASSIFICATION_META[k].fill} dashed={k === "INSUFFICIENT_DATA"} label={CLASSIFICATION_META[k].label} />
            ))}
            <LegendSwatch shape="area" color="#0f8a73" label="Shellfish water" />
            <LegendSwatch shape="line" color="#3987e5" label="River" />
            <LegendSwatch shape="ring" color="#0b2545" label="River / tide gauge" />
            <LegendSwatch shape="ring" color="#eb6834" label="Bathing beach" />
          </div>
          <p className="text-[11px] text-slate-500">
            {visible.stations ? `${filteredStations.length} EPA monitoring stations shown. A station marks where water is sampled, not a problem. ` : ""}
            Colours come from live rainfall and river gauges and recent beach tests, combined by RunoffPulse.
          </p>
        </div>

        <div className="space-y-4">
          {selectedStation && <StationPanel id={selectedStation} onClose={() => setSelectedStation(null)} />}
          <Card
            title={selectedAreaData ? areaName(selectedAreaData.name) : "Coastal areas"}
            actions={
              selectedAreaData && (
                <button type="button" aria-label="Close area detail" className="btn-secondary px-2 py-1" onClick={() => setSelectedArea(null)}>
                  <X className="h-3.5 w-3.5" />
                </button>
              )
            }
          >
            {risk.loading && !risk.data ? (
              <LoadingState label="Checking conditions…" />
            ) : risk.error ? (
              <ErrorState message={risk.error} onRetry={risk.reload} />
            ) : selectedAreaData ? (
              <ScreeningPanel area={selectedAreaData} />
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-slate-500">
                  {attention.length
                    ? `${attention.length} of ${risk.data?.areas.length} areas need attention. Click one for details.`
                    : `All ${risk.data?.areas.length ?? ""} areas are normal. Click an area on the map or below for details.`}
                </p>
                <ul className="max-h-[480px] divide-y divide-slate-100 overflow-y-auto">
                  {(risk.data?.areas ?? []).map((a) => (
                    <li key={a.area_id}>
                      <button type="button" className="flex w-full items-center justify-between gap-2 py-1.5 text-left text-xs hover:bg-slate-50" onClick={() => setSelectedArea(a.area_id)}>
                        <span className="truncate text-slate-700">{areaName(a.name)}</span>
                        <ClassificationBadge value={a.classification} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
