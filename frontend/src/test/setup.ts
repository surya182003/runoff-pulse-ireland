import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;

// Leaflet feature-detects SVG support via createSVGRect, which jsdom lacks; without it no
// vector renderer exists and circle markers/polygons cannot be added. Real browsers have it.
(SVGSVGElement.prototype as unknown as { createSVGRect: () => object }).createSVGRect = () => ({});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
