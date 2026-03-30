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
          <div className="brand-logo">
            <div className="brand-logo-icon">
              <span className="brand-logo-dot" />
              <span className="brand-logo-dot" />
              <span className="brand-logo-dot" />
              <span className="brand-logo-dot" />
            </div>
            <div>
              <p className="brand-kicker">Capability Transit System</p>
              <h1>CTS Console</h1>
            </div>
          </div>
          <p className="brand-copy">
            统一的能力控制台，整合 source、mount 与 stable entry。
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
        <header className="topbar-premium">
          <div className="topbar-brand">
            <div className="topbar-brand-icon">
              <Icon name="dashboard" size={18} />
            </div>
            <div>
              <h2>Workspace Console</h2>
              <p>集中查看运行态摘要与系统状态</p>
            </div>
          </div>

          <div className="topbar-content">
            {summaryQuery.isLoading ? (
              <LoadingState compact label="读取应用摘要" />
            ) : summaryQuery.isError ? (
              <ErrorState compact title="无法读取应用摘要" error={summaryQuery.error} />
            ) : summaryQuery.data ? (
              <>
                <div className="topbar-stat">
                  <span className="topbar-stat-icon">
                    <Icon name="auth" size={14} />
                  </span>
                  <div>
                    <span className="topbar-stat-label">Profile</span>
                    <span className="topbar-stat-value">{summaryQuery.data.profile || "default"}</span>
                  </div>
                </div>
                <div className="topbar-stat">
                  <span className="topbar-stat-icon">
                    <Icon name="sources" size={14} />
                  </span>
                  <div>
                    <span className="topbar-stat-label">Config Files</span>
                    <span className="topbar-stat-value">{summaryQuery.data.config_files.length}</span>
                  </div>
                </div>
                <div className="topbar-stat topbar-stat-wide">
                  <span className="topbar-stat-icon">
                    <Icon name="mounts" size={14} />
                  </span>
                  <div>
                    <span className="topbar-stat-label">Surfaces</span>
                    <SurfacePills surfaces={summaryQuery.data.surfaces} />
                  </div>
                </div>
              </>
            ) : null}
          </div>

          <div className="topbar-actions">
            <div className="theme-switcher">
              <button
                type="button"
                className={`theme-btn ${mode === "light" ? "active" : ""}`}
                onClick={() => setMode("light")}
                title="Light mode"
              >
                <Icon name="auth" size={16} />
              </button>
              <button
                type="button"
                className={`theme-btn ${mode === "dark" ? "active" : ""}`}
                onClick={() => setMode("dark")}
                title="Dark mode"
              >
                <Icon name="drift" size={16} />
              </button>
              <button
                type="button"
                className={`theme-btn ${mode === "system" ? "active" : ""}`}
                onClick={() => setMode("system")}
                title="System preference"
              >
                <Icon name="extensions" size={16} />
              </button>
            </div>
            <div className="theme-indicator">
              <span className="theme-indicator-label">
                {mode === "system" ? `System · ${resolvedTheme === "dark" ? "Dark" : "Light"}` : mode === "dark" ? "Dark" : "Light"}
              </span>
            </div>
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  );
}
