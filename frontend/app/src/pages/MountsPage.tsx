import { ChangeEvent, FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useAddMount, useMounts, useRemoveMount, useSources } from "../lib/api";
import { formatList } from "../lib/format";

const DEFAULT_SURFACES = ["cli", "invoke", "http"];
const SURFACE_OPTIONS = ["cli", "invoke", "http", "mcp", "jsonrpc", "ui"];

export function MountsPage() {
  const [params, setParams] = useSearchParams();
  const addMountMutation = useAddMount();
  const removeMountMutation = useRemoveMount();
  const [formState, setFormState] = useState({
    sourceName: "",
    operationId: "",
    mountId: "",
    commandPath: "",
    stableName: "",
    summary: "",
    description: "",
    risk: "read",
    surfaces: DEFAULT_SURFACES,
  });
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
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
  const handleAddMount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setErrorMessage(null);
    try {
      const result = await addMountMutation.mutateAsync({
        source_name: formState.sourceName,
        operation_id: formState.operationId,
        mount_id: formState.mountId || undefined,
        command_path: formState.commandPath || undefined,
        stable_name: formState.stableName || undefined,
        summary: formState.summary || undefined,
        description: formState.description || undefined,
        risk: formState.risk || undefined,
        surfaces: formState.surfaces,
      });
      setMessage(`Mount ${result.mount_id} 已创建。`);
      setFormState((current) => ({
        ...current,
        operationId: "",
        mountId: "",
        commandPath: "",
        stableName: "",
        summary: "",
        description: "",
      }));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Mount 创建失败");
    }
  };

  const handleRemoveMount = async (mountId: string) => {
    setMessage(null);
    setErrorMessage(null);
    try {
      await removeMountMutation.mutateAsync(mountId);
      setMessage(`Mount ${mountId} 已删除。`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Mount 删除失败");
    }
  };

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setParams(next);
  };

  const toggleSurface = (surface: string) => {
    setFormState((current) => ({
      ...current,
      surfaces: current.surfaces.includes(surface) ? current.surfaces.filter((item) => item !== surface) : [...current.surfaces, surface],
    }));
  };

  return (
    <div className="page-stack">
      <section className="hero">
        <div>
          <PageTitle
            icon="mounts"
            eyebrow="Mounts"
            title="人类命令路径与机器合同在这里汇合"
            description="这里管理 mount inventory 和创建入口，把发现出来的 operation 收口成稳定产品命令。"
          />
          {message ? <div className="inline-note">{message}</div> : null}
          {errorMessage ? <div className="inline-error">{errorMessage}</div> : null}
        </div>
      </section>

      <Panel title="Mount Inventory" subtitle="按 source / risk / surface 浏览和管理现有 mount">
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
                <button type="button" className="secondary-button" onClick={() => handleRemoveMount(mount.mount_id)} disabled={removeMountMutation.isPending}>
                  Remove
                </button>
              </div>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Create Mount" subtitle="最小 mount add 界面，适合把已发现 operation 变成稳定产品入口">
        <form className="form-grid" onSubmit={handleAddMount}>
          <label>
            <span className="field-label">Source</span>
            <select className="field" value={formState.sourceName} onChange={(event) => setFormState((current) => ({ ...current, sourceName: event.target.value }))}>
              <option value="">Select source</option>
              {sources.map((source) => (
                <option key={source.name} value={source.name}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Operation ID</span>
            <input className="field" value={formState.operationId} onChange={(event) => setFormState((current) => ({ ...current, operationId: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Mount ID</span>
            <input className="field" value={formState.mountId} onChange={(event) => setFormState((current) => ({ ...current, mountId: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Command Path</span>
            <input className="field" value={formState.commandPath} onChange={(event) => setFormState((current) => ({ ...current, commandPath: event.target.value }))} placeholder="ops jira issue get" />
          </label>
          <label>
            <span className="field-label">Stable Name</span>
            <input className="field" value={formState.stableName} onChange={(event) => setFormState((current) => ({ ...current, stableName: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Risk</span>
            <select className="field" value={formState.risk} onChange={(event) => setFormState((current) => ({ ...current, risk: event.target.value }))}>
              <option value="read">read</option>
              <option value="write">write</option>
              <option value="destructive">destructive</option>
            </select>
          </label>
          <label>
            <span className="field-label">Summary</span>
            <input className="field" value={formState.summary} onChange={(event) => setFormState((current) => ({ ...current, summary: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Description</span>
            <input className="field" value={formState.description} onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))} />
          </label>
          <div className="form-full">
            <span className="field-label">Surfaces</span>
            <div className="option-grid">
              {SURFACE_OPTIONS.map((surface) => (
                <label key={surface} className={`option-chip ${formState.surfaces.includes(surface) ? "option-chip-active" : ""}`}>
                  <input type="checkbox" checked={formState.surfaces.includes(surface)} onChange={() => toggleSurface(surface)} />
                  <span>{surface}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="inline-actions">
            <button type="submit" className="primary-button" disabled={addMountMutation.isPending}>
              {addMountMutation.isPending ? "Creating..." : "Create Mount"}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
