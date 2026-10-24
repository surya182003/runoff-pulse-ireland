import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { WQRecord } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, DataStatusBadge, EmptyState, Notice, PageHeader, SourceLine } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";

const SERIES: Record<string, string> = { "E. coli": "#2a78d6", "Intestinal enterococci": "#eb6834" };

interface Point {
  t: number;
  v: number;
  r: WQRecord;
}

function WQTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const { r } = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
      <div className="font-medium text-navy-900">
        {r.measurement} · {formatDate(r.observed_date)}
      </div>
      <div className="tabular text-slate-700">
        {r.value_raw} {r.unit}
        {r.qualifier ? " (censored value)" : ""}
      </div>
      <div className="text-slate-500">Official sample status: {r.sample_status ?? "—"}</div>
    </div>
  );
}

export default function WaterQuality() {
  const [station, setStation] = useState("");
  const [indicator, setIndicator] = useState("");
  const [unit, setUnit] = useState("");
  const [start, setStart] = useState("2019-01-01");
  const [end, setEnd] = useState("");

  const meta = useApi((s) => api.waterQuality({ start: "2100-01-01" }, s));
  useEffect(() => {
    if (!station && meta.data?.stations.length) {
      const preferred = meta.data.stations.find((b) => b.beach_name === "Fountainstown") ?? meta.data.stations[0];
      setStation(preferred.beach_id);
    }
  }, [meta.data, station]);

  const data = useApi(
    (s) => api.waterQuality({ station: station || undefined, indicator: indicator || undefined, unit: unit || undefined, start: start || undefined, end: end || undefined }, s),
    [station, indicator, unit, start, end],
  );
  const invalidRange = Boolean(start && end && start > end);

  const series = useMemo(() => {
    const grouped: Record<string, Point[]> = {};
    for (const r of data.data?.records ?? []) {
      if (r.value === null || !r.observed_date) continue;
      (grouped[r.measurement] ??= []).push({ t: Date.parse(`${r.observed_date}T00:00:00Z`), v: Math.max(1, r.value), r });
    }
    return grouped;
  }, [data.data]);

  const stationName = meta.data?.stations.find((b) => b.beach_id === station)?.beach_name;

  return (
    <>
      <PageHeader
        title="Water Quality"
        subtitle="Measured indicators that are genuinely available for the study area. Nothing is interpolated or estimated; seasonal gaps are shown as gaps."
      />

      <Card title="Filters" className="mb-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="label" htmlFor="wq-station">Station (bathing water)</label>
            <select id="wq-station" className="input" value={station} onChange={(e) => setStation(e.target.value)}>
              {meta.data?.stations.map((b) => (
                <option key={b.beach_id} value={b.beach_id}>
                  {b.beach_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="wq-indicator">Indicator</label>
            <select id="wq-indicator" className="input" value={indicator} onChange={(e) => setIndicator(e.target.value)}>
              <option value="">All indicators</option>
              {meta.data?.indicators.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="wq-unit">Unit</label>
            <select id="wq-unit" className="input" value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="">All units</option>
              {meta.data?.units.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="wq-start">From</label>
            <input id="wq-start" type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="wq-end">To</label>
            <input id="wq-end" type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>
        {invalidRange && <p className="mt-2 text-xs text-status-critical">"From" must be on or before "To".</p>}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title={`Bacteriological results${stationName ? ` · ${stationName}` : ""}`}
          actions={<DataStatusBadge status="REAL_OBSERVATION" />}
        >
          <Async state={data} loadingLabel="Loading measurements…">
            {(d) =>
              d.records.length === 0 ? (
                <EmptyState title="No measurements match these filters">
                  Bathing waters are sampled only in the bathing season (about June to mid-September).
                </EmptyState>
              ) : (
                <>
                  <div style={{ height: 300 }} role="img" aria-label="Scatter chart of bacteriological sample results over time, log scale">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <CartesianGrid stroke="#e1e0d9" vertical={false} />
                        <XAxis
                          dataKey="t"
                          type="number"
                          scale="time"
                          domain={["dataMin", "dataMax"]}
                          tickFormatter={(t: number) => new Date(t).toISOString().slice(0, 7)}
                          tick={{ fontSize: 11, fill: "#898781" }}
                          tickLine={false}
                          axisLine={{ stroke: "#c3c2b7" }}
                        />
                        <YAxis
                          dataKey="v"
                          type="number"
                          scale="log"
                          domain={[1, "auto"]}
                          allowDataOverflow
                          tick={{ fontSize: 11, fill: "#898781" }}
                          tickLine={false}
                          axisLine={false}
                          width={56}
                          label={{ value: "count/100 ml (log)", angle: -90, position: "insideLeft", fontSize: 11, fill: "#898781", dx: 4, dy: 50 }}
                        />
                        <Tooltip content={<WQTooltip />} cursor={{ strokeDasharray: "3 3" }} />
                        <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                        {Object.entries(series).map(([name, points]) => (
                          <Scatter key={name} name={name} data={points} fill={SERIES[name] ?? "#6250d6"} stroke="#fcfcfb" strokeWidth={1.5} isAnimationActive={false} />
                        ))}
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                  <SourceLine>
                    EPA Bathing Water open data API (CC BY 4.0). {d.total_matching} matching results
                    {d.total_matching > d.returned ? `, most recent ${d.returned} shown` : ""}. Censored values (e.g. "&lt;10") are plotted at their
                    reporting limit and keep their qualifier in the table.
                  </SourceLine>
                </>
              )
            }
          </Async>
        </Card>

        <div className="space-y-4">
          <Card title="Not available (and not estimated)">
            <Async state={meta}>
              {(m) => (
                <div className="space-y-2">
                  {m.not_connected.map((n) => (
                    <Notice key={n.measurement} tone="warning">
                      <strong>{n.measurement}.</strong> {n.reason}
                    </Notice>
                  ))}
                  <ul className="list-disc space-y-1 pl-5 text-[11px] text-slate-500">
                    {m.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Async>
          </Card>
          <Card title="River water temperature (latest)" actions={<DataStatusBadge status="REAL_OBSERVATION" />} bodyClassName="max-h-80 overflow-y-auto px-4 py-3">
            <Async state={meta}>
              {(m) =>
                m.river_water_temperature.length ? (
                  <table className="w-full text-xs">
                    <tbody className="divide-y divide-slate-100">
                      {m.river_water_temperature
                        .filter((t) => t.in_study_catchment)
                        .map((t) => (
                          <tr key={t.station_ref}>
                            <td className="py-1.5 pr-2 text-slate-700">{t.station_name}</td>
                            <td className="tabular py-1.5 text-right font-medium text-navy-900">{formatNumber(t.value, 1, "°C")}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                ) : (
                  <EmptyState title="No temperature readings available" />
                )
              }
            </Async>
            <SourceLine>OPW waterlevel.ie, provisional real-time data. Gauges inside Catchment 19 only.</SourceLine>
          </Card>
        </div>
      </div>

      <Card className="mt-4" title="Measurements (table view)" bodyClassName="max-h-[420px] overflow-auto">
        <Async state={data}>
          {(d) =>
            d.records.length ? (
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="sticky top-0 bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Observed</th>
                    <th className="px-4 py-2 font-medium">Station</th>
                    <th className="px-4 py-2 font-medium">Measurement</th>
                    <th className="px-4 py-2 text-right font-medium">Value</th>
                    <th className="px-4 py-2 font-medium">Unit</th>
                    <th className="px-4 py-2 font-medium">Sample status</th>
                    <th className="px-4 py-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {[...d.records].reverse().map((r, i) => (
                    <tr key={`${r.station_id}-${r.observed_date}-${r.measurement}-${i}`}>
                      <td className="tabular px-4 py-1.5">{formatDate(r.observed_date)}</td>
                      <td className="px-4 py-1.5">{r.station_name}</td>
                      <td className="px-4 py-1.5">{r.measurement}</td>
                      <td className="tabular px-4 py-1.5 text-right">{r.value_raw}</td>
                      <td className="px-4 py-1.5 text-slate-500">{r.unit}</td>
                      <td className="px-4 py-1.5">{r.sample_status ?? "—"}</td>
                      <td className="px-4 py-1.5 text-slate-500">{r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No rows" />
            )
          }
        </Async>
      </Card>

      <Card className="mt-4" title="Bathing waters in the study area" bodyClassName="overflow-x-auto">
        <Async state={meta}>
          {(m) => (
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Bathing water</th>
                  <th className="px-4 py-2 font-medium">Official classification</th>
                  <th className="px-4 py-2 font-medium">Latest sample</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {m.stations.map((b) => (
                  <tr key={b.beach_id}>
                    <td className="px-4 py-1.5">{b.beach_name}</td>
                    <td className="px-4 py-1.5">
                      {b.classification ?? "Not classified"}
                      {b.classification_year ? ` (${b.classification_year})` : ""}
                    </td>
                    <td className="tabular px-4 py-1.5">{formatDate(b.latest_sample_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
        <SourceLine>Classification: official EU Bathing Water Directive multi-year assessment (EPA), not a current measurement.</SourceLine>
      </Card>
    </>
  );
}
