import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, ShieldOff } from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import {
  Async,
  Card,
  ClassificationBadge,
  DataStatusBadge,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  PageHeader,
} from "../components/ui";
import { BaseMap } from "../components/map/MapParts";
import { CatchmentLayer, GaugeMarkers, ShellfishLayer, StationMarkers } from "../components/map/Layers";
import { ScreeningPanel } from "../components/ScreeningPanel";
import { buildBriefing, downloadText } from "../lib/briefing";
import { formatDateTime } from "../lib/format";

export default function Aquaculture() {
  const aqua = useApi((s) => api.aquaculture(s));
  const risk = useApi((s) => api.risk(undefined, s));
  const stations = useApi((s) => api.stations(s));
  const catchment = useApi((s) => api.catchment(s));
  const hydro = useApi((s) => api.hydrometric(s));
  const [selected, setSelected] = useState<string | null>(null);

  const areas = useMemo(() => aqua.data?.shellfish_waters.features ?? [], [aqua.data]);
  useEffect(() => {
    if (!selected && areas.length) {
      const linked = areas.find((a) => a.properties.linked_to_study_catchment) ?? areas[0];
      setSelected(linked.properties.area_id);
    }
  }, [areas, selected]);
  const area = areas.find((a) => a.properties.area_id === selected);
  const nearbyIds = new Set(area?.properties.nearby_monitoring_stations.map((s) => s.StationID) ?? []);

  return (
    <>
      <PageHeader
        title="Shellfish Watch"
        subtitle="Early warning for oyster and mussel waters. Shows where rain-driven runoff from the land may be reaching protected shellfish areas, so operators can plan extra checks."
        actions={
          area &&
          aqua.data && (
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                downloadText(
                  `runoffpulse-briefing-${area.properties.area_id}-${new Date().toISOString().slice(0, 10)}.md`,
                  buildBriefing(area, aqua.data!, risk.data),
                )
              }
            >
              <Download className="h-4 w-4" aria-hidden /> Export briefing
            </button>
          )
        }
      />

      <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="card flex gap-3 border-amber-200 bg-amber-50/60 p-4">
          <ShieldOff className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" aria-hidden />
          <div className="text-sm">
            <div className="font-semibold text-amber-950">Official harvesting advisories: not connected</div>
            <p className="mt-1 text-xs leading-relaxed text-amber-900">
              {aqua.data?.official_advisories.message ??
                "RunoffPulse never infers closures. Check the SFPA and Marine Institute for official harvesting status."}
            </p>
            <div className="mt-2 flex flex-wrap gap-3">
              {aqua.data?.official_advisories.sources.map((s) => (
                <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-amber-900 underline">
                  {s.name} <ExternalLink className="h-3 w-3" />
                </a>
              ))}
            </div>
          </div>
        </div>
        <div className="card p-4 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-navy-900">Classified production areas (SFPA)</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
              {aqua.data?.production_areas.available ? "Loaded" : "Layer unavailable"}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">{aqua.data?.production_areas.note ?? "…"}</p>
        </div>
      </div>

      {aqua.loading && !aqua.data ? (
        <LoadingState label="Loading shellfish waters…" />
      ) : aqua.error ? (
        <ErrorState message={aqua.error} onRetry={aqua.reload} />
      ) : !aqua.data?.shellfish_waters_available || areas.length === 0 ? (
        <EmptyState title="Shellfish-water boundaries are not available">
          Run scripts/acquire_all.py to download EPA designated shellfish waters. The interface will display them once available.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_420px]">
          <div className="space-y-4">
            <Card title="Shellfish waters map" bodyClassName="p-3" actions={<DataStatusBadge status="OFFICIAL_DESIGNATION" />}>
              <BaseMap height={460} center={[51.8, -8.2]} zoom={10}>
                {catchment.data && <CatchmentLayer data={catchment.data} showSub={false} />}
                <ShellfishLayer data={aqua.data.shellfish_waters} onSelect={setSelected} />
                {stations.data && (
                  <StationMarkers features={stations.data.features.filter((f) => nearbyIds.has(f.properties.StationID))} />
                )}
                {hydro.data && <GaugeMarkers features={hydro.data.features.filter((f) => f.properties.in_study_catchment)} />}
              </BaseMap>
              <p className="mt-2 text-[11px] text-slate-500">
                Source: EPA WFD Register of Protected Areas (Shellfish Waters). These designations are not the SFPA harvest-classified production
                areas. Coloured fill = screening result; teal outline = designated boundary. Station dots are EPA stations within ~3 km of the
                selected area (proximity only).
              </p>
            </Card>

            <Card title="Protected shellfish waters" bodyClassName="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-xs">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Area</th>
                    <th className="px-4 py-2 font-medium">Water body (official health rating)</th>
                    <th className="px-4 py-2 font-medium">Fed by river catchment</th>
                    <th className="px-4 py-2 font-medium">Runoff status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {areas.map((a) => (
                    <tr
                      key={a.properties.area_id}
                      className={`cursor-pointer hover:bg-slate-50 ${a.properties.area_id === selected ? "bg-ocean-50/60" : ""}`}
                      onClick={() => setSelected(a.properties.area_id)}
                    >
                      <td className="px-4 py-2 font-medium text-navy-900">{a.properties.name}</td>
                      <td className="px-4 py-2 text-slate-600">
                        {a.properties.parent_waterbody_name} ({a.properties.parent_waterbody_wfd_status ?? "unknown"})
                      </td>
                      <td className="px-4 py-2 text-slate-600">{a.properties.adjacent_hydrometric_area ?? "—"}</td>
                      <td className="px-4 py-2">
                        {a.properties.screening ? <ClassificationBadge value={a.properties.screening.classification} /> : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="space-y-4">
            {area ? (
              <>
                <Card title={area.properties.name} actions={<span className="text-[11px] text-slate-500">{area.properties.area_id}</span>}>
                  {area.properties.screening ? (
                    <ScreeningPanel area={area.properties.screening} />
                  ) : (
                    <EmptyState title="No screening result" />
                  )}
                </Card>
                <Card title="Nearby EPA monitoring stations">
                  {area.properties.nearby_monitoring_stations.length ? (
                    <ul className="divide-y divide-slate-100 text-xs">
                      {area.properties.nearby_monitoring_stations.map((s) => (
                        <li key={s.StationID} className="flex items-center justify-between gap-2 py-1.5">
                          <span>
                            <span className="font-medium text-navy-900">{s.StationName}</span>{" "}
                            <span className="text-slate-500">({s.StationType.replace("_STATION", "").toLowerCase()})</span>
                          </span>
                          <span className="tabular whitespace-nowrap text-slate-500">{s.inside_area ? "inside" : `~${s.approx_distance_km} km`}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState title="No EPA stations within ~3 km" />
                  )}
                  <p className="mt-2 text-[11px] text-slate-500">
                    Lab results from these stations are not yet connected.
                  </p>
                </Card>
                <Async state={risk}>
                  {(r) => (
                    <Notice>
                      Based on {r.shared_inputs.rainfall.window_48h.total_mm ?? "—"} mm of rain in the last 2 days (Cork Airport) and{" "}
                      {r.shared_inputs.gauge_count_usable} live river gauges across the Lee, Bandon and Blackwater. Updated {formatDateTime(r.calculated_at)}.
                    </Notice>
                  )}
                </Async>
              </>
            ) : (
              <EmptyState title="Select an area" />
            )}
          </div>
        </div>
      )}
    </>
  );
}
