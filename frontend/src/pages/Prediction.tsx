import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Tooltip as MapTooltip } from "react-leaflet";
import {
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, BrainCircuit, CheckCircle2, CircleSlash, Info } from "lucide-react";
import { api } from "../api/client";
import type { BeachPrediction, ModelCard, ModelMetrics } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, DataStatusBadge, EmptyState, PageHeader, SourceLine, StatTile } from "../components/ui";
import { BaseMap } from "../components/map/MapParts";
import { BAND_META, PredictionBadge } from "../components/PredictionBadge";
import { formatDate, formatDateTime, isoDate } from "../lib/format";

const pct = (p: number | null | undefined, digits = 1) => (p === null || p === undefined ? "—" : `${(p * 100).toFixed(digits)}%`);

function StatusBanner({ status, message }: { status: string; message: string }) {
  const style =
    status === "OK"
      ? { cls: "border-green-200 bg-green-50 text-green-900", Icon: CheckCircle2, title: "Bathing season forecast" }
      : status === "OUT_OF_SEASON"
        ? { cls: "border-amber-200 bg-amber-50 text-amber-900", Icon: AlertTriangle, title: "Off-season: rough guide only" }
        : { cls: "border-slate-200 bg-slate-50 text-slate-700", Icon: CircleSlash, title: "Forecast unavailable" };
  const Icon = style.Icon;
  return (
    <div role="status" className={`flex gap-2 rounded-lg border px-3 py-2 text-xs ${style.cls}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>
        <div className="font-semibold">{style.title}</div>
        <div>{message}</div>
      </div>
    </div>
  );
}

function Drivers({ p }: { p: BeachPrediction }) {
  const top = p.drivers.filter((d) => Math.abs(d.log_odds) >= 0.05).slice(0, 2);
  if (!top.length) return <span className="text-slate-400">No strong drivers</span>;
  return (
    <span className="text-slate-600">
      {top.map((d, i) => (
        <span key={d.factor}>
          {i > 0 && " · "}
          {d.factor} {d.log_odds > 0 ? "↑" : "↓"}
        </span>
      ))}
    </span>
  );
}

function MetricsRow({ name, m, highlight }: { name: string; m: ModelMetrics; highlight?: boolean }) {
  return (
    <tr className={highlight ? "bg-reef-50/60 font-medium" : ""}>
      <td className="px-3 py-1.5">{name}</td>
      <td className="tabular px-3 py-1.5 text-right">
        {m.roc_auc.toFixed(2)} <span className="text-slate-400">({m.roc_auc_95ci[0].toFixed(2)}–{m.roc_auc_95ci[1].toFixed(2)})</span>
      </td>
      <td className="tabular px-3 py-1.5 text-right">{m.average_precision.toFixed(3)}</td>
      <td className="tabular px-3 py-1.5 text-right">{m.brier.toFixed(4)}</td>
    </tr>
  );
}

function ModelEvidence({ card }: { card: ModelCard }) {
  const v = card.variants[card.deployed_variant];
  const ev = v.evaluation;
  const calib = v.calibration.map((c) => ({ x: c.mean_predicted * 100, y: c.observed_rate * 100, n: c.n }));
  const maxAxis = Math.ceil(Math.max(...calib.map((c) => Math.max(c.x, c.y)), 5) / 2) * 2;
  const maxBand = Math.max(...v.bands_out_of_sample.map((b) => b.observed_rate ?? 0), 0.01);
  const compared = card.compared_variants ?? {};

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <Card title="Out-of-sample performance" actions={<span className="text-[11px] text-slate-500">leave-one-year-out</span>} bodyClassName="overflow-x-auto p-0">
        <table className="w-full min-w-[420px] text-left text-xs">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 text-right font-medium">ROC AUC (95% CI)</th>
              <th className="px-3 py-2 text-right font-medium">Avg precision</th>
              <th className="px-3 py-2 text-right font-medium">Brier</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            <MetricsRow name="Baseline: beach history only" m={ev.baseline_beach_rate} />
            <MetricsRow name="Logistic regression (deployed)" m={ev.logistic_regression} highlight />
            <MetricsRow name="Gradient boosting" m={ev.gradient_boosting} />
            {Object.entries(compared).map(([name, c]) => (
              <MetricsRow key={name} name={`Logistic regression + 7-day rain (${name})`} m={c.evaluation.logistic_regression} />
            ))}
          </tbody>
        </table>
        <p className="px-3 py-2 text-[11px] leading-relaxed text-slate-500">
          AUC 0.5 = chance, 1.0 = perfect. Adding older rainfall and a more complex model did not help, so the simplest model is deployed.
          Gradient boosting ranks similarly but its probabilities are less well calibrated (higher Brier score).
        </p>
      </Card>

      <Card title="Do the bands mean anything?" actions={<span className="text-[11px] text-slate-500">observed, unseen years</span>}>
        <div className="space-y-3">
          {v.bands_out_of_sample.map((b) => (
            <div key={b.band} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <PredictionBadge band={b.band} />
                <span className="tabular text-slate-600">
                  {b.events} of {b.n} samples elevated ·{" "}
                  <strong className="text-navy-900">{pct(b.observed_rate)}</strong>
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                <div className="h-full rounded-full" style={{ width: `${((b.observed_rate ?? 0) / maxBand) * 100}%`, background: BAND_META[b.band].fill }} />
              </div>
            </div>
          ))}
          <p className="text-[11px] leading-relaxed text-slate-500">
            Samples the model placed in the top fifth of risk were <strong>{v.top_vs_bottom_quintile_ratio}×</strong> as likely to show elevated
            bacteria as those in the bottom fifth. Bands are relative to the {pct(v.training.event_rate)} average rate; none means "safe".
          </p>
        </div>
      </Card>

      <Card title="Calibration (predicted vs observed)">
        <div style={{ height: 210 }} role="img" aria-label="Calibration chart: mean predicted probability versus observed rate in five groups">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, left: -8, bottom: 14 }}>
              <CartesianGrid stroke="#e1e0d9" />
              <XAxis type="number" dataKey="x" domain={[0, maxAxis]} tick={{ fontSize: 11, fill: "#898781" }} unit="%"
                label={{ value: "Predicted", position: "insideBottom", offset: -8, fontSize: 11, fill: "#898781" }} />
              <YAxis type="number" dataKey="y" domain={[0, maxAxis]} tick={{ fontSize: 11, fill: "#898781" }} unit="%" width={44} />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: maxAxis, y: maxAxis }]} stroke="#c3c2b7" strokeDasharray="4 4" />
              <Tooltip
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
                      Predicted {payload[0].payload.x.toFixed(1)}% · observed {payload[0].payload.y.toFixed(1)}% ({payload[0].payload.n} samples)
                    </div>
                  ) : null
                }
              />
              <Scatter data={calib} fill="#2a78d6" stroke="#fcfcfb" strokeWidth={2} isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <SourceLine>Five equal-sized groups of samples. Points near the dashed line mean the probabilities can be taken at face value.</SourceLine>
      </Card>
    </div>
  );
}

function BacktestChart({ beachId }: { beachId: string | null }) {
  const bt = useApi((s) => api.backtest(s));
  return (
    <Async state={bt}>
      {(data) => {
        const rows = data.records.filter((r) => !beachId || r.beach_id === beachId);
        if (!rows.length) return <EmptyState title="No historical samples for this beach" />;
        const toPoint = (r: (typeof rows)[number]) => ({ t: Date.parse(`${r.date}T00:00:00Z`), p: r.p_out_of_sample * 100, r });
        const clean = rows.filter((r) => !r.observed_elevated).map(toPoint);
        const elevated = rows.filter((r) => r.observed_elevated).map(toPoint);
        const firstYear = Number(rows[0].date.slice(0, 4));
        const lastYear = Number(rows[rows.length - 1].date.slice(0, 4));
        const yearTicks = Array.from({ length: lastYear - firstYear + 2 }, (_, i) => Date.UTC(firstYear + i, 0, 1));
        return (
          <>
            <div style={{ height: 240 }} role="img" aria-label="Backtest: out-of-sample predicted probability for each historical sample, with elevated samples highlighted">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke="#e1e0d9" vertical={false} />
                  <XAxis dataKey="t" type="number" scale="time" domain={[yearTicks[0], yearTicks[yearTicks.length - 1]]} ticks={yearTicks}
                    tick={{ fontSize: 11, fill: "#898781" }} tickFormatter={(t: number) => String(new Date(t).getUTCFullYear())} />
                  <YAxis dataKey="p" type="number" unit="%" tick={{ fontSize: 11, fill: "#898781" }} width={44} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const r = payload[0].payload.r as (typeof rows)[number];
                      return (
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-card">
                          <div className="font-medium">{r.beach_name} · {formatDate(r.date)}</div>
                          <div>AI estimate {pct(r.p_out_of_sample)} · rain the day before {r.rain_d1_mm ?? "—"} mm</div>
                          <div>{r.observed_elevated ? "Real test: FAILED" : "Real test: passed"}</div>
                        </div>
                      );
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                  <Scatter name="Test passed" data={clean} fill="#86b6ef" isAnimationActive={false} />
                  <Scatter name="Test failed" data={elevated} fill="#d03b3b" stroke="#fcfcfb" strokeWidth={1.5} isAnimationActive={false} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <SourceLine>Each dot is a real beach test. Red dots are tests that failed; the AI tends to give them higher chances.</SourceLine>
          </>
        );
      }}
    </Async>
  );
}

export default function Prediction() {
  const [date, setDate] = useState(isoDate(new Date()));
  const [selected, setSelected] = useState<string | null>(null);
  const prediction = useApi((s) => api.predictions(date, s), [date]);
  const model = useApi((s) => api.model(s));
  const bt = useApi((s) => api.backtest(s));

  const presets = useMemo(() => {
    const out: { label: string; date: string }[] = [{ label: "Today", date: isoDate(new Date()) }];
    const recs = bt.data?.records ?? [];
    if (recs.length) {
      out.push({ label: "Latest sampling day", date: recs[recs.length - 1].date });
      const hit = [...recs].filter((r) => r.observed_elevated).sort((a, b) => b.p_out_of_sample - a.p_out_of_sample)[0];
      if (hit) out.push({ label: "A day a beach failed", date: hit.date });
    }
    return out;
  }, [bt.data]);

  useEffect(() => {
    const first = prediction.data?.predictions[0];
    if (!selected && first) setSelected(first.beach_id);
  }, [prediction.data, selected]);

  const deployed = model.data ? model.data.variants[model.data.deployed_variant] : null;

  return (
    <>
      <PageHeader
        title="Beach Water Forecast (AI)"
        subtitle="Rain washes bacteria from land into the sea. This AI model learned that pattern from 12 years of real beach tests, and estimates the chance that a water sample at each beach would fail the EU bacteria limit."
        actions={<DataStatusBadge status="MODELLED_INDICATOR" />}
      />

      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatTile
          label="Learned from"
          icon={<BrainCircuit className="h-3.5 w-3.5" />}
          value={deployed ? `${deployed.training.samples.toLocaleString("en-IE")} beach tests` : "—"}
          sub={deployed ? `Real EPA results from ${deployed.training.beaches} Cork beaches, ${deployed.training.period[0].slice(0, 4)}–${deployed.training.period[1].slice(0, 4)}, matched with rainfall` : ""}
        />
        <StatTile
          label="Does it work?"
          value={
            deployed
              ? `${pct(deployed.bands_out_of_sample.find((b) => b.band === "ABOVE_TYPICAL")?.observed_rate, 0)} vs ${pct(
                  deployed.bands_out_of_sample.find((b) => b.band === "BELOW_TYPICAL")?.observed_rate,
                  0,
                )}`
              : "—"
          }
          sub="Share of tests that actually failed on 'raised chance' days vs 'low chance' days"
        />
        <StatTile
          label="Tested fairly"
          value={deployed ? `${Object.keys(deployed.per_year_auc).length} seasons` : "—"}
          sub="Each year was predicted by a model that had never seen that year's results"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
        <Card
          title="Forecast by beach"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {presets.map((p) => (
                <button key={p.label} type="button" onClick={() => setDate(p.date)}
                  className={`btn px-2.5 py-1 text-xs ${date === p.date ? "bg-navy-900 text-white" : "border border-slate-300 bg-white text-navy-900 hover:bg-slate-50"}`}>
                  {p.label}
                </button>
              ))}
              <label className="sr-only" htmlFor="pred-date">Prediction date</label>
              <input id="pred-date" type="date" className="input w-auto py-1 text-xs" min="2015-01-08" max={isoDate(new Date())} value={date}
                onChange={(e) => e.target.value && setDate(e.target.value)} />
            </div>
          }
        >
          <Async state={prediction} loadingLabel="Running model…">
            {(p) => (
              <div className="space-y-3">
                <StatusBanner status={p.status} message={p.message} />
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                  <span>Date: <strong className="text-navy-900">{formatDate(p.date)}</strong></span>
                  <span>
                    Rain the day before ({p.inputs.rain_station}):{" "}
                    <strong className="text-navy-900">{p.inputs.rainfall_mm.rain_d1 ?? "—"} mm</strong>
                  </span>
                </div>
                {p.status === "UNAVAILABLE" ? (
                  <EmptyState title="No prediction for this date">{p.message}</EmptyState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-left text-xs">
                      <thead className="bg-slate-50 text-slate-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">Beach</th>
                          <th className="px-3 py-2 text-right font-medium">Chance of failing</th>
                          <th className="px-3 py-2 font-medium">Rating</th>
                          <th className="px-3 py-2 font-medium">Why</th>
                          <th className="px-3 py-2 font-medium">Actual test that day</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {p.predictions.map((b) => (
                          <tr key={b.beach_id} onClick={() => setSelected(b.beach_id)}
                            className={`cursor-pointer hover:bg-slate-50 ${selected === b.beach_id ? "bg-ocean-50/60" : ""} ${p.status === "OUT_OF_SEASON" ? "opacity-80" : ""}`}>
                            <td className="px-3 py-2 font-medium text-navy-900">{b.beach_name}</td>
                            <td className="tabular px-3 py-2 text-right font-semibold">{pct(b.probability)}</td>
                            <td className="px-3 py-2">{b.band && <PredictionBadge band={b.band} />}</td>
                            <td className="px-3 py-2"><Drivers p={b} /></td>
                            <td className="px-3 py-2">
                              {b.observed ? (
                                <span className={b.observed.elevated ? "font-medium text-red-700" : "text-slate-600"}>
                                  {b.observed.elevated ? "Failed" : "Passed"} (E. coli {b.observed.e_coli})
                                </span>
                              ) : (
                                <span className="text-slate-400">No test</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <SourceLine>
                  "Failing" means E. coli above 250 or enterococci above 100 per 100 ml (EU limits for excellent coastal water). This is an AI
                  estimate to help plan sampling, not an official beach advisory.
                </SourceLine>
              </div>
            )}
          </Async>
        </Card>

        <div className="space-y-4">
          <Card title="Map" bodyClassName="p-3">
            <BaseMap height={300} center={[51.85, -8.1]} zoom={9}>
              {prediction.data?.predictions.map((b) =>
                b.band ? (
                  <CircleMarker key={b.beach_id} center={[b.lat, b.lon]} radius={selected === b.beach_id ? 10 : 7}
                    pathOptions={{ color: "#ffffff", weight: 2, fillColor: BAND_META[b.band].fill, fillOpacity: 0.95 }}
                    eventHandlers={{ click: () => setSelected(b.beach_id) }}>
                    <MapTooltip>{b.beach_name}: {pct(b.probability)} ({BAND_META[b.band].label})</MapTooltip>
                  </CircleMarker>
                ) : null,
              )}
            </BaseMap>
          </Card>
          <Card title="How the model decides">
            {deployed ? (
              <ul className="space-y-2 text-xs text-slate-700">
                <li className="flex gap-2"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ocean-600" />
                  <span><strong>Rain the day before</strong>: more rain washes more bacteria from land, rivers and drains into the sea.</span></li>
                <li className="flex gap-2"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ocean-600" />
                  <span><strong>Time of year</strong>: failed tests become more likely later in the summer.</span></li>
                <li className="flex gap-2"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ocean-600" />
                  <span><strong>Beach history</strong>: some beaches fail more often because of local streams and outfalls (most often: {deployed.beach_effects.slice(0, 2).map((b) => b.beach_name).join(", ")}).</span></li>
              </ul>
            ) : (
              <EmptyState title="Model card unavailable" />
            )}
          </Card>
        </div>
      </div>

      <Card className="mt-4" title={`Past results: AI estimate vs real test${selected && prediction.data ? ` · ${prediction.data.predictions.find((b) => b.beach_id === selected)?.beach_name ?? ""}` : ""}`}
        actions={selected && <button type="button" className="text-xs font-medium text-ocean-600 hover:underline" onClick={() => setSelected(null)}>Show all beaches</button>}>
        <BacktestChart beachId={selected} />
      </Card>

      <details className="card mt-4">
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-navy-900">
          Technical details: model performance and validation
        </summary>
        <div className="border-t border-slate-100 p-4">
          <p className="mb-3 text-xs text-slate-600">
            Algorithm: {model.data?.algorithm}. Validation: {model.data?.evaluation}.
          </p>
          <Async state={model}>{(card) => <ModelEvidence card={card} />}</Async>
        </div>
      </details>

      {model.data && (
        <Card className="mt-4" title="What the forecast cannot do">
          <ul className="list-disc space-y-1 pl-5 text-xs text-slate-700">
            {model.data.limitations.map((l) => <li key={l}>{l}</li>)}
          </ul>
          <SourceLine>
            Model {model.data.model_id} v{model.data.version}, trained {formatDateTime(model.data.trained_at)}. Retrain with
            scripts/train_bathing_model.py. {model.data.evaluation}.
          </SourceLine>
        </Card>
      )}
    </>
  );
}
