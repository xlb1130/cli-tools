import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { useAppLogs, useDriftReport, useReliabilityStatus, useSources } from "../lib/api";
import { formatDate } from "../lib/format";

export function GovernancePage() {
  const sourcesQuery = useSources();
  const [selectedSource, setSelectedSource] = useState("");
  const reliabilityQuery = useReliabilityStatus();
  const driftQuery = useDriftReport(selectedSource || undefined);
  const logsQuery = useAppLogs({ limit: 40 });

  useEffect(() => {
    if (!selectedSource && sourcesQuery.data?.length) {
      setSelectedSource(sourcesQuery.data[0].name);
    }
  }, [selectedSource, sourcesQuery.data]);

  const loading = sourcesQuery.isLoading || reliabilityQuery.isLoading || driftQuery.isLoading || logsQuery.isLoading;
  const error = sourcesQuery.error || reliabilityQuery.error || driftQuery.error || logsQuery.error;

  const reliability = reliabilityQuery.data;
  const drift = driftQuery.data;
  const rateLimiters = Object.entries(reliability?.status?.rate_limits || {});
  const concurrencyScopes = Object.entries(reliability?.status?.concurrency || {});
  const highlightedLogs = (logsQuery.data ?? [])
    .filter((item) => {
      if (item.level === "WARNING" || item.level === "ERROR") {
        return true;
      }
      return /(rate_limit|concurrency|idempotency|retry|drift|sync|auth)/i.test(item.event || "");
    })
    .slice(0, 10);
  const sourceState = drift?.source_drift_state;
  const governedMounts = useMemo(
    () => (drift?.drift_governance?.mounts ? Object.values(drift.drift_governance.mounts) : []),
    [drift?.drift_governance],
  );

  if (loading) {
    return <LoadingState label="加载 governance 视图" />;
  }

  if (error) {
    return <ErrorState title="Governance 页面加载失败" error={error} />;
  }

  return (
    <div className="page-stack">
      <section className="stats-grid">
        <StatCard label="Drift Source" value={selectedSource || "-"} />
        <StatCard label="Drift Severity" value={String(sourceState?.severity || drift?.drift_summary?.severity || "clean")} />
        <StatCard label="Retry Attempts" value={String(reliability?.defaults?.retry?.max_attempts ?? "-")} />
        <StatCard label="Per Source Concurrency" value={String(reliability?.defaults?.concurrency?.max_inflight_per_source ?? "-")} />
      </section>

      <div className="content-grid two-col">
        <Panel title="Reliability Defaults" subtitle="当前全局 retry / timeout / concurrency 默认值" kicker="Policy">
          <div className="stack">
            <div className="pill-row">
              <span className="sidebar-chip">Budgets {reliability?.configured_budget_count ?? 0}</span>
              <span className="sidebar-chip">Rate Limiters {rateLimiters.length}</span>
              <span className="sidebar-chip">Idempotency {reliability?.status?.idempotency?.total_records ?? 0}</span>
            </div>
            <dl className="detail-grid">
              <div>
                <dt>Timeout</dt>
                <dd>{String(reliability?.defaults?.timeout_seconds ?? "-")}s</dd>
              </div>
              <div>
                <dt>Backoff</dt>
                <dd>{String(reliability?.defaults?.retry?.backoff?.strategy || "-")}</dd>
              </div>
              <div>
                <dt>Base Delay</dt>
                <dd>{String(reliability?.defaults?.retry?.backoff?.base_delay_ms ?? "-")}ms</dd>
              </div>
              <div>
                <dt>Global Concurrency</dt>
                <dd>{String(reliability?.defaults?.concurrency?.max_inflight_global ?? "-")}</dd>
              </div>
            </dl>
            <JsonViewer data={reliability?.configured_budgets ?? {}} />
          </div>
        </Panel>

        <Panel
          title="Drift Watch"
          subtitle="选一个 source 看当前治理状态"
          kicker="Governance"
          actions={
            <select className="field" value={selectedSource} onChange={(event) => setSelectedSource(event.target.value)}>
              {(sourcesQuery.data ?? []).map((source) => (
                <option key={source.name} value={source.name}>
                  {source.name}
                </option>
              ))}
            </select>
          }
        >
          <div className="stack">
            <dl className="detail-grid">
              <div>
                <dt>Status</dt>
                <dd>{sourceState?.status || "-"}</dd>
              </div>
              <div>
                <dt>Severity</dt>
                <dd>{String(sourceState?.severity || drift?.drift_summary?.severity || "-")}</dd>
              </div>
              <div>
                <dt>Affected</dt>
                <dd>{String(sourceState?.affected_mount_count ?? 0)}</dd>
              </div>
              <div>
                <dt>Accepted</dt>
                <dd>{String(sourceState?.accepted_mount_count ?? 0)}</dd>
              </div>
            </dl>
            <div className="inline-actions inline-actions-start">
              <Link to="/drift" className="secondary-button">
                Open Drift Page
              </Link>
            </div>
            <JsonViewer data={sourceState || drift?.drift_summary || {}} />
          </div>
        </Panel>
      </div>

      <Panel title="Runtime Guardrails" subtitle="rate limit / concurrency / idempotency 当前状态" kicker="Runtime">
        <div className="content-grid two-col">
          <div className="table-like">
            {rateLimiters.length ? (
              rateLimiters.map(([key, limiter]) => (
                <article key={key} className="row-card row-card-rich">
                  <div>
                    <strong>{key}</strong>
                    <p>
                      requests={limiter.total_requests} limited={limiter.total_limited}
                    </p>
                    <p className="muted">tokens={Math.round(limiter.tokens * 100) / 100}</p>
                  </div>
                </article>
              ))
            ) : (
              <div className="state">暂无活跃 rate limiter。</div>
            )}
          </div>
          <div className="table-like">
            {concurrencyScopes.length ? (
              concurrencyScopes.map(([key, scope]) => (
                <article key={key} className="row-card row-card-rich">
                  <div>
                    <strong>{key}</strong>
                    <p>
                      current={String(scope.current_concurrent ?? 0)} / max={String(scope.max_concurrent ?? "-")}
                    </p>
                    <p className="muted">timeouts={String(scope.total_timeouts ?? 0)}</p>
                  </div>
                </article>
              ))
            ) : (
              <div className="state">暂无活跃 concurrency scope。</div>
            )}
          </div>
        </div>
        <div className="content-grid two-col">
          <div className="state">
            <strong>Idempotency Cache</strong>
            <p>
              total={reliability?.status?.idempotency?.total_records ?? 0} pending={reliability?.status?.idempotency?.pending ?? 0} completed=
              {reliability?.status?.idempotency?.completed ?? 0} failed=
              {reliability?.status?.idempotency?.failed ?? 0}
            </p>
            <p className="muted">{reliability?.status?.idempotency?.cache_dir ?? "-"}</p>
          </div>
          <div className="state">
            <strong>Governed Mounts</strong>
            <p>{governedMounts.length} mount state(s) in current drift governance report.</p>
            <div className="inline-actions inline-actions-start">
              <Link to="/logs" className="secondary-button">
                Open Logs Page
              </Link>
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Recent Signals" subtitle="最近值得看的 warning / error / governance 相关事件" kicker="Watchlist">
        <div className="event-list">
          {highlightedLogs.length ? (
            highlightedLogs.map((item, index) => (
              <article key={`${item.ts}:${item.event}:${index}`} className="event-card">
                <div className="event-card-top">
                  <div>
                    <strong>{item.event}</strong>
                    <p className="muted">{formatDate(item.ts)}</p>
                  </div>
                  <span className={signalBadge(item.level)}>{item.level}</span>
                </div>
                <p>{item.message || item.source || item.mount_id || "-"}</p>
                <JsonViewer data={item.data || {}} />
              </article>
            ))
          ) : (
            <div className="state">最近没有明显的治理信号。</div>
          )}
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

function signalBadge(level: string) {
  if (level === "ERROR") return "badge badge-danger";
  if (level === "WARNING") return "badge badge-warn";
  return "badge badge-neutral";
}
