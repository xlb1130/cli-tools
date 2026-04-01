import { useParams } from "react-router-dom";

import { useMount } from "../lib/api";
import { ErrorBlock, LoadingBlock, MetricLine, Panel, StatusPill, SurfaceStack } from "../components/ui";
import { joinPath } from "../lib/format";

export function MountDetailPage() {
  const { mountId = "" } = useParams();
  const mountQuery = useMount(mountId);

  if (mountQuery.isLoading) return <LoadingBlock label="加载 mount 详情" />;
  if (mountQuery.isError) return <ErrorBlock title="Mount 详情读取失败" error={mountQuery.error} />;

  const mount = mountQuery.data!;

  return (
    <div className="page">
      <section className="detail-strip">
        <div>
          <p className="eyebrow">Mount Detail</p>
          <h1>{mount.mount_id}</h1>
          <p className="hero-copy">{mount.summary || mount.description || "这一条能力入口负责把底层 provider 能力映射成稳定命令。"} </p>
        </div>
        <div className="detail-strip-meta">
          <StatusPill tone={mount.risk === "read" ? "neutral" : mount.risk === "write" ? "warn" : "bad"}>{mount.risk}</StatusPill>
          <SurfaceStack items={mount.supported_surfaces} />
        </div>
      </section>

      <section className="dashboard-grid">
        <Panel title="Command Mapping" eyebrow="Route">
          <div className="metric-list">
            <MetricLine label="Stable Name" value={mount.stable_name} />
            <MetricLine label="Command Path" value={joinPath(mount.command_path)} />
            <MetricLine label="Source" value={mount.source} />
            <MetricLine label="Provider" value={mount.provider_type} />
          </div>
        </Panel>

        <Panel title="Execution Contract" eyebrow="Operation">
          <div className="metric-list">
            <MetricLine label="Operation ID" value={mount.operation_id} />
            <MetricLine label="Generated" value={mount.generated ? "yes" : "no"} />
            <MetricLine label="Origin File" value={mount.origin_file || "-"} />
            <MetricLine label="Source File" value={mount.source_origin_file || "-"} />
          </div>
        </Panel>
      </section>

      <Panel title="Aliases" eyebrow="Routing">
        <div className="token-grid">
          {mount.aliases.length ? (
            mount.aliases.map((alias) => (
              <span key={alias.join("/")} className="token">
                {alias.join(" / ")}
              </span>
            ))
          ) : (
            <span className="muted">No aliases</span>
          )}
        </div>
      </Panel>
    </div>
  );
}
