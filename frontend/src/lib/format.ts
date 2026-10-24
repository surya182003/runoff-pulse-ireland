const dateTimeFmt = new Intl.DateTimeFormat("en-IE", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Dublin",
});
const dateFmt = new Intl.DateTimeFormat("en-IE", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : `${dateTimeFmt.format(d)} (Irish time)`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFmt.format(d);
}

export function formatAge(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "unknown age";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours < 48) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function formatNumber(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function titleCase(value: string): string {
  return value
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Plain display name for an EPA waterbody (drops reporting codes such as "(HAs 18;19;20)"). */
export function areaName(name: string): string {
  return name.replace(/\s*\(HAs?[^)]*\)/, "").trim();
}

/** Plain description of an area type for non-specialist readers. */
export function areaType(type: string): string {
  if (type.startsWith("Transitional")) return "Estuary";
  if (type.startsWith("Coastal")) return "Coastal water";
  if (type.startsWith("Designated shellfish")) return "Shellfish water";
  return type;
}

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
