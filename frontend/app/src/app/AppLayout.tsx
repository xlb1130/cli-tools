import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAppSummary } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { Icon } from "../components/Icon";
import { LoadingState } from "../components/LoadingState";
import { SurfacePills } from "../components/SurfacePills";
import { useTheme } from "./theme";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "dashboard" as const, section: "Overview", description: "总体态势与核心摘要" },
  {
    to: "/governance",
    label: "Governance",
    icon: "governance" as const,
    section: "Control",
    description: "策略、可靠性与治理状态",
  },
  { to: "/sources", label: "Sources", icon: "sources" as const, section: "Control", description: "源配置与接入质量" },
  { to: "/aliases", label: "Aliases", icon: "aliases" as const, section: "Control", description: "入口映射与命名转发" },
  { to: "/auth", label: "Auth", icon: "auth" as const, section: "Control", description: "认证配置与会话健康" },
  { to: "/mounts", label: "Mounts", icon: "mounts" as const, section: "Runtime", description: "挂载能力与运行入口" },
  { to: "/catalog", label: "Catalog", icon: "catalog" as const, section: "Runtime", description: "可调用能力目录" },
  { to: "/runs", label: "Runs", icon: "runs" as const, section: "Runtime", description: "执行记录与任务轨迹" },
  { to: "/drift", label: "Drift", icon: "drift" as const, section: "Observe", description: "变更漂移与异常发现" },
  { to: "/logs", label: "Logs", icon: "logs" as const, section: "Observe", description: "日志事件与审计线索" },
  {
    to: "/extensions",
    label: "Extensions",
    icon: "extensions" as const,
    section: "Observe",
    description: "插件、Hook 与扩展生态",
  },
] as const;

type NavItem = (typeof NAV_ITEMS)[number];
type NavSection = NavItem["section"];
type SectionState = Record<NavSection, boolean>;

const SECTION_ORDER = Array.from(new Set(NAV_ITEMS.map((item) => item.section))) as NavSection[];
const SIDEBAR_COMPACT_STORAGE_KEY = "cts-console-sidebar-compact";

function getDefaultSectionState(activeSection: NavSection): SectionState {
  return SECTION_ORDER.reduce((acc, section) => {
    acc[section] = section === activeSection || section === "Overview";
    return acc;
  }, {} as SectionState);
}

export function AppLayout() {
  const summaryQuery = useAppSummary();
  const { mode, resolvedTheme, setMode } = useTheme();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCompact, setSidebarCompact] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COMPACT_STORAGE_KEY) === "true";
  });
  const activeItem =
    [...NAV_ITEMS]
      .sort((a, b) => b.to.length - a.to.length)
      .find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to))) ?? NAV_ITEMS[0];
  const navSections = NAV_ITEMS.reduce<Record<string, NavItem[]>>((acc, item) => {
    const group = acc[item.section] ?? [];
    group.push(item);
    acc[item.section] = group;
    return acc;
  }, {});
  const [expandedSections, setExpandedSections] = useState<SectionState>(() => getDefaultSectionState(activeItem.section));

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    setExpandedSections((current) => ({
      ...current,
      [activeItem.section]: true,
    }));
  }, [activeItem.section]);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COMPACT_STORAGE_KEY, String(sidebarCompact));
  }, [sidebarCompact]);

  useEffect(() => {
    if (!sidebarOpen) {
      document.body.style.overflow = "";
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [sidebarOpen]);

  const toggleSection = (section: NavSection) => {
    if (sidebarCompact) {
      return;
    }

    setExpandedSections((current) => {
      const isExpanded = current[section];
      const newState: SectionState = {} as SectionState;

      // 收起所有其他section
      SECTION_ORDER.forEach((s) => {
        newState[s] = s === section ? !isExpanded : false;
      });

      return newState;
    });
  };

  return (
    <div className="app-shell">
      <header className="global-topbar">
        <div className="global-topbar-brand">
          <button
            type="button"
            className="global-nav-btn"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label="Toggle navigation"
            aria-expanded={sidebarOpen}
          >
            <Icon name="catalog" size={18} />
          </button>
          <div className="global-brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="global-brand-copy">
            <p className="global-brand-kicker">Capability Transit System</p>
            <h1>CTS Console</h1>
            <p>统一的能力控制台与运行态工作台</p>
          </div>
        </div>

        <div className="global-topbar-center">
          <span className="global-status-chip">{activeItem.section}</span>
          <span className="global-status-copy">{activeItem.label}</span>
        </div>

        <div className="global-topbar-actions">
          <button
            type="button"
            className={`global-action-btn sidebar-desktop-toggle ${sidebarCompact ? "active" : ""}`}
            onClick={() => setSidebarCompact((current) => !current)}
            aria-label={sidebarCompact ? "Expand sidebar" : "Collapse sidebar"}
            title={sidebarCompact ? "Expand sidebar" : "Collapse sidebar"}
          >
            <span className="sidebar-rail-toggle-lines" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span>{sidebarCompact ? "展开侧栏" : "收起侧栏"}</span>
          </button>

          <div className="theme-switcher global-theme-switcher">
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

          <div className="theme-indicator global-theme-indicator">
            <span className="theme-indicator-label">
              {mode === "system" ? `System · ${resolvedTheme === "dark" ? "Dark" : "Light"}` : mode === "dark" ? "Dark" : "Light"}
            </span>
          </div>
        </div>
      </header>

      <div className={`shell ${sidebarCompact ? "sidebar-compact" : ""}`}>
        <div
          className={`shell-backdrop ${sidebarOpen ? "active" : ""}`}
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />

        <aside className={`shell-sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="sidebar-mobile-header">
            <span>Navigation</span>
            <button type="button" className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
              <Icon name="extensions" size={16} />
            </button>
          </div>

          <div className="sidebar-scroll">
            <div className="brand-block">
              <div className="brand-logo">
                <div className="brand-logo-icon">
                  <span className="brand-logo-dot" />
                  <span className="brand-logo-dot" />
                  <span className="brand-logo-dot" />
                  <span className="brand-logo-dot" />
                </div>
                <div>
                  <p className="brand-kicker">Navigation Hub</p>
                  <h1>Workspace</h1>
                </div>
              </div>
              <p className="brand-copy">
                浏览模块、查看分组，并在桌面端通过顶部操作切换布局。
              </p>
              <div className="brand-summary">
                <div className="brand-summary-item">
                  <span>Sources</span>
                  <strong>{summaryQuery.data?.source_count ?? "--"}</strong>
                </div>
                <div className="brand-summary-item">
                  <span>Mounts</span>
                  <strong>{summaryQuery.data?.mount_count ?? "--"}</strong>
                </div>
                <div className="brand-summary-item">
                  <span>Configs</span>
                  <strong>{summaryQuery.data?.config_files.length ?? "--"}</strong>
                </div>
              </div>
            </div>

            {SECTION_ORDER.map((section) => {
              const items = navSections[section] ?? [];
              const isExpanded = expandedSections[section];
              const isActiveSection = activeItem.section === section;

              return (
              <div className={`nav-section ${isExpanded ? "expanded" : "collapsed"} ${isActiveSection ? "nav-section-current" : ""}`} key={section}>
                <button
                  type="button"
                  className={`nav-section-trigger ${isActiveSection ? "active" : ""}`}
                  onClick={() => toggleSection(section)}
                  aria-expanded={isExpanded}
                  aria-label={`${section} section`}
                  title={sidebarCompact ? section : undefined}
                >
                  <span className="nav-section-heading">
                    <span className="nav-section-label">{section}</span>
                    <span className="nav-section-count">{items.length}</span>
                  </span>
                  <span className="nav-section-caret" aria-hidden="true" />
                </button>
                <nav className={`nav-list ${isExpanded || sidebarCompact ? "expanded" : "collapsed"}`}>
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                      title={sidebarCompact ? item.label : undefined}
                    >
                      <span className="nav-link-icon" aria-hidden="true">
                        <Icon name={item.icon} size={16} />
                      </span>
                      <span className="nav-link-copy">
                        <span className="nav-link-label">{item.label}</span>
                        <span className="nav-link-meta">{item.description}</span>
                      </span>
                    </NavLink>
                  ))}
                </nav>
              </div>
              );
            })}

            <div className="sidebar-footer">
              <span className="sidebar-chip">Adaptive Theme</span>
              <span className="sidebar-chip">API-first</span>
            </div>
          </div>
        </aside>

        <main className="shell-main">
          <header className="topbar-premium">
            <div className="topbar-brand">
              <div className="topbar-brand-icon">
                <Icon name={activeItem.icon} size={18} />
              </div>
              <div className="topbar-brand-copy">
                <div className="topbar-context">
                  <span className="topbar-context-pill">{activeItem.section}</span>
                  <span className="topbar-context-path">{activeItem.label}</span>
                </div>
                <div>
                  <h2>{activeItem.label}</h2>
                  <p>{activeItem.description}</p>
                </div>
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
                  <div className="topbar-stat">
                    <span className="topbar-stat-icon">
                      <Icon name="dashboard" size={14} />
                    </span>
                    <div>
                      <span className="topbar-stat-label">Footprint</span>
                      <span className="topbar-stat-value">
                        {summaryQuery.data.source_count} sources / {summaryQuery.data.mount_count} mounts
                      </span>
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
          </header>

          <Outlet />
        </main>
      </div>
    </div>
  );
}
