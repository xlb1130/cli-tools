import { ChangeEvent, FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { TablePagination } from "../components/TablePagination";
import { useAddMount, useMounts, useRemoveMount, useSources } from "../lib/api";
import { formatList } from "../lib/format";

const DEFAULT_SURFACES = ["cli", "invoke", "http"];
const SURFACE_OPTIONS = ["cli", "invoke", "http", "mcp", "jsonrpc", "ui"];

export function MountsPage() {
  const [params, setParams] = useSearchParams();
  const addMountMutation = useAddMount();
  const removeMountMutation = useRemoveMount();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
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
      setIsCreateModalOpen(false);
      setCurrentPage(1);
      setFormState((current) => ({
        ...current,
        sourceName: "",
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
    setCurrentPage(1);
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
        <div className="hero-actions">
          <button type="button" className="primary-button" onClick={() => setIsCreateModalOpen(true)}>
            Create Mount
          </button>
        </div>
      </section>

      <Panel
        title="Mount Inventory"
        subtitle="按 source / risk / surface 浏览和管理现有 mount"
        actions={
          <div className="filters-compact">
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
        }
      >
        {mounts.length ? (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Mount ID</th>
                  <th>Summary</th>
                  <th>Stable Name</th>
                  <th>Command Path</th>
                  <th>Source</th>
                  <th>Provider</th>
                  <th>Surfaces</th>
                  <th>Risk</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {mounts.slice((currentPage - 1) * pageSize, currentPage * pageSize).map((mount) => (
                  <tr key={mount.mount_id}>
                    <td>
                      <Link to={`/mounts/${mount.mount_id}`} className="data-table-link">
                        {mount.mount_id}
                      </Link>
                    </td>
                    <td>{mount.summary}</td>
                    <td>{mount.stable_name}</td>
                    <td>{formatList(mount.command_path)}</td>
                    <td>{mount.source}</td>
                    <td>{mount.provider_type}</td>
                    <td>
                      <SurfacePills surfaces={mount.supported_surfaces} />
                    </td>
                    <td>
                      <RiskBadge risk={mount.risk} />
                    </td>
                    <td>
                      <div className="data-table-actions">
                        <CopyButton value={`cts ${mount.command_path.join(" ")}`} />
                        <button
                          type="button"
                          className="data-table-action-btn"
                          onClick={() => handleRemoveMount(mount.mount_id)}
                          disabled={removeMountMutation.isPending}
                        >
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <TablePagination
              currentPage={currentPage}
              pageSize={pageSize}
              totalItems={mounts.length}
              onPageChange={setCurrentPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setCurrentPage(1);
              }}
            />
          </div>
        ) : (
          <div className="table-empty">
            <strong>还没有 mount</strong>
            <p>给已发现的 operation 创建稳定的命令入口。</p>
          </div>
        )}
      </Panel>

      {/* Create Mount Modal */}
      {isCreateModalOpen && (
        <div className="modal-overlay" onClick={() => setIsCreateModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>Create Mount</h2>
                <p>最小 mount add 界面，适合把已发现 operation 变成稳定产品入口</p>
              </div>
              <button className="modal-close" onClick={() => setIsCreateModalOpen(false)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
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
              </form>
            </div>
            <div className="modal-footer">
              <button type="button" className="secondary-button" onClick={() => setIsCreateModalOpen(false)}>
                Cancel
              </button>
              <button type="button" className="primary-button" onClick={() => document.querySelector('form')?.requestSubmit()} disabled={addMountMutation.isPending}>
                {addMountMutation.isPending ? "Creating..." : "Create Mount"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
