import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { SurfacePills } from "../components/SurfacePills";
import { useSources } from "../lib/api";
import { JsonViewer } from "../components/JsonViewer";

export function SourcesPage() {
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const sourcesQuery = useSources();

  if (sourcesQuery.isLoading) {
    return <LoadingState label="加载 sources" />;
  }

  if (sourcesQuery.isError) {
    return <ErrorState title="Sources 加载失败" error={sourcesQuery.error} />;
  }

  const sources = sourcesQuery.data ?? [];
  const focused = sources.find((source) => source.name === focus);

  return (
    <div className="page-stack">
      <Panel title="Sources" subtitle="南向 provider 的实际注册快照">
        <div className="card-list">
          {sources.map((source) => (
            <article key={source.name} className={`source-card ${focus === source.name ? "focused" : ""}`}>
              <div className="source-card-top">
                <div>
                  <h3>{source.name}</h3>
                  <p>
                    {source.type} · {source.discovery_mode}
                  </p>
                </div>
                <span className={source.health?.ok ? "badge badge-safe" : "badge badge-danger"}>
                  {source.health?.ok ? "healthy" : "needs check"}
                </span>
              </div>
              <dl className="detail-list">
                <div>
                  <dt>Operations</dt>
                  <dd>{source.operation_count}</dd>
                </div>
                <div>
                  <dt>Origin</dt>
                  <dd>{source.origin_file || "-"}</dd>
                </div>
              </dl>
              <SurfacePills surfaces={source.expose_to_surfaces} />
            </article>
          ))}
        </div>
      </Panel>

      {focused ? (
        <Panel title={`Focused Source: ${focused.name}`} subtitle="来自 URL query 的快速聚焦视图">
          <JsonViewer data={focused} />
        </Panel>
      ) : null}
    </div>
  );
}
