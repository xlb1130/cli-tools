import { ChangeEvent, FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { SurfacePills } from "../components/SurfacePills";
import { useAddSource, useSources } from "../lib/api";
import { formatList } from "../lib/format";

const DEFAULT_SURFACES = ["cli", "invoke", "http"];
const SURFACE_OPTIONS = ["cli", "invoke", "http", "mcp", "jsonrpc", "ui"];
const PROVIDER_TYPE_OPTIONS = ["cli", "shell", "http", "openapi", "graphql", "mcp"];
const DISCOVERY_MODE_OPTIONS = [
  { value: "", label: "Default" },
  { value: "manual", label: "manual" },
  { value: "manifest", label: "manifest" },
  { value: "live", label: "live" },
  { value: "cache_only", label: "cache_only" },
];

export function SourcesPage() {
  const [params, setParams] = useSearchParams();
  const addSourceMutation = useAddSource();
  const [formState, setFormState] = useState({
    providerType: "cli",
    sourceName: "",
    description: "",
    executable: "",
    baseUrl: "",
    manifest: "",
    discoverMode: "",
    authRef: "",
    surfaces: DEFAULT_SURFACES,
  });
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const filters = {
    q: params.get("q") || "",
    type: params.get("type") || "",
    auth: params.get("auth") || "",
    health: params.get("health") || "",
  };
  const sourcesQuery = useSources();

  if (sourcesQuery.isLoading) {
    return <LoadingState label="加载 sources" />;
  }

  if (sourcesQuery.isError) {
    return <ErrorState title="Sources 加载失败" error={sourcesQuery.error} />;
  }

  const sources = (sourcesQuery.data ?? []).filter((source) => {
    const q = filters.q.trim().toLowerCase();
    if (q) {
      const haystacks = [source.name, source.type, source.discovery_mode, source.origin_file || ""].map((item) => item.toLowerCase());
      if (!haystacks.some((item) => item.includes(q))) {
        return false;
      }
    }
    if (filters.type && source.type !== filters.type) {
      return false;
    }
    if (filters.auth) {
      const authState = source.auth?.state || (source.auth_ref ? "configured" : "unconfigured");
      if (authState !== filters.auth) {
        return false;
      }
    }
    if (filters.health === "healthy" && !source.health?.ok) {
      return false;
    }
    if (filters.health === "needs_check" && source.health?.ok) {
      return false;
    }
    return true;
  });

  const types = Array.from(new Set((sourcesQuery.data ?? []).map((source) => source.type))).sort();
  const authStates = Array.from(new Set((sourcesQuery.data ?? []).map((source) => source.auth?.state).filter(Boolean) as string[])).sort();
  const providerTypeOptions = Array.from(new Set([...PROVIDER_TYPE_OPTIONS, ...types])).sort();

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setParams(next);
  };

  const handleAddSource = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setErrorMessage(null);
    try {
      const result = await addSourceMutation.mutateAsync({
        provider_type: formState.providerType,
        source_name: formState.sourceName,
        description: formState.description || undefined,
        executable: formState.executable || undefined,
        base_url: formState.baseUrl || undefined,
        manifest: formState.manifest || undefined,
        discover_mode: formState.discoverMode || undefined,
        auth_ref: formState.authRef || undefined,
        surfaces: formState.surfaces,
      });
      setMessage(`Source ${result.source_name} 已创建。`);
      setFormState({
        providerType: formState.providerType,
        sourceName: "",
        description: "",
        executable: "",
        baseUrl: "",
        manifest: "",
        discoverMode: "",
        authRef: "",
        surfaces: DEFAULT_SURFACES,
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Source 创建失败");
    }
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
            icon="sources"
            eyebrow="Sources"
            title="Source registry 与运行态入口"
            description="这里先看 source 摘要，再点进去做 `show` / `test` / `test --discover`。页面关注的是 provider、auth、drift、discovery 是否真的接得起来。"
          />
          {message ? <div className="inline-note">{message}</div> : null}
          {errorMessage ? <div className="inline-error">{errorMessage}</div> : null}
        </div>
        <div className="hero-actions">
          <div className="stack compact-stack">
            <span className="sidebar-chip">Sources {sources.length}</span>
            <span className="sidebar-chip">Healthy {(sourcesQuery.data ?? []).filter((item) => item.health?.ok).length}</span>
            <span className="sidebar-chip">Auth Bound {(sourcesQuery.data ?? []).filter((item) => item.auth_ref).length}</span>
          </div>
        </div>
      </section>

      <Panel title="Create Source" subtitle="最小 source 管理入口，先覆盖常用 CLI / HTTP 类 provider 字段">
        <form className="form-grid" onSubmit={handleAddSource}>
          <label>
            <span className="field-label">Provider Type</span>
            <select className="field" value={formState.providerType} onChange={(event) => setFormState((current) => ({ ...current, providerType: event.target.value }))}>
              {providerTypeOptions.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Source Name</span>
            <input className="field" value={formState.sourceName} onChange={(event) => setFormState((current) => ({ ...current, sourceName: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Description</span>
            <input className="field" value={formState.description} onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Executable</span>
            <input className="field" value={formState.executable} onChange={(event) => setFormState((current) => ({ ...current, executable: event.target.value }))} placeholder="python3 / kubectl" />
          </label>
          <label>
            <span className="field-label">Base URL</span>
            <input className="field" value={formState.baseUrl} onChange={(event) => setFormState((current) => ({ ...current, baseUrl: event.target.value }))} placeholder="https://api.example.com" />
          </label>
          <label>
            <span className="field-label">Manifest</span>
            <input className="field" value={formState.manifest} onChange={(event) => setFormState((current) => ({ ...current, manifest: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Discover Mode</span>
            <select className="field" value={formState.discoverMode} onChange={(event) => setFormState((current) => ({ ...current, discoverMode: event.target.value }))}>
              {DISCOVERY_MODE_OPTIONS.map((option) => (
                <option key={option.value || "default"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Auth Ref</span>
            <input className="field" value={formState.authRef} onChange={(event) => setFormState((current) => ({ ...current, authRef: event.target.value }))} />
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
            <button type="submit" className="primary-button" disabled={addSourceMutation.isPending}>
              {addSourceMutation.isPending ? "Creating..." : "Create Source"}
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="Source Inventory" subtitle="筛选后进入 source 详情页，查看 show/test 结果">
        <div className="filters">
          <input
            className="field"
            placeholder="搜索 source 名称 / provider / discovery"
            value={filters.q}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setFilter("q", event.target.value)}
          />
          <select className="field" value={filters.type} onChange={(event) => setFilter("type", event.target.value)}>
            <option value="">All providers</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <select className="field" value={filters.auth} onChange={(event) => setFilter("auth", event.target.value)}>
            <option value="">All auth states</option>
            {authStates.map((state) => (
              <option key={state} value={state}>
                {state}
              </option>
            ))}
          </select>
          <select className="field" value={filters.health} onChange={(event) => setFilter("health", event.target.value)}>
            <option value="">All health</option>
            <option value="healthy">healthy</option>
            <option value="needs_check">needs check</option>
          </select>
        </div>

        {sources.length ? (
          <div className="card-list">
            {sources.map((source) => (
              <Link key={source.name} to={`/sources/${source.name}`} className="source-card source-card-button">
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
                    <dt>Auth</dt>
                    <dd>{source.auth_ref ? `${source.auth_ref} · ${source.auth?.state || "configured"}` : "none"}</dd>
                  </div>
                  <div>
                    <dt>Profiles</dt>
                    <dd>{formatList(source.profile_scope)}</dd>
                  </div>
                  <div>
                    <dt>Origin</dt>
                    <dd>{source.origin_file || "-"}</dd>
                  </div>
                </dl>
                <SurfacePills surfaces={source.expose_to_surfaces} />
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="没有匹配的 source" body="当前筛选没有结果，可以放宽 provider、auth 或 health 条件。" />
        )}
      </Panel>
    </div>
  );
}
