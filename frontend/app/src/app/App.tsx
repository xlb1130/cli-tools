import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./AppLayout";
import { AliasPage } from "../pages/AliasPage";
import { CatalogPage } from "../pages/CatalogPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DriftPage } from "../pages/DriftPage";
import { ExtensionsPage } from "../pages/ExtensionsPage";
import { GovernancePage } from "../pages/GovernancePage";
import { MountDetailPage } from "../pages/MountDetailPage";
import { MountsPage } from "../pages/MountsPage";
import { AuthPage } from "../pages/AuthPage";
import { LogsPage } from "../pages/LogsPage";
import { RunDetailPage } from "../pages/RunDetailPage";
import { RunsPage } from "../pages/RunsPage";
import { SourceDetailPage } from "../pages/SourceDetailPage";
import { SourcesPage } from "../pages/SourcesPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/governance" element={<GovernancePage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/sources/:sourceName" element={<SourceDetailPage />} />
        <Route path="/aliases" element={<AliasPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/drift" element={<DriftPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/extensions" element={<ExtensionsPage />} />
        <Route path="/mounts" element={<MountsPage />} />
        <Route path="/mounts/:mountId" element={<MountDetailPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
