import { ChangeEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useMounts, useSources } from "../lib/api";
import { formatList } from "../lib/format";

export function MountsPage() {
  const [params, setParams] = useSearchParams();
  const filters = {
    q: params.get("q") || "",
    risk: params.get("risk") || "",
    source: params.get("source") || "",
    surface: params.get("surface") || "",
  };

  const mountsQuery = useMounts(filters);
  const sourcesQuery = useSources();

  if (mountsQuery.isLoading || sourcesQuery.isLoading) {
    return <LoadingState label="加载 mounts" />;
  }

  if (mountsQuery.isError) {
    return <ErrorState title="Mounts 加载失败" error={mountsQuery.error} />;
  }

  const mounts = mountsQuery.data ?? [];
  const sources = sourcesQuery.data ?? [];

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setParams(next);
  };

  return (
    <div className="page-stack">
      <Panel title="Mounts" subtitle="人类命令路径与机器合同在这里汇合">
        <div className="filters">
          <input
            className="field"
            placeholder="搜索 mount id / stable name / command path"
            value={filters.q}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setFilter("q", event.target.value)}
          />
          <select className="field" value={filters.risk} onChange={(event) => setFilter("risk", event.target.value)}>
            <option value="">All risks</option>
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="destructive">destructive</option>
          </select>
          <select className="field" value={filters.source} onChange={(event) => setFilter("source", event.target.value)}>
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source.name} value={source.name}>
                {source.name}
              </option>
            ))}
          </select>
          <select className="field" value={filters.surface} onChange={(event) => setFilter("surface", event.target.value)}>
            <option value="">All surfaces</option>
            <option value="cli">cli</option>
            <option value="invoke">invoke</option>
            <option value="mcp">mcp</option>
            <option value="http">http</option>
          </select>
        </div>

        <div className="table-list">
          {mounts.map((mount) => (
            <article key={mount.mount_id} className="table-item">
              <div className="table-item-main">
                <div className="table-item-title">
                  <Link to={`/mounts/${mount.mount_id}`}>{mount.mount_id}</Link>
                  <RiskBadge risk={mount.risk} />
                </div>
                <p>{mount.summary}</p>
                <p className="muted">{mount.stable_name}</p>
              </div>
              <div className="table-item-meta">
                <div>
                  <span className="eyebrow">Command</span>
                  <p>{formatList(mount.command_path)}</p>
                </div>
                <div>
                  <span className="eyebrow">Source</span>
                  <p>
                    {mount.source} · {mount.provider_type}
                  </p>
                </div>
                <SurfacePills surfaces={mount.supported_surfaces} />
                <CopyButton value={`cts ${mount.command_path.join(" ")}`} />
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
