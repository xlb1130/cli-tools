import { useMemo, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { useAppLogs, useConfigLogs, useDiscoveryLogs, useSources } from "../lib/api";
import { formatDate } from "../lib/format";
import type { LogEvent } from "../lib/types";

const LOG_LIMIT = 30;

export function LogsPage() {
  const sourcesQuery = useSources();
  const [appFilters, setAppFilters] = useState({ level: "", source: "", mountId: "", events: "" });
  const [discoveryFilters, setDiscoveryFilters] = useState({ source: "", eventPrefix: "" });
  const appLogsQuery = useAppLogs({
    limit: LOG_LIMIT,
    level: appFilters.level || undefined,
    source: appFilters.source || undefined,
    mountId: appFilters.mountId || undefined,
    events: appFilters.events || undefined,
  });
  const discoveryLogsQuery = useDiscoveryLogs({
    limit: LOG_LIMIT,
    source: discoveryFilters.source || undefined,
    eventPrefix: discoveryFilters.eventPrefix || undefined,
  });
  const configLogsQuery = useConfigLogs(LOG_LIMIT);

  const loading = sourcesQuery.isLoading || appLogsQuery.isLoading || discoveryLogsQuery.isLoading || configLogsQuery.isLoading;
  const error = sourcesQuery.error || appLogsQuery.error || discoveryLogsQuery.error || configLogsQuery.error;
  const sourceOptions = sourcesQuery.data ?? [];
  const appEvents = useMemo(() => appLogsQuery.data ?? [], [appLogsQuery.data]);
  const discoveryEvents = useMemo(() => discoveryLogsQuery.data ?? [], [discoveryLogsQuery.data]);
  const configEvents = useMemo(() => configLogsQuery.data ?? [], [configLogsQuery.data]);

  if (loading) {
    return <LoadingState label="加载 logs" />;
  }

  if (error) {
    return <ErrorState title="Logs 页面加载失败" error={error} />;
  }

  return (
    <div className="page-stack">
      <Panel title="App Logs" subtitle="运行时事件、hook 调度、auth 操作与 HTTP surface 事件">
        <div className="filters">
          <label>
            <span className="field-label">Level</span>
            <select className="field" value={appFilters.level} onChange={(event) => setAppFilters((current) => ({ ...current, level: event.target.value }))}>
              <option value="">All</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </label>
          <label>
            <span className="field-label">Source</span>
            <select className="field" value={appFilters.source} onChange={(event) => setAppFilters((current) => ({ ...current, source: event.target.value }))}>
              <option value="">All</option>
              {sourceOptions.map((source) => (
                <option key={source.name} value={source.name}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Mount ID</span>
            <input className="field" value={appFilters.mountId} onChange={(event) => setAppFilters((current) => ({ ...current, mountId: event.target.value }))} />
          </label>
          <label>
            <span className="field-label">Events</span>
            <input className="field" value={appFilters.events} onChange={(event) => setAppFilters((current) => ({ ...current, events: event.target.value }))} placeholder="auth_login_complete,surface_sync_complete" />
          </label>
        </div>
        <EventList items={appEvents} emptyLabel="暂无 app logs。" />
      </Panel>

      <div className="content-grid two-col">
        <Panel title="Discovery Logs" subtitle="sync / discovery / schema import 过程">
          <div className="filters">
            <label>
              <span className="field-label">Source</span>
              <select className="field" value={discoveryFilters.source} onChange={(event) => setDiscoveryFilters((current) => ({ ...current, source: event.target.value }))}>
                <option value="">All</option>
                {sourceOptions.map((source) => (
                  <option key={source.name} value={source.name}>
                    {source.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Event Prefix</span>
              <input
                className="field"
                value={discoveryFilters.eventPrefix}
                onChange={(event) => setDiscoveryFilters((current) => ({ ...current, eventPrefix: event.target.value }))}
                placeholder="discovery. / schema. / sync."
              />
            </label>
          </div>
          <EventList items={discoveryEvents} emptyLabel="暂无 discovery logs。" />
        </Panel>

        <Panel title="Config Logs" subtitle="配置加载、lint、merge 等留痕">
          <EventList items={configEvents} emptyLabel="暂无 config logs。" />
        </Panel>
      </div>
    </div>
  );
}

function EventList({ items, emptyLabel }: { items: LogEvent[]; emptyLabel: string }) {
  if (!items.length) {
    return <div className="state">{emptyLabel}</div>;
  }

  return (
    <div className="event-list">
      {items.map((item, index) => (
        <article key={`${item.ts}:${item.event}:${index}`} className="event-card">
          <div className="event-card-top">
            <div>
              <strong>{item.event}</strong>
              <p className="muted">{formatDate(item.ts)}</p>
            </div>
            <span className={logBadgeClass(item.level)}>{item.level}</span>
          </div>
          <dl className="detail-grid">
            <div>
              <dt>Source</dt>
              <dd>{item.source || "-"}</dd>
            </div>
            <div>
              <dt>Mount</dt>
              <dd>{item.mount_id || "-"}</dd>
            </div>
            <div>
              <dt>Run</dt>
              <dd>{item.run_id || "-"}</dd>
            </div>
            <div>
              <dt>Surface</dt>
              <dd>{item.surface || "-"}</dd>
            </div>
          </dl>
          {item.message ? <p>{item.message}</p> : null}
          <JsonViewer data={item.data || {}} />
        </article>
      ))}
    </div>
  );
}

function logBadgeClass(level: string) {
  if (level === "ERROR") {
    return "badge badge-danger";
  }
  if (level === "WARNING") {
    return "badge badge-warn";
  }
  if (level === "INFO") {
    return "badge badge-safe";
  }
  return "badge badge-neutral";
}
