import { Component, type ReactNode } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import { AlertTriangle } from "lucide-react";

export const CORK_CENTER: LatLngExpression = [51.86, -8.42];
export const STUDY_BOUNDS: LatLngBoundsExpression = [
  [51.7, -9.42],
  [52.11, -7.78],
];

/** Keeps a map failure (tiles, bad geometry, Leaflet error) from breaking the rest of the page. */
export class MapErrorBoundary extends Component<{ children: ReactNode; height?: number | string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          style={{ height: this.props.height ?? 400 }}
          className="flex flex-col items-center justify-center gap-2 rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-600"
        >
          <AlertTriangle className="h-5 w-5 text-status-serious" aria-hidden />
          The map could not be displayed. Other data on this page is unaffected.
          <button type="button" className="btn-secondary" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function BaseMap({
  height = 480,
  children,
  center = CORK_CENTER,
  zoom = 10,
  className = "",
}: {
  height?: number | string;
  children?: ReactNode;
  center?: LatLngExpression;
  zoom?: number;
  className?: string;
}) {
  return (
    <MapErrorBoundary height={height}>
      <div style={{ height }} className={`overflow-hidden rounded-lg border border-slate-200 ${className}`} data-testid="map">
        <MapContainer center={center} zoom={zoom} minZoom={8} maxBounds={[[50.8, -11], [53.2, -6]]} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {children}
        </MapContainer>
      </div>
    </MapErrorBoundary>
  );
}

/** Safely read [lon, lat] from a GeoJSON Point; returns null for anything malformed. */
export function pointLatLng(geometry: { type: string; coordinates: unknown } | null | undefined): [number, number] | null {
  if (!geometry || geometry.type !== "Point" || !Array.isArray(geometry.coordinates)) return null;
  const [lon, lat] = geometry.coordinates as unknown[];
  if (typeof lon !== "number" || typeof lat !== "number" || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (lat < 51 || lat > 55.6 || lon < -11 || lon > -5) return null;
  return [lat, lon];
}

export const STATION_TYPE_STYLE: Record<string, { color: string; label: string }> = {
  RIVER_STATION: { color: "#2a78d6", label: "River" },
  TRANSITIONAL_STATION: { color: "#1baf7a", label: "Transitional (estuary)" },
  COASTAL_STATION: { color: "#6250d6", label: "Coastal" },
  LAKE_STATION: { color: "#e87ba4", label: "Lake" },
  GROUNDWATER_STATION: { color: "#8a6d3b", label: "Groundwater" },
};

export function LegendSwatch({ color, label, shape = "dot", dashed = false }: { color: string; label: string; shape?: "dot" | "line" | "area" | "ring"; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-700">
      {shape === "dot" && <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: color }} />}
      {shape === "ring" && <span className="h-2.5 w-2.5 rounded-full border-2 bg-white" style={{ borderColor: color }} />}
      {shape === "line" && <span className="h-0.5 w-4" style={{ background: color }} />}
      {shape === "area" && (
        <span
          className="h-3 w-4 rounded-sm"
          style={{ background: `${color}33`, border: `1.5px ${dashed ? "dashed" : "solid"} ${color}` }}
        />
      )}
      {label}
    </span>
  );
}
