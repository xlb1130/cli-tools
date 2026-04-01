import { Link, useSearchParams } from "react-router-dom";

import { useSources } from "../lib/api";
import { ErrorBlock, LoadingBlock, Panel, StatusPill, SurfaceStack } from "../components/ui";

export function SourcesPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q")?.toLowerCase().trim() || "";
  const health = params.get("health") || "";
  const sourcesQuery = useSources();

  if (sourcesQuery.isLoading) return <LoadingBlock label="加载 sources" />;
  if (sourcesQuery.isError) return <ErrorBlock title="Sources 读取失败" error={sourcesQuery.error} />;

  const sources = (sourcesQuery.data ?? []).filter((item) => {
    if (query) {
      const haystack = [item.name, item.type, item.discovery_mode, item.origin_file || ""].join(" ").toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (health === "healthy" && !item.health?.ok) return false;
    if (health === "issue" && item.health?.ok) return false;
    return true;
  });

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <div className="page">
      <Panel
        title="Sources"
        eyebrow="Inventory"
        aside={
          <div className="toolbar">
            <input className="field-input" value={query} onChange={(event) => setFilter("q", event.target.value)} placeholder="搜索 source / provider / origin" />
            <select className="field-input" value={health} onChange={(event) => setFilter("health", event.target.value)}>
              <option value="">All health</option>
              <option value="healthy">Healthy</option>
              <option value="issue">Needs check</option>
            </select>
          </div>
        }
      >
        <div className="inventory-list">
          {sources.map((source) => (
            <Link key={source.name} to={`/sources/${source.name}`} className="inventory-row">
              <div className="inventory-main">
                <div className="inventory-title">
                  <strong>{source.name}</strong>
                  <StatusPill tone={source.health?.ok ? "good" : "warn"}>{source.health?.ok ? "healthy" : "check"}</StatusPill>
                </div>
                <p>
                  {source.type} · {source.discovery_mode} · {source.operation_count} ops
                </p>
              </div>
              <div className="inventory-meta">
                <SurfaceStack items={source.expose_to_surfaces} />
                <small>{source.origin_file || "No origin file"}</small>
              </div>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
