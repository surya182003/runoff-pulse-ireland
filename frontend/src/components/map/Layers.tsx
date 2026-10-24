import { CircleMarker, GeoJSON, Popup, Tooltip } from "react-leaflet";
import type { Layer, PathOptions } from "leaflet";
import type {
  AreaScreening,
  BathingStation,
  CatchmentResponse,
  Feature,
  FeatureCollection,
  HydroProps,
  Report,
  RiverProps,
  ShellfishProps,
  StationProps,
  WaterbodyProps,
} from "../../api/types";
import { CLASSIFICATION_META } from "../ui";
import { escapeHtml } from "../../lib/escape";
import { areaName, formatDateTime, formatNumber, titleCase } from "../../lib/format";
import { pointLatLng, STATION_TYPE_STYLE } from "./MapParts";

type GJ = GeoJSON.GeoJsonObject;

export function CatchmentLayer({ data, showSub }: { data: CatchmentResponse; showSub: boolean }) {
  return (
    <>
      {showSub && (
        <GeoJSON
          key="sub"
          data={data.subcatchments as unknown as GJ}
          style={{ color: "#94a3b8", weight: 1, fillOpacity: 0, dashArray: "3 4" }}
          onEachFeature={(f: GeoJSON.Feature, layer: Layer) => {
            layer.bindTooltip(`Sub-catchment ${escapeHtml((f.properties as { Name: string }).Name)}`, { sticky: true });
          }}
        />
      )}
      <GeoJSON
        key="catchment"
        data={data.catchment as unknown as GJ}
        style={{ color: "#0b2545", weight: 2, fillColor: "#0b2545", fillOpacity: 0.03, dashArray: "6 4" }}
        interactive={false}
      />
    </>
  );
}

export function RiverLayer({ data }: { data: FeatureCollection<RiverProps> }) {
  return (
    <GeoJSON
      key={`rivers-${data.features.length}`}
      data={data as unknown as GJ}
      style={{ color: "#3987e5", weight: 1.6, opacity: 0.85 }}
      onEachFeature={(feat: GeoJSON.Feature, layer: Layer) => {
        const f = feat as unknown as Feature<RiverProps>;
        layer.bindTooltip(
          `<strong>${escapeHtml(titleCase(f.properties.Name.replace(/_\d+$/, "")))}</strong><br/>River health: ${escapeHtml(
            f.properties.wfd_status ?? "unknown",
          )} <span style="color:#64748b">(official EPA rating)</span>`,
          { sticky: true },
        );
      }}
    />
  );
}

function screeningStyle(screening: AreaScreening | undefined, base: PathOptions): PathOptions {
  if (!screening) return { ...base, color: "#94a3b8", fillColor: "#cbd5e1", fillOpacity: 0.15 };
  const meta = CLASSIFICATION_META[screening.classification];
  return {
    ...base,
    color: meta.color,
    fillColor: meta.fill,
    fillOpacity: { INSUFFICIENT_DATA: 0.12, NO_ELEVATED_SIGNAL: 0.16, POTENTIAL_RUNOFF_RISK: 0.32, ELEVATED_SCREENING_RISK: 0.38 }[
      screening.classification
    ],
    dashArray: screening.classification === "INSUFFICIENT_DATA" ? "4 4" : undefined,
  };
}

function screeningTooltip(name: string, kind: string, screening: AreaScreening | undefined): string {
  if (!screening) return `<strong>${escapeHtml(name)}</strong><br/>${escapeHtml(kind)}<br/>Not assessed`;
  const meta = CLASSIFICATION_META[screening.classification];
  return `<strong>${escapeHtml(areaName(name))}</strong> · ${escapeHtml(kind)}<br/><strong style="color:${meta.color}">${escapeHtml(
    meta.label,
  )}</strong><br/><span style="color:#475569">${escapeHtml(screening.summary)}</span><br/><span style="color:#94a3b8">Click for details</span>`;
}

export function WaterbodyLayer({
  data,
  screening,
  onSelect,
}: {
  data: FeatureCollection<WaterbodyProps>;
  screening: Map<string, AreaScreening>;
  onSelect?: (id: string) => void;
}) {
  return (
    <GeoJSON
      key={`wb-${data.features.length}-${screening.size}-${[...screening.values()].map((s) => s.classification).join("")}`}
      data={data as unknown as GJ}
      style={(f) => screeningStyle(screening.get((f as Feature<WaterbodyProps>).properties.EU_CD), { weight: 1.2 })}
      onEachFeature={(feat: GeoJSON.Feature, layer: Layer) => {
        const p = (feat as unknown as Feature<WaterbodyProps>).properties;
        layer.bindTooltip(
          screeningTooltip(p.NAME, p.waterbody_category === "Transitional" ? "Estuary" : "Coastal water", screening.get(p.EU_CD)),
          { sticky: true },
        );
        if (onSelect) layer.on("click", () => onSelect(p.EU_CD));
      }}
    />
  );
}

export function ShellfishLayer({
  data,
  onSelect,
}: {
  data: FeatureCollection<ShellfishProps>;
  onSelect?: (id: string) => void;
}) {
  return (
    <GeoJSON
      key={`sf-${data.features.length}-${data.features.map((f) => f.properties.screening?.classification).join("")}`}
      data={data as unknown as GJ}
      style={(f) => ({
        ...screeningStyle((f as Feature<ShellfishProps>).properties.screening ?? undefined, { weight: 2.5 }),
        color: "#0f8a73",
      })}
      onEachFeature={(feat: GeoJSON.Feature, layer: Layer) => {
        const p = (feat as unknown as Feature<ShellfishProps>).properties;
        layer.bindTooltip(screeningTooltip(p.name, "Shellfish water", p.screening ?? undefined), { sticky: true });
        if (onSelect) layer.on("click", () => onSelect(p.area_id));
      }}
    />
  );
}

export function StationMarkers({
  features,
  selectedId,
  onSelect,
}: {
  features: Feature<StationProps>[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  return (
    <>
      {features.map((f) => {
        const ll = pointLatLng(f.geometry);
        if (!ll) return null;
        const p = f.properties;
        const style = STATION_TYPE_STYLE[p.StationType] ?? { color: "#64748b", label: p.StationType };
        const selected = p.StationID === selectedId;
        return (
          <CircleMarker
            key={p.StationID}
            center={ll}
            radius={selected ? 8 : 4.5}
            pathOptions={{ color: "#ffffff", weight: selected ? 3 : 1.5, fillColor: style.color, fillOpacity: 0.95 }}
            eventHandlers={onSelect ? { click: () => onSelect(p.StationID) } : undefined}
          >
            <Tooltip>
              <strong>{p.StationName}</strong>
              <br />
              EPA {style.label.toLowerCase()} monitoring station
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

export function GaugeMarkers({ features }: { features: Feature<HydroProps>[] }) {
  const levels = features.filter((f) => f.properties.sensor_ref === "0001");
  return (
    <>
      {levels.map((f) => {
        const ll = pointLatLng(f.geometry);
        if (!ll) return null;
        const p = f.properties;
        const tidal = !p.catchment_name && !p.in_study_catchment;
        return (
          <CircleMarker
            key={`g-${p.station_ref}`}
            center={ll}
            radius={6}
            pathOptions={{ color: tidal ? "#6250d6" : "#0b2545", weight: 2, fillColor: "#ffffff", fillOpacity: 1 }}
          >
            <Tooltip>
              <strong>{p.station_name}</strong> · {tidal ? "coastal / tide gauge" : "river gauge"}
              <br />
              Water level {formatNumber(p.value, 2, "m")} · {formatDateTime(p.observed_at)}
              <br />
              <span className="text-slate-500">Live OPW reading{p.excluded_from_screening ? " · not used for risk (dam or tide controlled)" : ""}</span>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

export function BathingMarkers({ stations }: { stations: BathingStation[] }) {
  return (
    <>
      {stations.map((b) => (
        <CircleMarker
          key={b.beach_id}
          center={[b.lat, b.lon]}
          radius={6}
          pathOptions={{ color: "#eb6834", weight: 2.5, fillColor: "#ffffff", fillOpacity: 1 }}
        >
          <Tooltip>
            <strong>{b.beach_name}</strong> (bathing water)
            <br />
            Classification: {b.classification ?? "not classified"}
            {b.classification_year ? ` (${b.classification_year})` : ""}
            <br />
            Latest sample: {b.latest_sample_date ?? "none"}
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export function ReportMarkers({ reports }: { reports: Report[] }) {
  return (
    <>
      {reports.map((r) => (
        <CircleMarker
          key={r.id}
          center={[r.latitude, r.longitude]}
          radius={6}
          pathOptions={{ color: "#6250d6", weight: 2, dashArray: "2 2", fillColor: "#ede9fe", fillOpacity: 0.9 }}
        >
          <Popup>
            {/* Rendered as React text nodes: user content is never injected as HTML. */}
            <div className="max-w-[220px] space-y-1">
              <div className="text-xs font-semibold">{titleCase(r.category)}</div>
              <div className="text-xs">{r.description}</div>
              <div className="text-[11px] text-slate-500">Observed {formatDateTime(r.observed_at)}</div>
              <div className="text-[11px] font-medium text-violet-700">Citizen report · unverified</div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
