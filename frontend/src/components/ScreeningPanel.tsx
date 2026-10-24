import { CloudRain, Droplets, ListChecks, Waves } from "lucide-react";
import type { AreaScreening } from "../api/types";
import { formatDateTime } from "../lib/format";
import { ClassificationBadge } from "./ui";

function level(value: number | null, labels: [string, string, string]): string {
  if (value === null) return "Not available";
  if (value >= 0.5) return labels[2];
  if (value >= 0.2) return labels[1];
  return labels[0];
}

/** Plain-language explanation of one area's result; technical detail is collapsed. */
export function ScreeningPanel({ area }: { area: AreaScreening }) {
  const rain = area.inputs.rainfall;
  const checks = [
    {
      Icon: CloudRain,
      label: "Rainfall",
      value: rain?.total_48h_mm != null ? `${level(area.components.rainfall, ["Low", "Moderate", "Heavy"])} · ${rain.total_48h_mm} mm in 2 days` : "Not available",
    },
    {
      Icon: Waves,
      label: "River levels",
      value: `${level(area.components.river_response, ["Normal", "Slightly raised", "High"])}${area.inputs.gauges ? ` · ${area.inputs.gauges} gauges` : ""}`,
    },
    {
      Icon: Droplets,
      label: "Recent beach tests",
      value: area.components.water_quality === null ? "None this week (sampled June to September)" : area.components.water_quality >= 0.5 ? "A nearby beach failed" : "Passed",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <ClassificationBadge value={area.classification} size="md" />
        <p className="text-sm leading-relaxed text-navy-900">{area.summary}</p>
      </div>

      <div>
        <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">What we checked</h4>
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {checks.map(({ Icon, label, value }) => (
            <li key={label} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
              <span className="flex items-center gap-2 text-slate-600">
                <Icon className="h-3.5 w-3.5 text-ocean-600" aria-hidden /> {label}
              </span>
              <span className="text-right font-medium text-navy-900">{value}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg bg-slate-50 p-3">
        <h4 className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-navy-900">
          <ListChecks className="h-3.5 w-3.5" aria-hidden /> Suggested action
        </h4>
        <p className="text-xs text-slate-700">{area.next_step}</p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {area.catchment && (
          <>
            <dt>Fed by</dt>
            <dd className="text-slate-700">{area.catchment} river catchment</dd>
          </>
        )}
        {area.context.parent_wfd_status && (
          <>
            <dt>Water health</dt>
            <dd className="text-slate-700">
              {area.context.parent_wfd_status} (official EPA rating, {area.context.parent_wfd_status_period?.replace("SW ", "")})
            </dd>
          </>
        )}
      </dl>

      <details className="group rounded-lg border border-slate-200 text-xs">
        <summary className="cursor-pointer select-none px-3 py-2 font-medium text-slate-600 hover:text-navy-900">Technical details</summary>
        <div className="space-y-2 border-t border-slate-100 px-3 py-2 text-slate-600">
          <p>
            Score {area.score === null ? "not calculated" : area.score.toFixed(2)} · confidence {area.confidence.toLowerCase()} · method{" "}
            {area.engine_version}
          </p>
          <p>
            Components (0–1): rainfall {area.components.rainfall ?? "n/a"}, rivers {area.components.river_response ?? "n/a"}, beach tests{" "}
            {area.components.water_quality ?? "n/a"}; weights {Object.values(area.weights).join(" / ")}.
          </p>
          {area.evidence.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4">
              {area.evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          {area.missing_inputs.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4 text-slate-500">
              {area.missing_inputs.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <p>Link to catchment: {area.linkage.basis}. Calculated {formatDateTime(area.calculated_at)}.</p>
        </div>
      </details>
    </div>
  );
}
