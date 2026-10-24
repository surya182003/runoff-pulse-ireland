import { History } from "lucide-react";
import { SCENARIOS, type Scenario } from "../lib/events";

export function ScenarioTabs({ value, onChange }: { value: Scenario; onChange: (s: Scenario) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Choose conditions to show">
      {SCENARIOS.map((s) => (
        <button
          key={s.id}
          type="button"
          aria-pressed={value.id === s.id}
          onClick={() => onChange(s)}
          className={`btn px-3 py-1.5 text-xs ${
            value.id === s.id ? "bg-navy-900 text-white" : "border border-slate-300 bg-white text-navy-900 hover:bg-slate-50"
          }`}
        >
          {s.asOf && <History className="h-3.5 w-3.5" aria-hidden />}
          {s.label}
        </button>
      ))}
    </div>
  );
}
