import { useParams } from "react-router-dom";

import { useSource } from "../lib/api";
import { ErrorBlock, LoadingBlock, MetricLine, Panel, StatusPill, SurfaceStack } from "../components/ui";

export function SourceDetailPage() {
  const { sourceName = "" } = useParams();
  const sourceQuery = useSource(sourceName);

  if (sourceQuery.isLoading) return <LoadingBlock label="加载 source 详情" />;
  if (sourceQuery.isError) return <ErrorBlock title="Source 详情读取失败" error={sourceQuery.error} />;

  const source = sourceQuery.data!;

  return (
    <div className="page">
      <section className="detail-strip">
        <div>
          <p className="eyebrow">Source Detail</p>
          <h1>{source.name}</h1>
          <p className="hero-copy">这一页把 source 的 provider、auth、health 和编译结果收在同一条阅读路径上。</p>
        </div>
        <div className="detail-strip-meta">
          <StatusPill tone={source.health?.ok ? "good" : "warn"}>{source.health?.ok ? "healthy" : "needs check"}</StatusPill>
          <SurfaceStack items={source.expose_to_surfaces} />
        </div>
      </section>

      <section className="dashboard-grid">
        <Panel title="Identity" eyebrow="Profile">
          <div className="metric-list">
            <MetricLine label="Provider" value={source.type} />
            <MetricLine label="Discovery" value={source.discovery_mode} />
            <MetricLine label="Compiled Ops" value={source.compiled_operation_count} />
            <MetricLine label="Auth Ref" value={source.auth_ref || "none"} />
          </div>
        </Panel>

        <Panel title="Runtime State" eyebrow="Signals">
          <div className="metric-list">
            <MetricLine label="Health" value={source.health?.ok ? "ok" : "needs check"} />
            <MetricLine label="Auth State" value={source.auth?.state || "unconfigured"} />
            <MetricLine label="Origin File" value={source.origin_file || "-"} />
            <MetricLine label="Profile Scope" value={source.profile_scope.join(", ") || "-"} />
          </div>
        </Panel>
      </section>

      <Panel title="Compiled Operations" eyebrow="Output">
        <div className="token-grid">
          {source.operation_ids.map((operationId) => (
            <span key={operationId} className="token">
              {operationId}
            </span>
          ))}
        </div>
      </Panel>
    </div>
  );
}
