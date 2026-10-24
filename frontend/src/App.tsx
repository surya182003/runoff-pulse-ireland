import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState, LoadingState } from "./components/ui";
import Overview from "./pages/Overview";

const RiskMap = lazy(() => import("./pages/RiskMap"));
const WaterQuality = lazy(() => import("./pages/WaterQuality"));
const Rainfall = lazy(() => import("./pages/Rainfall"));
const Aquaculture = lazy(() => import("./pages/Aquaculture"));
const Reports = lazy(() => import("./pages/Reports"));
const Sources = lazy(() => import("./pages/Sources"));
const Business = lazy(() => import("./pages/Business"));
const Prediction = lazy(() => import("./pages/Prediction"));

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<LoadingState />}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/map" element={<RiskMap />} />
          <Route path="/prediction" element={<Prediction />} />
          <Route path="/water-quality" element={<WaterQuality />} />
          <Route path="/rainfall" element={<Rainfall />} />
          <Route path="/aquaculture" element={<Aquaculture />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/business" element={<Business />} />
          <Route path="*" element={<EmptyState title="Page not found" />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
