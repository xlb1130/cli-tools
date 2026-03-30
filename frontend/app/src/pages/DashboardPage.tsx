import { Link } from "react-router-dom";
import { useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useAppSummary, useMounts, useReloadApp, useRuns, useSources, useSyncAll } from "../lib/api";
import { formatDate } from "../lib/format";

export function DashboardPage() {
  const summaryQuery = useAppSummary();
  const sourcesQuery = useSources();
  const mountsQuery = useMounts();
  const runsQuery = useRuns(8);
  const reloadMutation = useReloadApp();
  const syncMutation = useSyncAll();
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  if (summaryQuery.isLoading || sourcesQuery.isLoading || mountsQuery.isLoading || runsQuery.isLoading) {
    return <LoadingState label="加载控制台数据" />;
  }

  if (summaryQuery.isError) {
    return <ErrorState title="Dashboard 加载失败" error={summaryQuery.error} />;
  }

  const summary = summaryQuery.data!;
  const sources = sourcesQuery.data ?? [];
  const mounts = mountsQuery.data ?? [];
  const runs = runsQuery.data ?? [];
  const highRiskMounts = mounts.filter((item) => item.risk !== "read");

  const handleReload = async () => {
    setActionMessage(null);
    try {
      const result = await reloadMutation.mutateAsync();
      setActionMessage(`Reload 完成，当前 mount 数量 ${result.summary.mount_count}。`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Reload 失败。");
    }
  };

  const handleSync = async () => {
    setActionMessage(null);
    try {
      const result = await syncMutation.mutateAsync();
      setActionMessage(`Sync 完成，处理 ${result.items.length} 个 source。`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Sync 失败。");
    }
  };

  return (
    <div className="page-stack">
      <section className="stats-grid">
        <StatCard label="Profile" value={summary.profile || "default"} />
        <StatCard label="Sources" value={String(summary.source_count)} />
        <StatCard label="Mounts" value={String(summary.mount_count)} />
        <StatCard label="High Risk" value={String(highRiskMounts.length)} />
      </section>

      <div className="content-grid two-col">
        <Panel
          title="Loaded Config Files"
          subtitle="后端实际读取并编译的配置路径"
          kicker="Runtime Graph"
          actions={
            <div className="explain-actions">
              <SurfacePills surfaces={summary.surfaces} />
              <button type="button" className="primary-button" onClick={handleReload} disabled={reloadMutation.isPending}>
                {reloadMutation.isPending ? "Reloading..." : "Reload"}
              </button>
              <button type="button" className="secondary-button" onClick={handleSync} disabled={syncMutation.isPending}>
                {syncMutation.isPending ? "Syncing..." : "Sync All"}
              </button>
            </div>
          }
        >
          {actionMessage ? <div className="inline-note">{actionMessage}</div> : null}
          <ul className="plain-list list-grid">
            {summary.config_files.map((file) => (
              <li key={file} className="list-card">
                {file}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Runtime Paths" subtitle="最小日志与 history 存储位置" kicker="Diagnostics">
          <dl className="detail-list">
            <div>
              <dt>app.jsonl</dt>
              <dd>{summary.runtime_paths.app_log}</dd>
            </div>
            <div>
              <dt>audit.jsonl</dt>
              <dd>{summary.runtime_paths.audit_log}</dd>
            </div>
            <div>
              <dt>history.db</dt>
              <dd>{summary.runtime_paths.history_db}</dd>
            </div>
          </dl>
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Source Snapshot" subtitle="最新 source 健康与 discovery 视图">
          <div className="table-like">
            {sources.map((source) => (
              <Link key={source.name} to={`/sources/${source.name}`} className="row-card">
                <div>
                  <strong>{source.name}</strong>
                  <p>
                    {source.type} · {source.discovery_mode}
                  </p>
                </div>
                <span className={source.health?.ok ? "badge badge-safe" : "badge badge-danger"}>
                  {source.health?.ok ? "healthy" : "check"}
                </span>
              </Link>
            ))}
          </div>
        </Panel>

        <Panel title="Recent Runs" subtitle="最近一次调用的最小摘要">
          <div className="table-like">
            {runs.map((run) => (
              <div key={run.run_id} className="row-card">
                <div>
                  <strong>{run.mount_id || run.run_id}</strong>
                  <p>
                    {run.mode} · {formatDate(run.ts_start)}
                  </p>
                </div>
                <span className={run.ok ? "badge badge-safe" : "badge badge-danger"}>
                  {run.ok ? "ok" : run.error_code || "failed"}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="High Signal Mounts" subtitle="默认优先关注非只读能力和关键稳定入口" kicker="Focus">
        <div className="mount-grid">
          {mounts.slice(0, 6).map((mount) => (
            <Link key={mount.mount_id} to={`/mounts/${mount.mount_id}`} className="mount-card">
              <div className="mount-card-top">
                <RiskBadge risk={mount.risk} />
                <span className="mount-provider">{mount.provider_type}</span>
              </div>
              <h3>{mount.summary}</h3>
              <p className="mount-path">{mount.command_path.join(" ")}</p>
              <p className="mount-stable">{mount.stable_name}</p>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}
