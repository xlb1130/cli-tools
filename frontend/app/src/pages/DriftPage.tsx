import { useEffect, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { useDriftReport, useSources } from "../lib/api";
import { formatDate } from "../lib/format";

export function DriftPage() {
  const sourcesQuery = useSources();
  const [selectedSource, setSelectedSource] = useState<string>("");
  const driftQuery = useDriftReport(selectedSource || undefined);

  useEffect(() => {
    if (!selectedSource && sourcesQuery.data?.length) {
      setSelectedSource(sourcesQuery.data[0].name);
    }
  }, [selectedSource, sourcesQuery.data]);

  if (sourcesQuery.isLoading || driftQuery.isLoading) {
    return <LoadingState label="加载 drift report" />;
  }

  if (sourcesQuery.isError) {
    return <ErrorState title="Drift 页面加载失败" error={sourcesQuery.error} />;
  }

  if (driftQuery.isError) {
    return <ErrorState title="Drift 报告加载失败" error={driftQuery.error} />;
  }

  const report = driftQuery.data!;
  const sourceState = report.source_drift_state;
  const driftSummary = report.drift_summary ?? {};
  const governanceSources = report.drift_governance?.sources ? Object.values(report.drift_governance.sources) : [];
  const governanceMounts = report.drift_governance?.mounts ? Object.values(report.drift_governance.mounts) : [];

  return (
    <div className="page-stack">
      <section className="stats-grid">
        <StatCard label="Severity" value={String(sourceState?.severity || driftSummary.severity || "clean")} />
        <StatCard label="Affected Mounts" value={String(sourceState?.affected_mount_count ?? 0)} />
        <StatCard label="Blocked Mounts" value={String(sourceState?.blocked_mount_count ?? 0)} />
        <StatCard label="Accepted Mounts" value={String(sourceState?.accepted_mount_count ?? 0)} />
      </section>

      <div className="content-grid two-col">
        <Panel
          title="Current Source State"
          subtitle="source 粒度的 drift 治理状态"
          actions={
            <label className="field-wrap">
              <span className="field-label">Source</span>
              <select className="field" value={selectedSource} onChange={(event) => setSelectedSource(event.target.value)}>
                {sourcesQuery.data?.map((source) => (
                  <option key={source.name} value={source.name}>
                    {source.name}
                  </option>
                ))}
              </select>
            </label>
          }
        >
          <div className="stack">
            <dl className="detail-grid">
              <div>
                <dt>Status</dt>
                <dd>{sourceState?.status || "-"}</dd>
              </div>
              <div>
                <dt>Generated At</dt>
                <dd>{formatDate(report.generated_at)}</dd>
              </div>
              <div>
                <dt>Report Path</dt>
                <dd>{report.report_path || "-"}</dd>
              </div>
              <div>
                <dt>Capability Snapshot</dt>
                <dd>{report.capability_snapshot_path || "-"}</dd>
              </div>
            </dl>
            <div className="pill-row">
              {(sourceState?.affected_mount_ids || []).map((mountId) => (
                <span key={mountId} className="pill pill-on">
                  {mountId}
                </span>
              ))}
            </div>
            <JsonViewer data={sourceState} />
          </div>
        </Panel>

        <Panel title="Report Summary" subtitle="sync report 的摘要与 discovery errors">
          <div className="stack">
            <JsonViewer data={driftSummary} />
            <div>
              <p className="eyebrow">Discovery Errors</p>
              <JsonViewer data={report.discovery_errors || {}} />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Changed Items" subtitle="每个 source item 的 drift 变化和治理结果">
        <div className="table-list">
          {report.items.map((item, index) => {
            const state = item.governance_state;
            return (
              <article key={`${item.source}:${index}`} className="table-item">
                <div className="table-item-main">
                  <div className="table-item-title">
                    <strong>{item.source}</strong>
                    <span className={driftBadgeClass(String(state?.status || item.drift?.severity || "neutral"))}>
                      {String(state?.status || item.drift?.severity || "clean")}
                    </span>
                  </div>
                  <p>{String(item.provider_type || "-")}</p>
                  <p className="muted">{(item.drift?.changes || []).length} change(s)</p>
                </div>
                <div className="table-item-meta">
                  <div>
                    <span className="eyebrow">Blocked</span>
                    <p>{state?.blocked ? "yes" : "no"}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Action</span>
                    <p>{state?.action || "-"}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Reasons</span>
                    <p>{(state?.reasons || []).join(", ") || "-"}</p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </Panel>

      <div className="content-grid two-col">
        <Panel title="Source Governance Index" subtitle="drift_governance.sources">
          <JsonViewer data={governanceSources} />
        </Panel>
        <Panel title="Mount Governance Index" subtitle="drift_governance.mounts">
          <JsonViewer data={governanceMounts} />
        </Panel>
      </div>
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

function driftBadgeClass(status: string) {
  if (status === "accepted" || status === "clean") {
    return "badge badge-safe";
  }
  if (status === "warning" || status === "additive" || status === "compatible") {
    return "badge badge-warn";
  }
  if (status === "frozen" || status === "review_required" || status === "breaking") {
    return "badge badge-danger";
  }
  return "badge badge-neutral";
}
