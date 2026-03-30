import { NavLink, Outlet } from "react-router-dom";

import { useAppSummary } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { Icon } from "../components/Icon";
import { LoadingState } from "../components/LoadingState";
import { SurfacePills } from "../components/SurfacePills";
import { useTheme } from "./theme";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "dashboard" as const },
  { to: "/governance", label: "Governance", icon: "governance" as const },
  { to: "/sources", label: "Sources", icon: "sources" as const },
  { to: "/aliases", label: "Aliases", icon: "aliases" as const },
  { to: "/auth", label: "Auth", icon: "auth" as const },
  { to: "/drift", label: "Drift", icon: "drift" as const },
  { to: "/logs", label: "Logs", icon: "logs" as const },
  { to: "/extensions", label: "Extensions", icon: "extensions" as const },
  { to: "/mounts", label: "Mounts", icon: "mounts" as const },
  { to: "/catalog", label: "Catalog", icon: "catalog" as const },
  { to: "/runs", label: "Runs", icon: "runs" as const },
];

export function AppLayout() {
  const summaryQuery = useAppSummary();
  const { mode, resolvedTheme, setMode } = useTheme();

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
              <span className="nav-link-icon" aria-hidden="true">
                <Icon name={item.icon} size={16} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="sidebar-chip">Adaptive Theme</span>
          <span className="sidebar-chip">API-first</span>
        </div>
      </aside>

      <main className="shell-main">
        <header className="page-header">
          <div className="page-header-copy">
            <p className="brand-kicker">Workspace Console</p>
            <h2>控制台总览</h2>
            <p className="theme-copy">集中查看运行态摘要，并在右上角快速切换界面主题。</p>
          </div>

          <div className="page-header-actions">
            <div className="appearance-switcher">
              <div className="appearance-label">
                <span>Appearance Mode</span>
                <strong>{mode === "system" ? `System · ${resolvedTheme === "dark" ? "Dark" : "Light"}` : mode === "dark" ? "Dark" : "Light"}</strong>
              </div>
              <div className="theme-toggle theme-toggle-compact" role="tablist" aria-label="Theme mode">
                <button type="button" className={mode === "light" ? "theme-option active" : "theme-option"} onClick={() => setMode("light")}>
                  Light
                </button>
                <button type="button" className={mode === "dark" ? "theme-option active" : "theme-option"} onClick={() => setMode("dark")}>
                  Dark
                </button>
                <button type="button" className={mode === "system" ? "theme-option active" : "theme-option"} onClick={() => setMode("system")}>
                  System
                </button>
              </div>
            </div>
          </div>
        </header>

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
              <div>
                <p className="eyebrow">Theme Mode</p>
                <div className="topbar-metric topbar-metric-small">{mode === "system" ? `system · ${resolvedTheme}` : mode}</div>
              </div>
            </>
          ) : null}
        </header>

        <Outlet />
      </main>
    </div>
  );
}
