import { FormEvent, useEffect, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { TablePagination } from "../components/TablePagination";
import { useAuthLogin, useAuthLogout, useAuthProfile, useAuthProfiles, useAuthRefresh } from "../lib/api";
import { formatDate, formatList } from "../lib/format";

export function AuthPage() {
  const inventoryQuery = useAuthProfiles();
  const [selectedName, setSelectedName] = useState<string>("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [formState, setFormState] = useState({
    token: "",
    apiKey: "",
    username: "",
    password: "",
    expiresAt: "",
    refreshToken: "",
    headerName: "",
    location: "header",
    queryName: "",
    metadata: "",
  });
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const detailQuery = useAuthProfile(selectedName);
  const loginMutation = useAuthLogin();
  const refreshMutation = useAuthRefresh();
  const logoutMutation = useAuthLogout();

  useEffect(() => {
    if (!selectedName && inventoryQuery.data?.items?.length) {
      setSelectedName(inventoryQuery.data.items[0].name);
    }
  }, [inventoryQuery.data, selectedName]);

  if (inventoryQuery.isLoading) {
    return <LoadingState label="加载 auth profiles" />;
  }

  if (inventoryQuery.isError) {
    return <ErrorState title="Auth 页面加载失败" error={inventoryQuery.error} />;
  }

  const inventory = inventoryQuery.data!;
  const items = inventory.items;
  const activeProfile = detailQuery.data ?? items.find((item) => item.name === selectedName) ?? null;
  const isMutating = loginMutation.isPending || refreshMutation.isPending || logoutMutation.isPending;

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedName) {
      return;
    }
    setActionError(null);
    setActionMessage(null);
    try {
      let metadata: Record<string, unknown> | undefined;
      if (formState.metadata.trim()) {
        const parsed = JSON.parse(formState.metadata);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("metadata 必须是 JSON object");
        }
        metadata = parsed as Record<string, unknown>;
      }
      const result = await loginMutation.mutateAsync({
        name: selectedName,
        token: formState.token || undefined,
        api_key: formState.apiKey || undefined,
        username: formState.username || undefined,
        password: formState.password || undefined,
        expires_at: formState.expiresAt || undefined,
        refresh_token: formState.refreshToken || undefined,
        header_name: formState.headerName || undefined,
        in: formState.location || undefined,
        query_name: formState.queryName || undefined,
        metadata,
      });
      setActionMessage(`Login 完成，当前状态 ${result.profile.state}。`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Login 失败");
    }
  };

  const handleRefresh = async () => {
    if (!selectedName) {
      return;
    }
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await refreshMutation.mutateAsync(selectedName);
      setActionMessage(`Refresh 完成，当前状态 ${result.profile.state}。`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Refresh 失败");
    }
  };

  const handleLogout = async () => {
    if (!selectedName) {
      return;
    }
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await logoutMutation.mutateAsync(selectedName);
      setActionMessage(`Logout 完成，当前状态 ${result.profile.state}。`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Logout 失败");
    }
  };

  return (
    <div className="page-stack">
      <div className="content-grid two-col">
        <Panel title="Profiles" subtitle="当前已配置 auth profile 与状态">
          {actionMessage ? <div className="inline-note">{actionMessage}</div> : null}
          {actionError ? <div className="inline-error">{actionError}</div> : null}
          {items.length ? (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source Types</th>
                    <th>State</th>
                    <th>Reason</th>
                    <th>Sources</th>
                  </tr>
                </thead>
                <tbody>
                  {items.slice((currentPage - 1) * pageSize, currentPage * pageSize).map((item) => (
                    <tr key={item.name} className={selectedName === item.name ? "table-row-selected" : ""}>
                      <td>
                        <button
                          type="button"
                          className="data-table-link"
                          onClick={() => setSelectedName(item.name)}
                        >
                          {item.name}
                        </button>
                      </td>
                      <td>{formatList(item.source_types)}</td>
                      <td>
                        <span className={authBadgeClass(item.state)}>{item.state}</span>
                      </td>
                      <td>{item.reason || "-"}</td>
                      <td>{item.source_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <TablePagination
                currentPage={currentPage}
                pageSize={pageSize}
                totalItems={items.length}
                onPageChange={setCurrentPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setCurrentPage(1);
                }}
              />
            </div>
          ) : (
            <div className="table-empty">
              <strong>还没有 auth profile</strong>
              <p>配置 auth profile 以启用认证功能。</p>
            </div>
          )}
        </Panel>

        <Panel
          title={activeProfile ? `Profile Detail: ${activeProfile.name}` : "Profile Detail"}
          subtitle="解析后的 profile / session / credentials 视图"
          actions={
            <div className="explain-actions">
              <button type="button" className="secondary-button" onClick={handleRefresh} disabled={!selectedName || isMutating}>
                {refreshMutation.isPending ? "Refreshing..." : "Refresh"}
              </button>
              <button type="button" className="secondary-button" onClick={handleLogout} disabled={!selectedName || isMutating}>
                {logoutMutation.isPending ? "Logging out..." : "Logout"}
              </button>
            </div>
          }
        >
          {detailQuery.isLoading && selectedName ? (
            <LoadingState label="加载 profile 详情" compact />
          ) : detailQuery.isError ? (
            <ErrorState title="Profile 详情加载失败" error={detailQuery.error} compact />
          ) : activeProfile ? (
            <div className="stack">
              <dl className="detail-grid">
                <div>
                  <dt>State</dt>
                  <dd>{activeProfile.state}</dd>
                </div>
                <div>
                  <dt>Reason</dt>
                  <dd>{activeProfile.reason || "-"}</dd>
                </div>
                <div>
                  <dt>Expires At</dt>
                  <dd>{formatDate(String(activeProfile.status?.expires_at || ""))}</dd>
                </div>
                <div>
                  <dt>Refresh</dt>
                  <dd>{activeProfile.status?.refresh_supported ? "supported" : "not available"}</dd>
                </div>
              </dl>
              <div className="pill-row">
                {activeProfile.source_names.map((name) => (
                  <span key={name} className="pill pill-on">
                    {name}
                  </span>
                ))}
              </div>
              <div className="content-grid two-col">
                <div>
                  <p className="eyebrow">Profile Config</p>
                  <JsonViewer data={activeProfile.profile} />
                </div>
                <div>
                  <p className="eyebrow">Session Snapshot</p>
                  <JsonViewer data={activeProfile.session} />
                </div>
              </div>
              <div>
                <p className="eyebrow">Resolved Credentials</p>
                <JsonViewer data={activeProfile.resolved_credentials} />
              </div>
            </div>
          ) : (
            <div className="state">暂无 auth profile。</div>
          )}
        </Panel>
      </div>

      <Panel title="Login / Rotate Session" subtitle="直接调用 /api/auth/login，适合临时录入 token / api key / basic auth">
        <form className="form-grid" onSubmit={handleLogin}>
          <label>
            <span className="field-label">Profile</span>
            <select className="field" value={selectedName} onChange={(event) => setSelectedName(event.target.value)}>
              <option value="">Select profile</option>
              {items.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Token</span>
            <input className="field" value={formState.token} onChange={(event) => setFormState((current) => ({ ...current, token: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">API Key</span>
            <input className="field" value={formState.apiKey} onChange={(event) => setFormState((current) => ({ ...current, apiKey: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Username</span>
            <input className="field" value={formState.username} onChange={(event) => setFormState((current) => ({ ...current, username: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Password</span>
            <input className="field" type="password" value={formState.password} onChange={(event) => setFormState((current) => ({ ...current, password: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Expires At</span>
            <input className="field" value={formState.expiresAt} onChange={(event) => setFormState((current) => ({ ...current, expiresAt: event.target.value }))} placeholder="2099-01-01T00:00:00+00:00" />
          </label>
          <label>
            <span className="field-label">Refresh Token</span>
            <input className="field" value={formState.refreshToken} onChange={(event) => setFormState((current) => ({ ...current, refreshToken: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Header Name</span>
            <input className="field" value={formState.headerName} onChange={(event) => setFormState((current) => ({ ...current, headerName: event.target.value }))} placeholder="Authorization / X-API-Key" />
          </label>
          <label>
            <span className="field-label">Location</span>
            <select className="field" value={formState.location} onChange={(event) => setFormState((current) => ({ ...current, location: event.target.value }))}>
              <option value="header">header</option>
              <option value="query">query</option>
            </select>
          </label>
          <label>
            <span className="field-label">Query Name</span>
            <input className="field" value={formState.queryName} onChange={(event) => setFormState((current) => ({ ...current, queryName: event.target.value }))} />
          </label>
          <label className="form-full">
            <span className="field-label">Metadata JSON</span>
            <textarea
              className="json-input"
              value={formState.metadata}
              onChange={(event) => setFormState((current) => ({ ...current, metadata: event.target.value }))}
              placeholder='{"team":"platform"}'
            />
          </label>
          <div className="inline-actions">
            <button type="submit" className="primary-button" disabled={!selectedName || isMutating}>
              {loginMutation.isPending ? "Submitting..." : "Login / Save Session"}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}

function authBadgeClass(state: string) {
  if (state === "active" || state === "configured") {
    return "badge badge-safe";
  }
  if (state === "expiring") {
    return "badge badge-warn";
  }
  if (state === "login_required" || state === "expired" || state === "failed" || state === "revoked") {
    return "badge badge-danger";
  }
  return "badge badge-neutral";
}
