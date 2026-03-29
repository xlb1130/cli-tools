import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./AppLayout";
import { CatalogPage } from "../pages/CatalogPage";
import { DashboardPage } from "../pages/DashboardPage";
import { ExtensionsPage } from "../pages/ExtensionsPage";
import { MountDetailPage } from "../pages/MountDetailPage";
import { MountsPage } from "../pages/MountsPage";
import { RunsPage } from "../pages/RunsPage";
import { SourcesPage } from "../pages/SourcesPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/extensions" element={<ExtensionsPage />} />
        <Route path="/mounts" element={<MountsPage />} />
        <Route path="/mounts/:mountId" element={<MountDetailPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/runs" element={<RunsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
