import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../App";
import { DataStatusBadge } from "../components/ui";
import { ReportForm } from "../pages/Reports";
import { fixtures, json, mockApi } from "./fixtures";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("application startup", () => {
  it("renders the overview status in plain language", async () => {
    mockApi();
    renderAt("/");
    expect(await screen.findByText("Normal conditions")).toBeInTheDocument();
    expect(screen.getByText(/none of the 1 coastal areas need extra attention/)).toBeInTheDocument();
    expect(screen.getByText("API connected")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Shellfish Watch");
  });

  it("replays a past event from the overview", async () => {
    const fetchMock = mockApi();
    renderAt("/");
    await screen.findByText("Normal conditions");
    await userEvent.click(screen.getByRole("button", { name: /Rain event · 27 Sep 2026/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("as_of=2026-09-27"))).toBe(true));
  });

  it("shows an error state with retry when the API is unreachable", async () => {
    const fetchMock = mockApi({
      "/api/risk": () => Promise.reject(new TypeError("Failed to fetch")),
    });
    renderAt("/");
    const alert = await screen.findByText(/Cannot reach the RunoffPulse API/);
    expect(alert).toBeInTheDocument();
    const callsBefore = fetchMock.mock.calls.length;
    await userEvent.click(within(alert.closest("[role=alert]") as HTMLElement).getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("shows API error details for server errors", async () => {
    mockApi({ "/api/sources": () => json({ detail: "Dataset 'manifest.json' has not been acquired." }, 503) });
    renderAt("/sources");
    expect(await screen.findByText(/has not been acquired/)).toBeInTheDocument();
  });
});

describe("empty datasets", () => {
  it("shows empty states instead of fabricated values", async () => {
    mockApi({
      "/api/rainfall": { ...(fixtures["/api/rainfall"] as object), records: [], latest_observation: null },
    });
    renderAt("/rainfall");
    expect(await screen.findByText("No rainfall data for this range")).toBeInTheDocument();
    expect(screen.getAllByText("No recent observation").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no community reports", async () => {
    mockApi();
    renderAt("/reports");
    expect(await screen.findByText("No reports yet")).toBeInTheDocument();
  });

  it("labels the aquaculture advisory feed as not connected", async () => {
    mockApi();
    renderAt("/aquaculture");
    expect(await screen.findByText("Official harvesting advisories: not connected")).toBeInTheDocument();
    expect(screen.getByText("Layer unavailable")).toBeInTheDocument();
  });
});

describe("risk map", () => {
  async function showStations() {
    await userEvent.click(await screen.findByRole("checkbox", { name: "EPA monitoring stations" }));
    await screen.findByText(/2 EPA monitoring stations shown/);
  }

  it("renders a Leaflet map with station markers, skipping invalid geometry", async () => {
    mockApi();
    const { container } = renderAt("/map");
    await showStations();
    expect(container.querySelector(".leaflet-container")).not.toBeNull();
    expect(container.querySelector(".leaflet-control-attribution")).toHaveTextContent("OpenStreetMap");
    // Two valid stations are drawn as circle markers; the null-geometry station is skipped.
    expect(container.querySelectorAll("path.leaflet-interactive").length).toBeGreaterThanOrEqual(2);
  });

  it("toggles layers and filters station types", async () => {
    mockApi();
    renderAt("/map");
    await showStations();
    const riverType = screen.getByRole("checkbox", { name: /^River \d+$/ });
    await userEvent.click(riverType);
    expect(await screen.findByText(/1 EPA monitoring stations shown/)).toBeInTheDocument();
    const stationsLayer = screen.getByRole("checkbox", { name: "EPA monitoring stations" });
    expect(stationsLayer).toBeChecked();
    await userEvent.click(stationsLayer);
    expect(stationsLayer).not.toBeChecked();
  });

  it("opens the station detail panel when a station is selected", async () => {
    const fetchMock = mockApi();
    const { container } = renderAt("/map");
    await showStations();
    await waitFor(() => expect(container.querySelectorAll("path.leaflet-interactive").length).toBeGreaterThan(0));
    const markers = [...container.querySelectorAll("path.leaflet-interactive")];
    // Click each interactive path until the station request fires (map polygons are interactive too).
    for (const m of markers) {
      fireEvent.click(m);
      if (fetchMock.mock.calls.some(([u]) => String(u).includes("/api/stations/RS19L030500"))) break;
    }
    expect(await screen.findByText("Monitoring station")).toBeInTheDocument();
    expect(await screen.findByText(/Lab results for this station are not yet connected/)).toBeInTheDocument();
  });

  it("explains an area's status in plain language, with technical detail available", async () => {
    mockApi();
    renderAt("/map");
    await userEvent.click(await screen.findByRole("button", { name: /Rostellan South/ }));
    expect(await screen.findByText("What we checked")).toBeInTheDocument();
    expect(screen.getByText(/Runoff is unlikely to be elevated/)).toBeInTheDocument();
    expect(screen.getByText("Technical details")).toBeInTheDocument();
    expect(screen.getByText(/sampling is seasonal/)).toBeInTheDocument();
  });
});

describe("AI prediction", () => {
  it("shows per-beach probabilities, drivers, actual outcome and validation evidence", async () => {
    mockApi();
    renderAt("/prediction");
    expect(await screen.findByText("18.4%")).toBeInTheDocument();
    expect(screen.getAllByText("Raised chance").length).toBeGreaterThan(0);
    expect(screen.getByText(/Rain yesterday ↑/)).toBeInTheDocument();
    expect(screen.getByText(/Failed \(E. coli 620\)/)).toBeInTheDocument();
    expect(screen.getByText("Bathing season forecast")).toBeInTheDocument();
    expect(await screen.findByText("Logistic regression (deployed)")).toBeInTheDocument();
    expect(screen.getByText(/not an official beach advisory/)).toBeInTheDocument();
  });

  it("does not invent a prediction when inputs are missing", async () => {
    mockApi({
      "/api/predictions": {
        ...(fixtures["/api/predictions"] as object),
        status: "UNAVAILABLE",
        message: "Not enough complete daily rainfall.",
        predictions: [],
      },
    });
    renderAt("/prediction");
    expect(await screen.findByText("No prediction for this date")).toBeInTheDocument();
  });
});

describe("citizen reports", () => {
  it("validates input before submitting", async () => {
    const fetchMock = mockApi();
    render(<ReportForm onCreated={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));
    expect(await screen.findByText(/at least 10 characters/)).toBeInTheDocument();
    expect(screen.getByText(/Choose a location/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("submits a valid report as multipart form data", async () => {
    let posted: FormData | null = null;
    mockApi({
      "/api/reports": (init?: RequestInit) => {
        posted = init?.body as FormData;
        return json({ id: "a".repeat(32), verification_status: "UNVERIFIED" }, 201);
      },
    });
    let created = 0;
    render(<ReportForm onCreated={() => created++} />);
    await userEvent.selectOptions(screen.getByLabelText("Category"), "FOAM");
    await userEvent.type(screen.getByLabelText("Description"), "Thick brown foam along the slipway.");
    await userEvent.type(screen.getByLabelText("Latitude"), "51.85");
    await userEvent.type(screen.getByLabelText("Longitude"), "-8.29");
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));
    expect(await screen.findByText(/stored as unverified/)).toBeInTheDocument();
    expect(created).toBe(1);
    expect(posted!.get("category")).toBe("FOAM");
    expect(posted!.get("latitude")).toBe("51.85");
  });

  it("shows server validation errors", async () => {
    mockApi({ "/api/reports": () => json({ detail: [{ msg: "observed_at cannot be in the future" }] }, 422) });
    render(<ReportForm onCreated={() => {}} />);
    await userEvent.type(screen.getByLabelText("Description"), "Oily sheen near the outfall pipe.");
    await userEvent.type(screen.getByLabelText("Latitude"), "51.85");
    await userEvent.type(screen.getByLabelText("Longitude"), "-8.29");
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));
    expect(await screen.findByText("observed_at cannot be in the future")).toBeInTheDocument();
  });
});

describe("data provenance", () => {
  it("labels data status visibly, including demo data", () => {
    render(
      <>
        <DataStatusBadge status="SIMULATED_DEMO" />
        <DataStatusBadge status="REAL_OBSERVATION" />
        <DataStatusBadge status="CITIZEN_REPORTED_UNVERIFIED" />
      </>,
    );
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
    expect(screen.getByText("Measured")).toBeInTheDocument();
    expect(screen.getByText("Public report · unverified")).toBeInTheDocument();
  });

  it("lists dataset licence, retrieval time and known gaps on the sources page", async () => {
    mockApi();
    renderAt("/sources");
    expect(await screen.findByText("EPA water monitoring station locations")).toBeInTheDocument();
    expect(screen.getByText("CC BY 4.0")).toBeInTheDocument();
    expect(screen.getByText("SFPA production areas")).toBeInTheDocument();
    expect(screen.getAllByText(/Irish time/).length).toBeGreaterThan(0);
  });

  it("shows rainfall gaps as incomplete records rather than zero", async () => {
    mockApi();
    renderAt("/rainfall");
    expect(await screen.findByText(/Some recent days have no complete record/)).toBeInTheDocument();
  });
});
