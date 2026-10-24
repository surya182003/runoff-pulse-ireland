import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  BrainCircuit,
  Briefcase,
  CloudRain,
  Database,
  Droplets,
  LayoutDashboard,
  Map as MapIcon,
  Menu,
  MessageSquareWarning,
  Shell,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";

export const NAV = [
  { to: "/", label: "Overview", Icon: LayoutDashboard },
  { to: "/map", label: "Coastal Risk Map", Icon: MapIcon },
  { to: "/prediction", label: "Beach Forecast (AI)", Icon: BrainCircuit },
  { to: "/aquaculture", label: "Shellfish Watch", Icon: Shell },
  { to: "/water-quality", label: "Water Quality", Icon: Droplets },
  { to: "/rainfall", label: "Rain & Rivers", Icon: CloudRain },
  { to: "/reports", label: "Community Reports", Icon: MessageSquareWarning },
  { to: "/sources", label: "Data Sources", Icon: Database },
  { to: "/business", label: "Business Value", Icon: Briefcase },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#0b2545" />
        <path
          d="M5 19c3 0 3-4 6-4s3 6 6 6 3-10 6-10 3 8 4 8"
          fill="none"
          stroke="#2dd4bf"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold text-navy-900">RunoffPulse</div>
        <div className="text-[11px] font-medium uppercase tracking-wider text-reef-600">Ireland</div>
      </div>
    </div>
  );
}

function ApiStatus() {
  const health = useApi((s) => api.health(s));
  const ok = health.data?.status === "ok";
  const label = health.loading ? "Connecting…" : health.error ? "API offline" : ok ? "API connected" : "API degraded";
  const dot = health.loading ? "bg-slate-300" : health.error ? "bg-status-critical" : ok ? "bg-status-good" : "bg-status-warning";
  return (
    <button
      type="button"
      onClick={health.reload}
      title={health.error ?? "Click to re-check"}
      className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      {label}
    </button>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive ? "bg-navy-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-navy-900"
            }`
          }
        >
          <Icon className="h-4 w-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 border-r border-slate-200 bg-white px-3 py-5 lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        {nav}
        <div className="mt-auto rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
          Cork coast pilot. Early-warning support only, not an official water-quality or shellfish advisory.
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-[1100] lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-navy-950/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-64 flex-col gap-6 bg-white px-3 py-5">
            <div className="flex items-center justify-between px-2">
              <Logo />
              <button type="button" aria-label="Close menu" onClick={() => setOpen(false)} className="btn-secondary px-2">
                <X className="h-4 w-4" />
              </button>
            </div>
            {nav}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-[1000] flex items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 py-2.5 backdrop-blur lg:px-8">
          <div className="flex items-center gap-3">
            <button type="button" aria-label="Open menu" onClick={() => setOpen(true)} className="btn-secondary px-2 lg:hidden">
              <Menu className="h-4 w-4" />
            </button>
            <div className="lg:hidden">
              <Logo />
            </div>
            <p className="hidden text-sm text-slate-500 lg:block">
              From rainfall to coastal risk, before it becomes a bigger problem.
            </p>
          </div>
          <ApiStatus />
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 lg:px-8">{children}</main>
        <footer className="border-t border-slate-200 px-4 py-3 text-[11px] text-slate-500 lg:px-8">
          Data: EPA Ireland, Met Éireann, OPW. Map © OpenStreetMap contributors. RunoffPulse supports, and never replaces,
          official EPA, HSE and SFPA advice.
        </footer>
      </div>
    </div>
  );
}
