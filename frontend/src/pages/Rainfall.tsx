import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { DailyRain, HourlyRain } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, DataStatusBadge, EmptyState, Notice, PageHeader, SourceLine, StatTile } from "../components/ui";
import { RainfallChart } from "../components/RainfallChart";
import { formatAge, formatDate, formatDateTime, formatNumber, isoDate } from "../lib/format";

const PRESETS = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
];

type RiverState = "Normal" | "Raised" | "High";
const STATE_CLS: Record<RiverState, string> = {
  Normal: "bg-reef-50 text-reef-700",
  Raised: "bg-amber-50 text-amber-900",
  High: "bg-red-50 text-red-800",
};

function riverState(percentile: number | null): RiverState {
  if ((percentile ?? 0) >= 0.9) return "High";
  if ((percentile ?? 0) >= 0.75) return "Raised";
  return "Normal";
}

/** Hourly bars on a true time axis, so hours with no report remain visible as empty space. */
function HourlyChart({ records, start, end }: { records: HourlyRain[]; start: string; end: string }) {
  const rows = records.map((r) => ({ t: Date.parse(r.datetime_utc), rain: r.rain_mm, src: r.source }));
  const domain = [Date.parse(`${start}T00:00:00Z`), Date.parse(`${end}T23:59:59Z`)];
  const ticks: number[] = [];
  for (let t = domain[0]; t <= domain[1]; t += 86400_000) ticks.push(t);
  return (
    <div style={{ height: 220 }} role="img" aria-label="Hourly rainfall bar chart for the last 7 days">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 14, right: 8, left: -8, bottom: 0 }} barSize={3}>
          <CartesianGrid vertical={false} stroke="#e1e0d9" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain}
            ticks={ticks}
            tickFormatter={(t: number) => formatDate(new Date(t).toISOString()).replace(/ \d{4}$/, "")}
            tick={{ fontSize: 11, fill: "#898781" }}
            tickLine={false}
            axisLine={{ stroke: "#c3c2b7" }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#898781" }}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip
            cursor={{ fill: "rgba(42,120,214,0.08)" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
                  <div className="font-medium">{formatDateTime(payload[0].payload.t)}</div>
                  <div className="tabular">{formatNumber(payload[0].payload.rain, 1, "mm")} in the hour</div>
                  <div className="text-slate-500">
                    {payload[0].payload.src === "met_eireann_hourly_archive" ? "Climate archive" : "Latest reports (provisional)"}
                  </div>
                </div>
              ) : null
            }
          />
          <Bar dataKey="rain" fill="#2a78d6" radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Rainfall() {
  const [days, setDays] = useState(90);
  const daily = useApi((s) => {
    const end = new Date();
    return api.rainfall({ start: isoDate(new Date(end.getTime() - days * 86400_000)), end: isoDate(end) }, s);
  }, [days]);
  const hourly = useApi((s) => {
    const end = new Date();
    return api.rainfall({ resolution: "hourly", start: isoDate(new Date(end.getTime() - 7 * 86400_000)), end: isoDate(end) }, s);
  });

  const risk = useApi((s) => api.risk(undefined, s));
  const rivers = {
    data: risk.data ? risk.data.shared_inputs.gauges.readings.filter((g) => g.percentile_30d !== null) : null,
  };

  return (
    <>
      <PageHeader
        title="Rain & Rivers"
        subtitle="Rain falls on the land, rivers carry the runoff to the coast. Rainfall from Met Éireann (Cork Airport) and live river levels from OPW gauges in the Lee, Bandon and Blackwater catchments."
        actions={<DataStatusBadge status="REAL_OBSERVATION" />}
      />

      <Async state={hourly} loadingLabel="Loading latest observations…">
        {(h) => (
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Latest hourly report"
              value={h.latest_observation ? formatNumber(h.latest_observation.rain_mm, 1, "mm") : "—"}
              sub={h.latest_observation ? `${formatDateTime(h.latest_observation.datetime_utc)} · ${formatAge(h.latest_observation.age_hours)}` : "No recent observation"}
            />
            <StatTile
              label="Last 24 hours"
              value={formatNumber(h.windows.last_24h.total_mm, 1, "mm")}
              sub={`${h.windows.last_24h.hours_with_data} of 24 hourly values present`}
            />
            <StatTile
              label="Last 48 hours"
              value={formatNumber(h.windows.last_48h.total_mm, 1, "mm")}
              sub={`${h.windows.last_48h.hours_with_data} of 48 hourly values present`}
            />
            <StatTile
              label="Rivers running high"
              value={rivers.data ? `${rivers.data.filter((g) => riverState(g.percentile_30d) === "High").length} of ${rivers.data.length}` : "—"}
              sub="Gauges above their usual 30-day range"
            />
          </div>
        )}
      </Async>

      <Card className="mb-4" title="River levels now" actions={<span className="text-[11px] text-slate-500">OPW live gauges</span>}>
        <Async state={risk} loadingLabel="Reading river gauges…">
          {(r) => {
            const readings = r.shared_inputs.gauges.readings.filter((g) => g.percentile_30d !== null);
            const groups = [...new Set(readings.map((g) => g.catchment ?? "Other"))];
            return readings.length ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                {groups.map((name) => {
                  const list = readings.filter((g) => (g.catchment ?? "Other") === name).sort((a, b) => (b.percentile_30d ?? 0) - (a.percentile_30d ?? 0));
                  return (
                    <div key={name}>
                      <h3 className="mb-1.5 text-xs font-semibold text-navy-900">
                        {name.replace(", Cork Harbour and Youghal Bay", "")} catchment{" "}
                        <span className="font-normal text-slate-500">· {list.length} gauges</span>
                      </h3>
                      <ul className="max-h-56 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
                        {list.map((g) => {
                          const state = riverState(g.percentile_30d);
                          return (
                            <li key={g.station_number} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
                              <span className="truncate text-slate-700">{g.station_name}</span>
                              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATE_CLS[state]}`}>{state}</span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No river readings available right now.</p>
            );
          }}
        </Async>
        <SourceLine>
          "High" means the river is higher than on 90% of the last 30 days; "Raised" means higher than on 75%. Dam-controlled and tidal gauges are left
          out because their levels follow dam releases or tides rather than rain.
        </SourceLine>
      </Card>

      <Card
        title="Daily rainfall (mm)"
        actions={
          <div className="flex gap-1" role="group" aria-label="Time range">
            {PRESETS.map((p) => (
              <button
                key={p.days}
                type="button"
                aria-pressed={days === p.days}
                onClick={() => setDays(p.days)}
                className={`btn px-2.5 py-1 text-xs ${days === p.days ? "bg-navy-900 text-white" : "border border-slate-300 bg-white text-navy-900 hover:bg-slate-50"}`}
              >
                {p.label}
              </button>
            ))}
          </div>
        }
      >
        <Async state={daily}>
          {(d) =>
            d.records.length ? (
              <>
                <RainfallChart records={d.records as DailyRain[]} height={280} />
                {(d.records as DailyRain[]).some((r) => !r.complete) && (
                  <div className="mt-2">
                    <Notice>
                      Some recent days have no complete record (shown as gaps). The Met Éireann climate archive runs to{" "}
                      {formatDate(d.archive_periods.met_rainfall_daily?.[1])}; after that, RunoffPulse only has the hourly reports it has
                      captured and never fills gaps with estimates.
                    </Notice>
                  </div>
                )}
                <SourceLine>{d.notes.join(" ")}</SourceLine>
              </>
            ) : (
              <EmptyState title="No rainfall data for this range" />
            )
          }
        </Async>
      </Card>

      <Card className="mt-4" title="Hourly rainfall, last 7 days (mm per hour)">
        <Async state={hourly}>
          {(h) =>
            h.records.length ? (
              <>
                <HourlyChart records={h.records as HourlyRain[]} start={h.start} end={h.end} />
                <SourceLine>
                  {h.records.length} hourly values in the last 7 days. Hours without a report are absent, not zero. Report times are converted from
                  Irish local time to UTC.
                </SourceLine>
              </>
            ) : (
              <EmptyState title="No hourly observations in the last 7 days" />
            )
          }
        </Async>
      </Card>
    </>
  );
}
