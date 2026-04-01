import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAppSummary } from "../lib/api";
import { formatNumber, summarizeSurfaceMap } from "../lib/format";
import { ErrorBlock, LoadingBlock, SurfaceStack } from "../components/ui";

const NAV = [
  { to: "/", label: "Overview", detail: "态势与告警" },
  { to: "/sources", label: "Sources", detail: "接入与健康" },
  { to: "/mounts", label: "Mounts", detail: "能力入口" },
  { to: "/runs", label: "Runs", detail: "执行轨迹" },
  { to: "/governance", label: "Governance", detail: "策略与预算" },
  { to: "/catalog", label: "Catalog", detail: "能力地图" },
  { to: "/drift", label: "Drift", detail: "变更与偏移" },
  { to: "/logs", label: "Logs", detail: "事件与审计" },
  { to: "/extensions", label: "Extensions", detail: "插件与 Hook" },
  { to: "/auth", label: "Auth", detail: "认证状态" },
  { to: "/aliases", label: "Aliases", detail: "命令映射" },
];

export function AppShell() {
  const summaryQuery = useAppSummary();
  const location = useLocation();
  const active = NAV.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to))) ?? NAV[0];

  return (
    <div className="command-center">
      <aside className="sidebar">
        <div className="brand">
          <p className="brand-kicker">CTS New UI</p>
          <h1>Command Center</h1>
          <p>为运行态、接入面和执行链路重新整理后的控制台。</p>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              <span>{item.label}</span>
              <small>{item.detail}</small>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footnote">
          <span>Workspace</span>
          <strong>{active.label}</strong>
        </div>
      </aside>

      <main className="main-stage">
        <header className="masthead">
          <div className="masthead-copy">
            <p className="eyebrow">Runtime Console</p>
            <h2>{active.label}</h2>
            <p>{active.detail}</p>
          </div>

          <div className="masthead-rail">
            {summaryQuery.isLoading ? (
              <LoadingBlock label="读取应用摘要" />
            ) : summaryQuery.isError ? (
              <ErrorBlock title="无法读取应用摘要" error={summaryQuery.error} />
            ) : summaryQuery.data ? (
              <>
                <div className="signal-box">
                  <span>Profile</span>
                  <strong>{summaryQuery.data.profile || "default"}</strong>
                </div>
                <div className="signal-box">
                  <span>Footprint</span>
                  <strong>
                    {formatNumber(summaryQuery.data.source_count)} / {formatNumber(summaryQuery.data.mount_count)}
                  </strong>
                </div>
                <div className="signal-box signal-box-wide">
                  <span>Surfaces</span>
                  <SurfaceStack items={summarizeSurfaceMap(summaryQuery.data.surfaces)} />
                </div>
              </>
            ) : null}
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  );
}
