import { ChangeEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useCatalog, useSources } from "../lib/api";
import { formatList } from "../lib/format";

export function CatalogPage() {
  const catalogQuery = useCatalog();
  const sourcesQuery = useSources();
  const [filters, setFilters] = useState({
    q: "",
    risk: "",
    source: "",
    surface: "",
  });
  const catalog = catalogQuery.data;
  const sourceOptions = sourcesQuery.data ?? [];
  const mounts = useMemo(
    () =>
      (catalog?.mounts ?? []).filter((mount) => {
        const q = filters.q.trim().toLowerCase();
        if (q) {
          const values = [mount.mount_id, mount.stable_name, mount.summary, mount.source, mount.provider_type, mount.command_path.join(" ")]
            .map((item) => item.toLowerCase());
          if (!values.some((item) => item.includes(q))) {
            return false;
          }
        }
        if (filters.risk && mount.risk !== filters.risk) {
          return false;
        }
        if (filters.source && mount.source !== filters.source) {
          return false;
        }
        if (filters.surface && !mount.supported_surfaces.includes(filters.surface)) {
          return false;
        }
        return true;
      }),
    [catalog?.mounts, filters],
  );

  if (catalogQuery.isLoading || sourcesQuery.isLoading) {
    return <LoadingState label="加载 catalog" />;
  }

  if (catalogQuery.isError) {
    return <ErrorState title="Catalog 加载失败" error={catalogQuery.error} />;
  }

  const readyCatalog = catalog!;

  return (
    <div className="page-stack">
      <section className="hero">
        <div>
          <PageTitle
            icon="catalog"
            eyebrow="Catalog"
            title="Capability cards 而不是原始 JSON"
            description="这里按 capability card 方式展示 catalog 里的 mount，支持过滤、搜索、按 risk/source/surface 聚焦，保留足够的 machine contract 信息但不把人淹没在 JSON 里。"
          />
        </div>
      </section>

      <Panel title="Catalog Filters" subtitle="筛 capability，而不是滚整份 export JSON">
        <div className="filters">
          <input
            className="field"
            placeholder="搜索 stable name / summary / mount / provider"
            value={filters.q}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setFilters((current) => ({ ...current, q: event.target.value }))}
          />
          <select className="field" value={filters.risk} onChange={(event) => setFilters((current) => ({ ...current, risk: event.target.value }))}>
            <option value="">All risks</option>
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="destructive">destructive</option>
          </select>
          <select className="field" value={filters.source} onChange={(event) => setFilters((current) => ({ ...current, source: event.target.value }))}>
            <option value="">All sources</option>
            {sourceOptions.map((source) => (
              <option key={source.name} value={source.name}>
                {source.name}
              </option>
            ))}
          </select>
          <select className="field" value={filters.surface} onChange={(event) => setFilters((current) => ({ ...current, surface: event.target.value }))}>
            <option value="">All surfaces</option>
            <option value="cli">cli</option>
            <option value="invoke">invoke</option>
            <option value="mcp">mcp</option>
            <option value="http">http</option>
          </select>
        </div>
      </Panel>

      <Panel title="Capability Cards" subtitle="面向人类浏览，但保留 machine contract 关键字段">
        {mounts.length ? (
          <div className="mount-grid">
            {mounts.map((mount) => (
              <article key={mount.mount_id} className="mount-card catalog-card">
                <div className="mount-card-top">
                  <RiskBadge risk={mount.risk} />
                  <span className="mount-provider">{mount.provider_type}</span>
                </div>
                <h3>{mount.summary}</h3>
                <p className="mount-path">{formatList(mount.command_path)}</p>
                <p className="mount-stable">{mount.stable_name}</p>
                <dl className="detail-list">
                  <div>
                    <dt>Mount</dt>
                    <dd>{mount.mount_id}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{mount.source}</dd>
                  </div>
                  <div>
                    <dt>Aliases</dt>
                    <dd>{mount.aliases.length ? mount.aliases.map((alias) => alias.join(" ")).join(" / ") : "-"}</dd>
                  </div>
                </dl>
                <SurfacePills surfaces={mount.supported_surfaces} />
                <div className="catalog-card-actions">
                  <Link to={`/mounts/${mount.mount_id}`} className="secondary-button">
                    Open Detail
                  </Link>
                  <CopyButton value={`cts ${mount.command_path.join(" ")}`} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="没有匹配的 capability" body="换一个搜索词、risk、source 或 surface 试试。" />
        )}
      </Panel>

      {readyCatalog.conflicts.length ? (
        <Panel title="Catalog Conflicts" subtitle="仍保留 export 里的冲突摘要，便于排障">
          <pre className="json-viewer">{JSON.stringify(readyCatalog.conflicts, null, 2)}</pre>
        </Panel>
      ) : null}
    </div>
  );
}
