import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { MountDetailPage } from "../pages/MountDetailPage";
import { MountsPage } from "../pages/MountsPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { RunDetailPage } from "../pages/RunDetailPage";
import { RunsPage } from "../pages/RunsPage";
import { SourceDetailPage } from "../pages/SourceDetailPage";
import { SourcesPage } from "../pages/SourcesPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/sources/:sourceName" element={<SourceDetailPage />} />
        <Route path="/mounts" element={<MountsPage />} />
        <Route path="/mounts/:mountId" element={<MountDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/governance" element={<PlaceholderPage title="Governance" description="治理面板将在这套新视觉里收敛为策略流和异常处置视图。" />} />
        <Route path="/aliases" element={<PlaceholderPage title="Aliases" description="入口映射和命名转发会接入同一套列表与详情语言。" />} />
        <Route path="/auth" element={<PlaceholderPage title="Auth" description="认证页会延续这一版的单列工作流和状态强调。" />} />
        <Route path="/catalog" element={<PlaceholderPage title="Catalog" description="能力目录会重做成更适合扫描的操作图谱。" />} />
        <Route path="/drift" element={<PlaceholderPage title="Drift" description="漂移视图会升级为时间线与差异并排的结构。" />} />
        <Route path="/logs" element={<PlaceholderPage title="Logs" description="日志页会重点强化过滤、级别和追踪关联。" />} />
        <Route path="/extensions" element={<PlaceholderPage title="Extensions" description="扩展生态会在新壳里作为独立子系统呈现。" />} />
      </Route>
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
