import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { useRun } from "../lib/api";
import { formatDate } from "../lib/format";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const runQuery = useRun(runId);

  if (runQuery.isLoading) {
    return <LoadingState label="加载 run 详情" />;
  }

  if (runQuery.isError) {
    return <ErrorState title="Run 详情加载失败" error={runQuery.error} />;
  }

  const run = runQuery.data!;

  return (
    <div className="page-stack">
      <section className="detail-hero">
        <div>
          <PageTitle
            icon="runs"
            eyebrow="Run Detail"
            title={run.mount_id || run.stable_name || run.run_id}
            description="单条 run 的执行留痕。这里展示的是 `/api/runs/:runId` 原始详情，方便和列表页、logs 页互相跳转排障。"
            compact
          />
        </div>
        <div className="detail-hero-side">
          <span className={run.ok ? "badge badge-safe" : "badge badge-danger"}>{run.ok ? "ok" : run.error_code || "failed"}</span>
          <Link to="/runs" className="secondary-button">
            Back to Runs
          </Link>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="Started" value={formatDate(run.ts_start)} />
        <StatCard label="Ended" value={formatDate(run.ts_end)} />
        <StatCard label="Surface" value={run.surface || "-"} />
        <StatCard label="Mode" value={run.mode || "-"} />
      </section>

      <div className="content-grid two-col">
        <Panel title="Run Summary" subtitle="用户关心的最小诊断字段">
          <dl className="detail-grid">
            <div>
              <dt>Run ID</dt>
              <dd>{run.run_id}</dd>
            </div>
            <div>
              <dt>Trace ID</dt>
              <dd>{run.trace_id || "-"}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{run.source || "-"}</dd>
            </div>
            <div>
              <dt>Operation</dt>
              <dd>{run.operation_id || "-"}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{run.provider_type || "-"}</dd>
            </div>
            <div>
              <dt>Exit Code</dt>
              <dd>{String(run.exit_code)}</dd>
            </div>
            <div>
              <dt>Error Type</dt>
              <dd>{run.error_type || "-"}</dd>
            </div>
            <div>
              <dt>Error Code</dt>
              <dd>{run.error_code || "-"}</dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Execution Notes" subtitle="摘要和 metadata 原样透出">
          <div className="stack">
            <div className="state">
              <strong>Summary</strong>
              <p>{run.summary || "-"}</p>
            </div>
            <div>
              <p className="eyebrow">Metadata</p>
              <JsonViewer data={run.metadata || {}} />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Raw Payload" subtitle="保留后端记录的完整 JSON">
        <JsonViewer data={run} />
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
