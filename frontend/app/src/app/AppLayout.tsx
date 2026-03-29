import { NavLink, Outlet } from "react-router-dom";

import { useAppSummary } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { SurfacePills } from "../components/SurfacePills";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/sources", label: "Sources" },
  { to: "/extensions", label: "Extensions" },
  { to: "/mounts", label: "Mounts" },
  { to: "/catalog", label: "Catalog" },
  { to: "/runs", label: "Runs" },
];

export function AppLayout() {
  const summaryQuery = useAppSummary();

  return (
    <div className="shell">
      <aside className="shell-sidebar">
        <div className="brand-block">
          <p className="brand-kicker">Capability Transit System</p>
          <h1>cts Console</h1>
          <p className="brand-copy">
            本地能力控制台。你看到的是统一后的 source、mount、stable entry，而不是一堆零散配置。
          </p>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="sidebar-chip">Read-only MVP</span>
          <span className="sidebar-chip">API-first</span>
        </div>
      </aside>

      <main className="shell-main">
        <header className="topbar">
          {summaryQuery.isLoading ? (
            <LoadingState compact label="读取应用摘要" />
          ) : summaryQuery.isError ? (
            <ErrorState compact title="无法读取应用摘要" error={summaryQuery.error} />
          ) : summaryQuery.data ? (
            <>
              <div>
                <p className="eyebrow">Current Profile</p>
                <div className="topbar-metric">{summaryQuery.data.profile || "default"}</div>
              </div>
              <div>
                <p className="eyebrow">Config Files</p>
                <div className="topbar-metric">{summaryQuery.data.config_files.length}</div>
              </div>
              <div>
                <p className="eyebrow">Runtime Surfaces</p>
                <SurfacePills surfaces={summaryQuery.data.surfaces} />
              </div>
            </>
          ) : null}
        </header>

        <Outlet />
      </main>
    </div>
  );
}
