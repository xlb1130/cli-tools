import { useParams } from "react-router-dom";

import { useRun } from "../lib/api";
import { formatDate } from "../lib/format";
import { ErrorBlock, LoadingBlock, MetricLine, Panel, StatusPill } from "../components/ui";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const runQuery = useRun(runId);

  if (runQuery.isLoading) return <LoadingBlock label="加载 run 详情" />;
  if (runQuery.isError) return <ErrorBlock title="Run 详情读取失败" error={runQuery.error} />;

  const run = runQuery.data!;

  return (
    <div className="page">
      <section className="detail-strip">
        <div>
          <p className="eyebrow">Run Detail</p>
          <h1>{run.mount_id || run.stable_name || run.run_id}</h1>
          <p className="hero-copy">{run.summary || "这里展示单次执行的时间、状态和链路上下文。"} </p>
        </div>
        <div className="detail-strip-meta">
          <StatusPill tone={run.ok ? "good" : "bad"}>{run.ok ? "ok" : run.error_code || "failed"}</StatusPill>
        </div>
      </section>

      <section className="dashboard-grid">
        <Panel title="Lifecycle" eyebrow="Timing">
          <div className="metric-list">
            <MetricLine label="Started" value={formatDate(run.ts_start)} />
            <MetricLine label="Ended" value={formatDate(run.ts_end)} />
            <MetricLine label="Surface" value={run.surface} />
            <MetricLine label="Mode" value={run.mode} />
          </div>
        </Panel>

        <Panel title="Context" eyebrow="Trace">
          <div className="metric-list">
            <MetricLine label="Run ID" value={run.run_id} />
            <MetricLine label="Trace ID" value={run.trace_id || "-"} />
            <MetricLine label="Source" value={run.source || "-"} />
            <MetricLine label="Operation" value={run.operation_id || "-"} />
          </div>
        </Panel>
      </section>
    </div>
  );
}
