import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { useRuns } from "../lib/api";
import { formatDate } from "../lib/format";

export function RunsPage() {
  const runsQuery = useRuns(50);

  if (runsQuery.isLoading) {
    return <LoadingState label="加载 runs" />;
  }

  if (runsQuery.isError) {
    return <ErrorState title="Runs 加载失败" error={runsQuery.error} />;
  }

  const runs = runsQuery.data ?? [];

  return (
    <div className="page-stack">
      <Panel title="Run History" subtitle="最小执行留痕，供前端与排障使用">
        <div className="table-list">
          {runs.map((run) => (
            <article key={run.run_id} className="table-item">
              <div className="table-item-main">
                <div className="table-item-title">
                  <strong>{run.mount_id || run.run_id}</strong>
                  <span className={run.ok ? "badge badge-safe" : "badge badge-danger"}>
                    {run.ok ? "ok" : run.error_code || "failed"}
                  </span>
                </div>
                <p>{run.summary || run.mode}</p>
                <p className="muted">{run.run_id}</p>
              </div>
              <div className="table-item-meta">
                <div>
                  <span className="eyebrow">When</span>
                  <p>{formatDate(run.ts_start)}</p>
                </div>
                <div>
                  <span className="eyebrow">Mode</span>
                  <p>{run.mode}</p>
                </div>
                <div>
                  <span className="eyebrow">Source</span>
                  <p>{run.source || "-"}</p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
