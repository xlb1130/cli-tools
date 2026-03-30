import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { SurfacePills } from "../components/SurfacePills";
import { TablePagination } from "../components/TablePagination";
import { useRemoveSource, useSource, useTestSource } from "../lib/api";
import { formatDate, formatList } from "../lib/format";

export function SourceDetailPage() {
  const { sourceName = "" } = useParams();
  const navigate = useNavigate();
  const sourceQuery = useSource(sourceName);
  const testMutation = useTestSource();
  const removeSourceMutation = useRemoveSource();
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  if (sourceQuery.isLoading) {
    return <LoadingState label="加载 source 详情" />;
  }

  if (sourceQuery.isError) {
    return <ErrorState title="Source 详情加载失败" error={sourceQuery.error} />;
  }

  const source = sourceQuery.data;
  if (!source) {
    return <ErrorState title="Source 不存在" error={new Error(sourceName)} />;
  }

  const runTest = async (discover: boolean) => {
    setActionMessage(null);
    setActionError(null);
    try {
      const result = await testMutation.mutateAsync({ sourceName: source.name, discover });
      setActionMessage(
        discover
          ? `Source test + discover 完成，当前 operation_count ${result.discovery?.operation_count ?? source.operation_count}。`
          : `Source test 完成，当前健康状态 ${result.ok ? "ok" : "failed"}。`,
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Source test 失败");
    }
  };

  const removeSource = async (force: boolean) => {
    setActionMessage(null);
    setActionError(null);
    try {
      await removeSourceMutation.mutateAsync({ sourceName: source.name, force });
      navigate("/sources");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Source 删除失败");
    }
  };

  return (
    <div className="page-stack">
      <section className="detail-hero">
        <div>
          <PageTitle
            icon="sources"
            eyebrow="Source Detail"
            title={source.name}
            description="这里把 source 管理入口收口到同一个交互页里，既能看编译后的 source 详情，也能直接跑健康检查和 discover。"
            compact
          />
          {actionMessage ? <div className="inline-note">{actionMessage}</div> : null}
          {actionError ? <div className="inline-error">{actionError}</div> : null}
        </div>
        <div className="detail-hero-side">
          <span className={source.health?.ok ? "badge badge-safe" : "badge badge-danger"}>
            {source.health?.ok ? "healthy" : "needs check"}
          </span>
          <div className="hero-summary-grid hero-summary-grid-single">
            <article className="hero-summary-card">
              <span>Provider</span>
              <strong>{source.type}</strong>
            </article>
            <article className="hero-summary-card">
              <span>Operations</span>
              <strong>{source.compiled_operation_count}</strong>
            </article>
          </div>
          <SurfacePills surfaces={source.expose_to_surfaces} />
          <Link to="/sources" className="secondary-button">
            Back to Sources
          </Link>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="Provider" value={source.type} />
        <StatCard label="Discovery" value={source.discovery_mode} />
        <StatCard label="Compiled Ops" value={String(source.compiled_operation_count)} />
        <StatCard label="Auth" value={source.auth?.auth_ref || "none"} />
      </section>

      <div className="content-grid two-col">
        <Panel title="Show Summary" subtitle="对应 `cts manage source show` 的主信息" kicker="Read Model">
          <dl className="detail-grid">
            <div>
              <dt>Name</dt>
              <dd>{source.name}</dd>
            </div>
            <div>
              <dt>Origin</dt>
              <dd>{source.origin_file || "-"}</dd>
            </div>
            <div>
              <dt>Profile Scope</dt>
              <dd>{formatList(source.profile_scope)}</dd>
            </div>
            <div>
              <dt>Auth Ref</dt>
              <dd>{source.auth_ref || "-"}</dd>
            </div>
            <div>
              <dt>Source State</dt>
              <dd>{source.auth?.state || "unconfigured"}</dd>
            </div>
            <div>
              <dt>Provider OK</dt>
              <dd>{source.health?.provider_type || source.type}</dd>
            </div>
          </dl>
        </Panel>

        <Panel
          title="Test Actions"
          subtitle="对应 `cts manage source test` 与 `cts manage source test --discover`"
          kicker="Write Actions"
          actions={
            <div className="explain-actions">
              <button type="button" className="secondary-button" onClick={() => runTest(false)} disabled={testMutation.isPending}>
                {testMutation.isPending ? "Testing..." : "Test"}
              </button>
              <button type="button" className="primary-button" onClick={() => runTest(true)} disabled={testMutation.isPending}>
                {testMutation.isPending ? "Running..." : "Test + Discover"}
              </button>
              <button type="button" className="secondary-button" onClick={() => removeSource(false)} disabled={removeSourceMutation.isPending}>
                Remove
              </button>
              <button type="button" className="secondary-button" onClick={() => removeSource(true)} disabled={removeSourceMutation.isPending}>
                Force Remove
              </button>
            </div>
          }
        >
          {testMutation.data ? (
            <div className="stack">
              <dl className="detail-grid">
                <div>
                  <dt>Test Result</dt>
                  <dd>{testMutation.data.ok ? "ok" : "failed"}</dd>
                </div>
                <div>
                  <dt>Operation Count</dt>
                  <dd>{String(testMutation.data.operation_count ?? 0)}</dd>
                </div>
                <div>
                  <dt>Discovery Report</dt>
                  <dd>{testMutation.data.discovery_report_path || "-"}</dd>
                </div>
                <div>
                  <dt>Capability Snapshot</dt>
                  <dd>{testMutation.data.capability_snapshot_path || "-"}</dd>
                </div>
              </dl>
              <JsonViewer data={testMutation.data} />
            </div>
          ) : (
            <div className="state">还没有执行 source health check。</div>
          )}
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Health / Auth / Drift" subtitle="source 编译后运行态" kicker="Control Signals">
          <div className="stack">
            <div>
              <p className="eyebrow">Health</p>
              <JsonViewer data={source.health || {}} />
            </div>
            <div>
              <p className="eyebrow">Auth</p>
              <JsonViewer data={source.auth || {}} />
            </div>
            <div>
              <p className="eyebrow">Drift</p>
              <JsonViewer data={source.drift_state || {}} />
            </div>
          </div>
        </Panel>

        <Panel title="Operations" subtitle="当前 source 编译出的 operation 列表" kicker="Compiled Surface">
          <div className="table-like">
            {source.operation_ids
              .slice((currentPage - 1) * pageSize, currentPage * pageSize)
              .map((operationId) => (
                <div key={operationId} className="row-card row-card-rich">
                  <div>
                    <strong>{operationId}</strong>
                    <p>{source.name}</p>
                  </div>
                  <span className="badge badge-neutral">operation</span>
                </div>
              ))}
          </div>
          <TablePagination
            currentPage={currentPage}
            pageSize={pageSize}
            totalItems={source.operation_ids.length}
            onPageChange={setCurrentPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setCurrentPage(1);
            }}
          />
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Source Payload" subtitle="完整 `manage source show` 结构" kicker="Raw View">
          <JsonViewer data={source} />
        </Panel>
        <Panel title="Discovery State" subtitle={`最后更新时间 ${formatDate(String(source.discovery_state?.updated_at || ""))}`} kicker="State Cache">
          <JsonViewer data={source.discovery_state || {}} />
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
