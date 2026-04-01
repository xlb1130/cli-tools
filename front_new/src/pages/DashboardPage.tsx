import { Link } from "react-router-dom";

import { useAppSummary, useMounts, useReloadApp, useRuns, useSources, useSyncAll } from "../lib/api";
import { formatDate, formatNumber, summarizeSurfaceMap } from "../lib/format";
import { ErrorBlock, LoadingBlock, MetricLine, Panel, RouteCard, Stat, StatusPill, SurfaceStack } from "../components/ui";

export function DashboardPage() {
  const summaryQuery = useAppSummary();
  const sourcesQuery = useSources();
  const mountsQuery = useMounts();
  const runsQuery = useRuns(8);
  const reloadMutation = useReloadApp();
  const syncMutation = useSyncAll();

  if (summaryQuery.isLoading || sourcesQuery.isLoading || mountsQuery.isLoading || runsQuery.isLoading) {
    return <LoadingBlock label="加载全局态势" />;
  }

  if (summaryQuery.isError) return <ErrorBlock title="Dashboard 读取失败" error={summaryQuery.error} />;
  if (sourcesQuery.isError) return <ErrorBlock title="Sources 读取失败" error={sourcesQuery.error} />;
  if (mountsQuery.isError) return <ErrorBlock title="Mounts 读取失败" error={mountsQuery.error} />;
  if (runsQuery.isError) return <ErrorBlock title="Runs 读取失败" error={runsQuery.error} />;

  const summary = summaryQuery.data!;
  const sources = sourcesQuery.data ?? [];
  const mounts = mountsQuery.data ?? [];
  const runs = runsQuery.data ?? [];
  const enabledSurfaces = summarizeSurfaceMap(summary.surfaces);
  const unhealthySources = sources.filter((item) => !item.health?.ok).length;
  const riskyMounts = mounts.filter((item) => item.risk !== "read").length;
  const failedRuns = runs.filter((item) => !item.ok).length;

  return (
    <div className="page">
      <section className="hero-grid">
        <div className="hero-panel">
          <p className="eyebrow">System Snapshot</p>
          <h1>把接入、能力入口和执行轨迹收拢到同一块工作台里。</h1>
          <p className="hero-copy">
            这一屏优先回答三个问题: 现在接了多少 source, 哪些能力入口风险更高, 最近执行链路有没有出现失败信号。
          </p>
          <div className="hero-actions">
            <button className="action-button" onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending}>
              {reloadMutation.isPending ? "Reloading" : "Reload Runtime"}
            </button>
            <button className="ghost-button" onClick={() => syncMutation.mutate()} disabled={syncMutation.isPending}>
              {syncMutation.isPending ? "Syncing" : "Sync Sources"}
            </button>
          </div>
        </div>

        <div className="hero-aside">
          <Stat label="Sources" value={formatNumber(summary.source_count)} meta={`${unhealthySources} 需要检查`} />
          <Stat label="Mounts" value={formatNumber(summary.mount_count)} meta={`${riskyMounts} 非只读`} />
          <Stat label="Surfaces" value={formatNumber(enabledSurfaces.length)} meta={enabledSurfaces.join(", ") || "none"} />
          <Stat label="Recent Failures" value={formatNumber(failedRuns)} meta="最近 8 条运行记录" />
        </div>
      </section>

      <section className="dashboard-grid">
        <Panel title="System Signals" eyebrow="Overview">
          <div className="metric-list">
            <MetricLine label="Active Profile" value={summary.profile || "default"} />
            <MetricLine label="Config Files" value={summary.config_files.length} />
            <MetricLine label="Discovery Errors" value={summary.discovery_error_count} />
            <MetricLine label="History DB" value={summary.runtime_paths.history_db} />
          </div>
        </Panel>

        <Panel title="Main Routes" eyebrow="Workspace">
          <div className="route-grid">
            <RouteCard to="/sources" title="Sources" description="看 provider、auth 和健康。" meta={<StatusPill tone={unhealthySources ? "warn" : "good"}>{unhealthySources ? `${unhealthySources} issues` : "healthy"}</StatusPill>} />
            <RouteCard to="/mounts" title="Mounts" description="看稳定入口、surface 和风险。" meta={<StatusPill tone={riskyMounts ? "warn" : "neutral"}>{riskyMounts} risky</StatusPill>} />
            <RouteCard to="/runs" title="Runs" description="追执行结果和失败链路。" meta={<StatusPill tone={failedRuns ? "bad" : "good"}>{failedRuns} failed</StatusPill>} />
          </div>
        </Panel>
      </section>

      <section className="dashboard-grid">
        <Panel title="Source Watchlist" eyebrow="Health">
          <div className="stack-list">
            {sources.slice(0, 5).map((source) => (
              <Link key={source.name} to={`/sources/${source.name}`} className="list-row">
                <div>
                  <strong>{source.name}</strong>
                  <p>
                    {source.type} · {source.discovery_mode}
                  </p>
                </div>
                <StatusPill tone={source.health?.ok ? "good" : "warn"}>{source.health?.ok ? "healthy" : "needs check"}</StatusPill>
              </Link>
            ))}
          </div>
        </Panel>

        <Panel title="Recent Runs" eyebrow="Execution">
          <div className="stack-list">
            {runs.map((run) => (
              <Link key={run.run_id} to={`/runs/${run.run_id}`} className="list-row">
                <div>
                  <strong>{run.mount_id || run.run_id}</strong>
                  <p>
                    {run.mode} · {formatDate(run.ts_start)}
                  </p>
                </div>
                <StatusPill tone={run.ok ? "good" : "bad"}>{run.ok ? "ok" : run.error_code || "failed"}</StatusPill>
              </Link>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="Priority Mounts" eyebrow="Command Surface" aside={<SurfaceStack items={enabledSurfaces} />}>
        <div className="priority-grid">
          {mounts.slice(0, 6).map((mount) => (
            <Link key={mount.mount_id} to={`/mounts/${mount.mount_id}`} className="priority-card">
              <div className="priority-top">
                <StatusPill tone={mount.risk === "read" ? "neutral" : mount.risk === "write" ? "warn" : "bad"}>{mount.risk}</StatusPill>
                <span>{mount.provider_type}</span>
              </div>
              <h3>{mount.summary || mount.mount_id}</h3>
              <p>{mount.stable_name}</p>
              <small>{mount.command_path.join(" ")}</small>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
