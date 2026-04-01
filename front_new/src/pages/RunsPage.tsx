import { Link } from "react-router-dom";

import { useRuns } from "../lib/api";
import { formatDate } from "../lib/format";
import { ErrorBlock, LoadingBlock, Panel, StatusPill } from "../components/ui";

export function RunsPage() {
  const runsQuery = useRuns(36);

  if (runsQuery.isLoading) return <LoadingBlock label="加载 runs" />;
  if (runsQuery.isError) return <ErrorBlock title="Runs 读取失败" error={runsQuery.error} />;

  const runs = runsQuery.data ?? [];

  return (
    <div className="page">
      <Panel title="Runs" eyebrow="Execution Timeline">
        <div className="inventory-list">
          {runs.map((run) => (
            <Link key={run.run_id} to={`/runs/${run.run_id}`} className="inventory-row">
              <div className="inventory-main">
                <div className="inventory-title">
                  <strong>{run.mount_id || run.run_id}</strong>
                  <StatusPill tone={run.ok ? "good" : "bad"}>{run.ok ? "ok" : run.error_code || "failed"}</StatusPill>
                </div>
                <p>
                  {run.surface} · {run.mode} · {run.source || "unknown source"}
                </p>
              </div>
              <div className="inventory-meta">
                <small>{formatDate(run.ts_start)}</small>
                <small>{run.summary || "No summary"}</small>
              </div>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
