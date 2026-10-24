import { useState, type FormEvent } from "react";
import { CircleMarker, useMapEvents } from "react-leaflet";
import { CheckCircle2, ChevronLeft, ChevronRight, ImageIcon, Send } from "lucide-react";
import { api } from "../api/client";
import type { ReportCategory } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Async, Card, DataStatusBadge, EmptyState, Notice, PageHeader } from "../components/ui";
import { BaseMap } from "../components/map/MapParts";
import { ReportMarkers } from "../components/map/Layers";
import { formatDateTime, titleCase } from "../lib/format";

export const CATEGORIES: { value: ReportCategory; label: string }[] = [
  { value: "UNUSUAL_COLOUR", label: "Unusual water colour" },
  { value: "FOAM", label: "Foam" },
  { value: "DEBRIS", label: "Debris" },
  { value: "UNUSUAL_ODOUR", label: "Unusual odour" },
  { value: "OTHER", label: "Other observation" },
];
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PAGE_SIZE = 10;

function localNow(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function ClickToPlace({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(Number(e.latlng.lat.toFixed(5)), Number(e.latlng.lng.toFixed(5))) });
  return null;
}

export function ReportForm({ onCreated }: { onCreated: () => void }) {
  const [category, setCategory] = useState<ReportCategory>("UNUSUAL_COLOUR");
  const [description, setDescription] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [observedAt, setObservedAt] = useState(localNow());
  const [photo, setPhoto] = useState<File | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);

  function validate(): string[] {
    const problems: string[] = [];
    if (description.trim().length < 10) problems.push("Description must be at least 10 characters.");
    const la = Number(lat);
    const lo = Number(lon);
    if (lat === "" || lon === "" || Number.isNaN(la) || Number.isNaN(lo)) problems.push("Choose a location on the map or enter latitude and longitude.");
    else if (la < 51 || la > 55.6 || lo < -11 || lo > -5) problems.push("Location must be in Ireland (e.g. latitude 51.85, longitude -8.29).");
    if (!observedAt) problems.push("Enter the observation date and time.");
    else if (new Date(observedAt).getTime() > Date.now() + 10 * 60_000) problems.push("Observation time cannot be in the future.");
    if (photo) {
      if (!["image/jpeg", "image/png", "image/webp"].includes(photo.type)) problems.push("Photo must be JPEG, PNG or WebP.");
      if (photo.size > MAX_PHOTO_BYTES) problems.push("Photo must be 5 MB or smaller.");
    }
    return problems;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    const problems = validate();
    setErrors(problems);
    if (problems.length) return;
    const form = new FormData();
    form.set("category", category);
    form.set("description", description.trim());
    form.set("latitude", lat);
    form.set("longitude", lon);
    form.set("observed_at", new Date(observedAt).toISOString());
    if (photo) form.set("photo", photo);
    setSubmitting(true);
    try {
      await api.createReport(form);
      setSuccess("Report submitted. It is stored as unverified until reviewed.");
      setDescription("");
      setPhoto(null);
      onCreated();
    } catch (err) {
      setErrors([(err as Error).message]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-3" aria-label="Citizen report form">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="r-category">Category</label>
          <select id="r-category" className="input" value={category} onChange={(e) => setCategory(e.target.value as ReportCategory)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="r-when">Observed at (local time)</label>
          <input id="r-when" type="datetime-local" className="input" value={observedAt} max={localNow()} onChange={(e) => setObservedAt(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="label" htmlFor="r-desc">Description</label>
        <textarea
          id="r-desc"
          className="input min-h-[84px]"
          maxLength={2000}
          placeholder="What did you see or smell, and roughly how widespread was it?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div>
        <span className="label">Location: click the map, or enter coordinates</span>
        <BaseMap height={220} center={[51.85, -8.3]} zoom={10}>
          <ClickToPlace
            onPick={(la, lo) => {
              setLat(String(la));
              setLon(String(lo));
            }}
          />
          {lat && lon && !Number.isNaN(Number(lat)) && !Number.isNaN(Number(lon)) && (
            <CircleMarker center={[Number(lat), Number(lon)]} radius={8} pathOptions={{ color: "#6250d6", weight: 3, fillColor: "#ede9fe", fillOpacity: 1 }} />
          )}
        </BaseMap>
        <div className="mt-2 grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="r-lat">Latitude</label>
            <input id="r-lat" inputMode="decimal" className="input" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="51.8500" />
          </div>
          <div>
            <label className="label" htmlFor="r-lon">Longitude</label>
            <input id="r-lon" inputMode="decimal" className="input" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="-8.2900" />
          </div>
        </div>
      </div>
      <div>
        <label className="label" htmlFor="r-photo">Photo (optional · JPEG, PNG or WebP · max 5 MB)</label>
        <input
          id="r-photo"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="block w-full text-xs text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-navy-900"
          onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
        />
      </div>
      {errors.length > 0 && (
        <ul role="alert" className="list-disc space-y-0.5 rounded-lg border border-red-200 bg-red-50 py-2 pl-7 pr-3 text-xs text-red-900">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {success && (
        <p role="status" className="flex items-center gap-1.5 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-900">
          <CheckCircle2 className="h-4 w-4" /> {success}
        </p>
      )}
      <button type="submit" className="btn-primary" disabled={submitting}>
        <Send className="h-4 w-4" aria-hidden /> {submitting ? "Submitting…" : "Submit report"}
      </button>
    </form>
  );
}

export default function Reports() {
  const [page, setPage] = useState(1);
  const reports = useApi((s) => api.reports(page, PAGE_SIZE, s), [page]);
  const mapReports = useApi((s) => api.reports(1, 100, s));

  return (
    <>
      <PageHeader
        title="Citizen Reports"
        subtitle="Community observations of unusual water conditions. Every report stays unverified until reviewed and is never used as a measurement."
        actions={<DataStatusBadge status="CITIZEN_REPORTED_UNVERIFIED" />}
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[480px_1fr]">
        <Card title="Submit an observation">
          <ReportForm
            onCreated={() => {
              setPage(1);
              reports.reload();
              mapReports.reload();
            }}
          />
          <div className="mt-4">
            <Notice>
              If you see a pollution incident in progress, report it to your local authority or the EPA (see epa.ie for the reporting line). This
              prototype does not notify anyone.
            </Notice>
          </div>
        </Card>
        <div className="space-y-4">
          <Card title="Reported locations" bodyClassName="p-3">
            <BaseMap height={260}>{mapReports.data && <ReportMarkers reports={mapReports.data.items} />}</BaseMap>
          </Card>
          <Card
            title={`Reports${reports.data ? ` (${reports.data.total})` : ""}`}
            actions={
              reports.data && reports.data.total > PAGE_SIZE ? (
                <div className="flex items-center gap-1 text-xs">
                  <button type="button" aria-label="Previous page" className="btn-secondary px-2 py-1" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <span className="tabular px-1">
                    {page} / {Math.ceil(reports.data.total / PAGE_SIZE)}
                  </span>
                  <button
                    type="button"
                    aria-label="Next page"
                    className="btn-secondary px-2 py-1"
                    disabled={page >= Math.ceil(reports.data.total / PAGE_SIZE)}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null
            }
          >
            <Async state={reports}>
              {(p) =>
                p.items.length ? (
                  <ul className="divide-y divide-slate-100">
                    {p.items.map((r) => (
                      <li key={r.id} className="flex gap-3 py-3">
                        {r.has_photo ? (
                          <img src={api.reportPhotoUrl(r.id)} alt={`Photo for ${titleCase(r.category)} report`} className="h-16 w-16 shrink-0 rounded-md object-cover" loading="lazy" />
                        ) : (
                          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-400">
                            <ImageIcon className="h-5 w-5" aria-hidden />
                          </div>
                        )}
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-navy-900">{titleCase(r.category)}</span>
                            <DataStatusBadge status={r.data_status} />
                          </div>
                          <p className="break-words text-xs text-slate-700">{r.description}</p>
                          <p className="text-[11px] text-slate-500">
                            Observed {formatDateTime(r.observed_at)} · {r.latitude.toFixed(4)}, {r.longitude.toFixed(4)} · {r.verification_status.toLowerCase()}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No reports yet">Submitted observations will appear here.</EmptyState>
                )
              }
            </Async>
          </Card>
        </div>
      </div>
    </>
  );
}
