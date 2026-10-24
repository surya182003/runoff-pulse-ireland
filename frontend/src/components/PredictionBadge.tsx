import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { PredictionBand } from "../api/types";

export const BAND_META: Record<PredictionBand, { label: string; fill: string; cls: string; Icon: typeof Minus }> = {
  BELOW_TYPICAL: { label: "Low chance", fill: "#14a085", cls: "bg-reef-50 text-reef-700 ring-reef-100", Icon: ArrowDown },
  TYPICAL: { label: "Usual chance", fill: "#fab219", cls: "bg-amber-50 text-amber-900 ring-amber-200", Icon: Minus },
  ABOVE_TYPICAL: { label: "Raised chance", fill: "#d03b3b", cls: "bg-red-50 text-red-800 ring-red-200", Icon: ArrowUp },
};

export function PredictionBadge({ band }: { band: PredictionBand }) {
  const meta = BAND_META[band];
  const Icon = meta.Icon;
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${meta.cls}`}>
      <Icon className="h-3 w-3" aria-hidden />
      {meta.label}
    </span>
  );
}
