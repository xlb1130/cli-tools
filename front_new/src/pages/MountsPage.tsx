import { Link, useSearchParams } from "react-router-dom";

import { useMounts } from "../lib/api";
import { ErrorBlock, LoadingBlock, Panel, StatusPill, SurfaceStack } from "../components/ui";

export function MountsPage() {
  const [params, setParams] = useSearchParams();
  const filters = {
    q: params.get("q") || "",
    risk: params.get("risk") || "",
    source: params.get("source") || "",
    surface: params.get("surface") || "",
  };
  const mountsQuery = useMounts(filters);

  if (mountsQuery.isLoading) return <LoadingBlock label="加载 mounts" />;
  if (mountsQuery.isError) return <ErrorBlock title="Mounts 读取失败" error={mountsQuery.error} />;

  const mounts = mountsQuery.data ?? [];
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <div className="page">
      <Panel
        title="Mounts"
        eyebrow="Command Surface"
        aside={
          <div className="toolbar toolbar-wide">
            <input className="field-input" value={filters.q} onChange={(event) => setFilter("q", event.target.value)} placeholder="搜索 mount id / stable name / path" />
            <select className="field-input" value={filters.risk} onChange={(event) => setFilter("risk", event.target.value)}>
              <option value="">All risks</option>
              <option value="read">read</option>
              <option value="write">write</option>
              <option value="destructive">destructive</option>
            </select>
          </div>
        }
      >
        <div className="inventory-list">
          {mounts.map((mount) => (
            <Link key={mount.mount_id} to={`/mounts/${mount.mount_id}`} className="inventory-row">
              <div className="inventory-main">
                <div className="inventory-title">
                  <strong>{mount.mount_id}</strong>
                  <StatusPill tone={mount.risk === "read" ? "neutral" : mount.risk === "write" ? "warn" : "bad"}>{mount.risk}</StatusPill>
                </div>
                <p>
                  {mount.summary} · {mount.source} · {mount.provider_type}
                </p>
              </div>
              <div className="inventory-meta">
                <SurfaceStack items={mount.supported_surfaces} />
                <small>{mount.command_path.join(" ")}</small>
              </div>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
