import type { ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, Info, Loader2, RefreshCw } from "lucide-react";
import type { Classification, DataStatus } from "../api/types";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-navy-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
  bodyClassName = "p-4",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          {title && <h2 className="card-title">{title}</h2>}
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-6 text-center">
      <AlertTriangle className="h-5 w-5 text-status-critical" aria-hidden />
      <p className="text-sm text-red-900">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-slate-300 bg-slate-50/60 px-4 py-8 text-center">
      <CircleDashed className="h-5 w-5 text-slate-400" aria-hidden />
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <div className="max-w-md text-xs text-slate-500">{children}</div>}
    </div>
  );
}

/** Wrap async content: loading, error-with-retry, then children. */
export function Async<T>({
  state,
  children,
  loadingLabel,
}: {
  state: { data: T | null; error: string | null; loading: boolean; reload: () => void };
  children: (data: T) => ReactNode;
  loadingLabel?: string;
}) {
  if (state.loading && !state.data) return <LoadingState label={loadingLabel} />;
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (!state.data) return <EmptyState title="No data" />;
  return <>{children(state.data)}</>;
}

const DATA_STATUS_STYLE: Record<DataStatus, { label: string; cls: string }> = {
  REAL_OBSERVATION: { label: "Measured", cls: "bg-ocean-50 text-ocean-700 ring-ocean-100" },
  REAL_STATION_LOCATION: { label: "Station locations", cls: "bg-slate-100 text-slate-700 ring-slate-200" },
  REAL_REFERENCE_GEOMETRY: { label: "Official map", cls: "bg-slate-100 text-slate-700 ring-slate-200" },
  OFFICIAL_ASSESSMENT: { label: "Official rating", cls: "bg-indigo-50 text-indigo-800 ring-indigo-100" },
  OFFICIAL_DESIGNATION: { label: "Official designation", cls: "bg-indigo-50 text-indigo-800 ring-indigo-100" },
  OFFICIAL_ADVISORY: { label: "Official alert", cls: "bg-indigo-50 text-indigo-800 ring-indigo-100" },
  MODELLED_INDICATOR: { label: "Calculated", cls: "bg-reef-50 text-reef-700 ring-reef-100" },
  SIMULATED_DEMO: { label: "DEMO DATA", cls: "bg-amber-100 text-amber-900 ring-amber-300" },
  CITIZEN_REPORTED_UNVERIFIED: { label: "Public report · unverified", cls: "bg-violet-50 text-violet-800 ring-violet-100" },
};

export function DataStatusBadge({ status, title }: { status: DataStatus | string | undefined; title?: string }) {
  const style = DATA_STATUS_STYLE[status as DataStatus] ?? { label: status ?? "Unknown", cls: "bg-slate-100 text-slate-700 ring-slate-200" };
  return (
    <span
      title={title ?? String(status)}
      data-status={status}
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style.cls}`}
    >
      {style.label}
    </span>
  );
}

export const CLASSIFICATION_META: Record<
  Classification,
  { label: string; short: string; color: string; fill: string; text: string; Icon: typeof Info }
> = {
  ELEVATED_SCREENING_RISK: {
    label: "High runoff risk",
    short: "High",
    color: "#d03b3b",
    fill: "#d03b3b",
    text: "text-red-800 bg-red-50 ring-red-200",
    Icon: AlertOctagon,
  },
  POTENTIAL_RUNOFF_RISK: {
    label: "Possible runoff",
    short: "Watch",
    color: "#b7790a",
    fill: "#fab219",
    text: "text-amber-900 bg-amber-50 ring-amber-200",
    Icon: AlertTriangle,
  },
  NO_ELEVATED_SIGNAL: {
    label: "Normal",
    short: "Normal",
    color: "#0f8a73",
    fill: "#14a085",
    text: "text-reef-700 bg-reef-50 ring-reef-100",
    Icon: CheckCircle2,
  },
  INSUFFICIENT_DATA: {
    label: "Not assessed",
    short: "Not assessed",
    color: "#94a3b8",
    fill: "#cbd5e1",
    text: "text-slate-600 bg-white ring-slate-300 ring-dashed",
    Icon: CircleSlash,
  },
};

export function ClassificationBadge({ value, size = "sm" }: { value: Classification; size?: "sm" | "md" }) {
  const meta = CLASSIFICATION_META[value];
  const Icon = meta.Icon;
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full font-medium ring-1 ring-inset ${meta.text} ${
        size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[11px]"
      }`}
    >
      <Icon className={size === "md" ? "h-3.5 w-3.5" : "h-3 w-3"} aria-hidden />
      {meta.label}
    </span>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warning"; children: ReactNode }) {
  const cls =
    tone === "warning" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-ocean-100 bg-ocean-50 text-navy-800";
  return (
    <div className={`flex gap-2 rounded-lg border px-3 py-2 text-xs leading-relaxed ${cls}`}>
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function SourceLine({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{children}</p>;
}

export function StatTile({
  label,
  value,
  sub,
  status,
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  status?: DataStatus;
  icon?: ReactNode;
}) {
  return (
    <div className="card flex flex-col gap-1 p-4">
      <span className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        {icon}
        {label}
      </span>
      <div className="text-2xl font-semibold tracking-tight text-navy-900">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
      {status && (
        <div className="mt-auto pt-1.5">
          <DataStatusBadge status={status} />
        </div>
      )}
    </div>
  );
}
