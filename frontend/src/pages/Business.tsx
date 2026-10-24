import { Building2, FileText, Fish, Layers, Satellite, Users } from "lucide-react";
import { Card, Notice, PageHeader } from "../components/ui";

const SEGMENTS = [
  {
    Icon: Building2,
    title: "Local authorities",
    need: "Investigate water-quality complaints and plan monitoring after heavy rainfall with limited staff.",
    value: "One view of rainfall, river response, monitoring locations and community reports, with an evidence trail for each flag.",
  },
  {
    Icon: Fish,
    title: "Aquaculture & shellfish operators",
    need: "Timely awareness of rainfall-driven runoff conditions near their sites, alongside, not instead of, official SFPA classifications.",
    value: "Area-level screening, nearby monitoring context and a one-click briefing for internal decisions on extra checks or sampling.",
  },
  {
    Icon: FileText,
    title: "Environmental consultancies",
    need: "Time spent assembling EPA, Met Éireann and OPW data for catchment and coastal studies.",
    value: "A reproducible acquisition pipeline with provenance, licences and validated geospatial outputs.",
  },
  {
    Icon: Users,
    title: "Coastal & community organisations",
    need: "Accessible evidence about local water conditions and a structured way to log observations.",
    value: "Plain-language status with data sources, plus a citizen reporting workflow that keeps reports clearly unverified.",
  },
];

export default function Business() {
  return (
    <>
      <PageHeader
        title="Business Value"
        subtitle="Potential customers and how RunoffPulse could fit into their work. These are hypotheses for validation, not existing customers or partnerships."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="The problem" className="lg:col-span-2">
          <p className="text-sm leading-relaxed text-slate-700">
            Heavy rainfall can wash nutrients, sediment and faecal bacteria from land, sewer overflows and urban surfaces into rivers, estuaries and
            coastal waters. The data needed to see this coming is public but fragmented: rainfall at Met Éireann, river levels at OPW, monitoring
            programmes, protected areas and bathing results at the EPA, and harvesting status with the SFPA. Combining them quickly, with clear
            provenance, is hard for organisations without a dedicated data team.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-700">
            RunoffPulse brings these sources together for one catchment and coast, screens for conditions that may warrant attention, and shows
            exactly which evidence was used and what is missing.
          </p>
        </Card>
        <Card title="Where it fits">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">
            <li>Alongside official monitoring and advisories; it never replaces them.</li>
            <li>Helps decide <em>where to look</em> and <em>when to check</em>, not whether water is safe.</li>
            <li>Keeps a transparent trail: inputs, thresholds, timestamps, limitations.</li>
          </ul>
        </Card>
      </div>

      <h2 className="mb-3 mt-6 text-sm font-semibold text-navy-900">Potential customer segments</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {SEGMENTS.map(({ Icon, title, need, value }) => (
          <div key={title} className="card p-4">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-reef-50 text-reef-700">
                <Icon className="h-4 w-4" aria-hidden />
              </span>
              <h3 className="text-sm font-semibold text-navy-900">{title}</h3>
            </div>
            <dl className="mt-3 space-y-2 text-sm">
              <div>
                <dt className="text-xs font-medium text-slate-500">Need</dt>
                <dd className="text-slate-700">{need}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-slate-500">Proposed benefit</dt>
                <dd className="text-slate-700">{value}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Deployment & commercial model (proposed)">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">
            <li>
              <strong>Organisational subscription</strong> per catchment or coastline: hosted dashboard, scheduled data refresh, screening and
              briefing exports.
            </li>
            <li>
              <strong>Site add-on</strong> for operators: watch areas around specific farms or outfalls, configurable thresholds and (once an
              authoritative trigger and delivery provider are agreed) notifications.
            </li>
            <li>
              <strong>Data services</strong> for consultancies: the provenance-tracked pipeline and API for their own studies.
            </li>
            <li>Lightweight stack (Python/FastAPI, React, SQLite/PostgreSQL) deployable on a single small cloud instance or on-premise.</li>
          </ul>
        </Card>
        <Card title="Roadmap & future integrations">
          <ul className="space-y-2 text-sm text-slate-700">
            <li className="flex gap-2">
              <Layers className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden />
              EPA river and estuarine chemistry, SFPA classified production areas and Marine Institute biotoxin/HAB results, once machine-readable
              access is agreed.
            </li>
            <li className="flex gap-2">
              <Satellite className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden />
              Sentinel-2/3 turbidity and chlorophyll-a proxies, with documented methods, cloud masking and coastal-water uncertainty.
            </li>
            <li className="flex gap-2">
              <Layers className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden />
              Calibrating the screening weights against historical events, distributed rainfall (radar) and tide data; more catchments.
            </li>
          </ul>
        </Card>
      </div>

      <div className="mt-4">
        <Notice>
          No revenue, savings, ROI or customer figures are claimed. Segment needs and benefits are hypotheses to be validated with potential users.
        </Notice>
      </div>
    </>
  );
}
