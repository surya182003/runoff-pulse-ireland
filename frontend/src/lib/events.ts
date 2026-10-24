/** Real past events that can be replayed with archived observations. */
export interface Scenario {
  id: string;
  label: string;
  asOf?: string;
  description: string;
}

export const SCENARIOS: Scenario[] = [
  { id: "now", label: "Now", description: "Current conditions from live rainfall and river gauges." },
  {
    id: "sep2026",
    label: "Rain event · 27 Sep 2026",
    asOf: "2026-09-27",
    description:
      "Replay of a real late-September rain event. About 20 mm fell in two days and rivers in the Lee, Bandon and Blackwater rose, all from recorded measurements.",
  },
  {
    id: "babet",
    label: "Storm Babet · 18 Oct 2023",
    asOf: "2023-10-18",
    description:
      "Replay of Storm Babet (82 mm of rain in two days at Cork Airport). River records from 2023 are not available, so the system can only flag runoff as 'possible', never 'high', without river evidence.",
  },
];
