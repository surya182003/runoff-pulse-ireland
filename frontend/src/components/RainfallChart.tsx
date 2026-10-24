import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyRain } from "../api/types";
import { formatDate } from "../lib/format";

const BLUE = "#2a78d6";

interface Row {
  date: string;
  rain: number | null;
  note: string;
}

function TooltipBody({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
      <div className="font-medium text-navy-900">{formatDate(row.date)}</div>
      <div className="tabular text-slate-700">{row.rain === null ? "No complete record" : `${row.rain.toFixed(1)} mm`}</div>
      <div className="text-slate-500">{row.note}</div>
    </div>
  );
}

/** Daily rainfall bars. Days without a complete record are left as gaps (never drawn as zero). */
export function RainfallChart({ records, height = 240 }: { records: DailyRain[]; height?: number }) {
  const rows: Row[] = records.map((r) => ({
    date: r.date,
    rain: r.rain_mm,
    note:
      r.source === "met_eireann_daily_archive"
        ? "Met Éireann daily archive"
        : r.source === "none"
          ? "No observations captured for this day"
          : r.complete
          ? "Sum of 24 hourly reports (provisional)"
          : `Incomplete: ${r.hours_with_data ?? 0} of 24 hourly reports`,
  }));
  return (
    <div style={{ height }} role="img" aria-label="Daily rainfall bar chart, millimetres per day at Cork Airport">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 14, right: 8, left: -8, bottom: 0 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} stroke="#e1e0d9" />
          <XAxis
            dataKey="date"
            tickFormatter={(d: string) => formatDate(d).replace(/ \d{4}$/, "")}
            tick={{ fontSize: 11, fill: "#898781" }}
            tickLine={false}
            axisLine={{ stroke: "#c3c2b7" }}
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#898781" }}
            tickLine={false}
            axisLine={false}
            width={40}
            allowDecimals={false}
          />
          <Tooltip content={<TooltipBody />} cursor={{ fill: "rgba(42,120,214,0.08)" }} />
          <Bar dataKey="rain" fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
