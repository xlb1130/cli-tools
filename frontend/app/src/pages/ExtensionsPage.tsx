import { ChangeEvent, useEffect, useMemo, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import {
  useExtensionEvents,
  useExplainHookDispatch,
  useExtensionsSummary,
  useHookContracts,
  useHooks,
  usePlugins,
  useProviders,
  useSimulateHookDispatch,
} from "../lib/api";
import { formatDate, formatList } from "../lib/format";
import type { ExtensionEvent, HookContract } from "../lib/types";

const EVENT_PAGE_SIZE = 12;
const HOOK_LAB_STORAGE_KEY = "cts.hook-lab-scenarios.v1";

type SavedHookScenario = {
  id: string;
  name: string;
  event: string;
  payloadText: string;
  mountId: string;
  sourceName: string;
  updatedAt: string;
};

export function ExtensionsPage() {
  const [selectedPlugin, setSelectedPlugin] = useState<string | null>(null);
  const [selectedHookEvent, setSelectedHookEvent] = useState<string>("");
  const [eventFilters, setEventFilters] = useState({
    plugin: "",
    level: "",
    event: "",
    mountId: "",
  });
  const [beforeTs, setBeforeTs] = useState<string | undefined>(undefined);
  const [eventItems, setEventItems] = useState<ExtensionEvent[]>([]);
  const [labEvent, setLabEvent] = useState<string>("explain.before");
  const [labPayloadText, setLabPayloadText] = useState<string>('{"args":{"text":"hello"},"runtime":{}}');
  const [labMountId, setLabMountId] = useState<string>("");
  const [labSourceName, setLabSourceName] = useState<string>("");
  const [labError, setLabError] = useState<string | null>(null);
  const [scenarioName, setScenarioName] = useState<string>("");
  const [savedScenarios, setSavedScenarios] = useState<SavedHookScenario[]>(() => loadSavedHookScenarios());
  const explainDispatchMutation = useExplainHookDispatch();
  const simulateDispatchMutation = useSimulateHookDispatch();

  const summaryQuery = useExtensionsSummary();
  const pluginsQuery = usePlugins();
  const providersQuery = useProviders();
  const hooksQuery = useHooks(selectedHookEvent ? { event: selectedHookEvent } : undefined);
  const contractsQuery = useHookContracts();
  const eventsQuery = useExtensionEvents({
    limit: EVENT_PAGE_SIZE,
    plugin: eventFilters.plugin || undefined,
    level: eventFilters.level || undefined,
    event: eventFilters.event || undefined,
    mountId: eventFilters.mountId || undefined,
    beforeTs,
  });

  const loading =
    summaryQuery.isLoading ||
    pluginsQuery.isLoading ||
    providersQuery.isLoading ||
    hooksQuery.isLoading ||
    contractsQuery.isLoading ||
    eventsQuery.isLoading;
  const summary = summaryQuery.data;
  const pluginPayload = pluginsQuery.data ?? { items: [], provider_conflicts: [] };
  const plugins = pluginPayload.items;
  const providers = providersQuery.data ?? [];
  const hooks = hooksQuery.data ?? [];
  const contracts = contractsQuery.data ?? [];
  const eventsResponse = eventsQuery.data ?? { items: [], filters: {}, next_before_ts: null };
  const activePlugin = plugins.find((item) => item.name === selectedPlugin) ?? plugins[0] ?? null;
  const visibleEvents = eventItems.length ? eventItems : eventsResponse.items;
  const eventNames = contracts.map((item) => item.event);
  const contractByEvent = useMemo(() => {
    const result = new Map<string, (typeof contracts)[number]>();
    for (const item of contracts) {
      result.set(item.event, item);
    }
    return result;
  }, [contracts]);
  const activeContract = contractByEvent.get(labEvent) ?? contracts[0] ?? null;

  // Hooks must be called before any early returns
  useEffect(() => {
    if (!beforeTs || eventsQuery.isFetching) {
      return;
    }
    setEventItems((current) => {
      const base = current.length ? current : [];
      const merged = [...base, ...eventsResponse.items];
      const seen = new Set<string>();
      return merged.filter((item) => {
        const key = `${item.ts}:${item.event}:${String(item.data?.index ?? "")}:${String(item.run_id ?? "")}`;
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
    });
    setBeforeTs(undefined);
  }, [beforeTs, eventsQuery.isFetching, eventsResponse.items]);

  useEffect(() => {
    if (selectedHookEvent) {
      setLabEvent(selectedHookEvent);
    }
  }, [selectedHookEvent]);

  if (loading) {
    return <LoadingState label="加载扩展调试视图" />;
  }

  if (summaryQuery.isError) {
    return <ErrorState title="Extensions 加载失败" error={summaryQuery.error} />;
  }

  const readySummary = summary!;

  const applyEventFilters = () => {
    setBeforeTs(undefined);
    setEventItems([]);
  };

  const loadMoreEvents = () => {
    if (!eventsResponse.next_before_ts) {
      return;
    }
    setEventItems((current) => [...(current.length ? current : eventsResponse.items)]);
    setBeforeTs(eventsResponse.next_before_ts || undefined);
  };

  const onEventFilterChange = (key: "plugin" | "level" | "event" | "mountId") => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setEventFilters((current) => ({ ...current, [key]: e.target.value }));
  };

  const runHookLab = async (executeHandlers: boolean) => {
    setLabError(null);
    let parsedPayload: Record<string, unknown>;
    try {
      const parsed = JSON.parse(labPayloadText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("payload must be a JSON object");
      }
      parsedPayload = parsed as Record<string, unknown>;
    } catch (error) {
      const message = error instanceof Error ? error.message : "invalid JSON";
      setLabError(`Payload JSON 无法解析: ${message}`);
      return;
    }

    if (executeHandlers) {
      await simulateDispatchMutation.mutateAsync({
        event: labEvent,
        payload: parsedPayload,
        executeHandlers: true,
        mountId: labMountId || undefined,
        sourceName: labSourceName || undefined,
      });
      return;
    }

    await explainDispatchMutation.mutateAsync({
      event: labEvent,
      payload: parsedPayload,
      mountId: labMountId || undefined,
      sourceName: labSourceName || undefined,
    });
  };

  const applySampleContract = (contract: HookContract | null) => {
    if (!contract) {
      return;
    }
    setLabEvent(contract.event);
    setLabPayloadText(JSON.stringify(contract.sample_payload, null, 2));
    if (contract.sample_context.mount_required && !labMountId) {
      setLabMountId("plugin-echo");
    }
    if (contract.sample_context.source_required && !labSourceName) {
      setLabSourceName("plugin_source");
    }
  };

  const saveScenario = () => {
    const trimmed = scenarioName.trim();
    if (!trimmed) {
      setLabError("请先填写场景名称。");
      return;
    }
    const nextScenario: SavedHookScenario = {
      id: `${labEvent}:${Date.now()}`,
      name: trimmed,
      event: labEvent,
      payloadText: labPayloadText,
      mountId: labMountId,
      sourceName: labSourceName,
      updatedAt: new Date().toISOString(),
    };
    const nextItems = [nextScenario, ...savedScenarios].slice(0, 20);
    setSavedScenarios(nextItems);
    persistSavedHookScenarios(nextItems);
    setScenarioName("");
    setLabError(null);
  };

  const loadScenario = (scenario: SavedHookScenario) => {
    setLabEvent(scenario.event);
    setLabPayloadText(scenario.payloadText);
    setLabMountId(scenario.mountId);
    setLabSourceName(scenario.sourceName);
    setScenarioName(scenario.name);
    setLabError(null);
  };

  const removeScenario = (scenarioId: string) => {
    const nextItems = savedScenarios.filter((item) => item.id !== scenarioId);
    setSavedScenarios(nextItems);
    persistSavedHookScenarios(nextItems);
  };

  return (
    <div className="page-stack">
      <section className="stats-grid">
        <StatCard label="Plugin Providers" value={String(readySummary.plugin_provider_count)} />
        <StatCard label="Core Providers" value={String(readySummary.core_provider_count)} />
        <StatCard label="Provider Conflicts" value={String(readySummary.provider_conflict_count)} />
        <StatCard label="Recent Events" value={String(readySummary.recent_event_count)} />
      </section>

      <div className="content-grid two-col">
        <Panel title="Loaded Plugins" subtitle="每个 plugin 的 provider 注册与 hook 绑定快照">
          <div className="card-list">
            {plugins.map((plugin) => (
              <button
                key={plugin.name}
                type="button"
                className={`source-card source-card-button ${activePlugin?.name === plugin.name ? "focused" : ""}`}
                onClick={() => setSelectedPlugin(plugin.name)}
              >
                <div className="source-card-top">
                  <div>
                    <h3>{plugin.name}</h3>
                    <p>{plugin.module || plugin.path || "in-process plugin"}</p>
                  </div>
                  <span className={plugin.enabled ? "badge badge-safe" : "badge badge-danger"}>
                    {plugin.enabled ? "loaded" : "disabled"}
                  </span>
                </div>
                <dl className="detail-list">
                  <div>
                    <dt>Providers</dt>
                    <dd>{plugin.provider_types.length}</dd>
                  </div>
                  <div>
                    <dt>Hook Bindings</dt>
                    <dd>{plugin.bound_hooks.length}</dd>
                  </div>
                </dl>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Hook Events" subtitle="配置中的 hook 绑定分布">
          <div className="table-like">
            {readySummary.hooks_by_event.map((item) => (
              <button
                key={item.event}
                type="button"
                className={`row-card source-card-button ${selectedHookEvent === item.event ? "focused" : ""}`}
                onClick={() => setSelectedHookEvent((current) => (current === item.event ? "" : item.event))}
              >
                <div>
                  <strong>{item.event}</strong>
                  <p>enabled hooks</p>
                </div>
                <span className="badge badge-neutral">{item.count}</span>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Provider Ownership" subtitle="内置 provider 与 plugin provider 的统一注册表">
          <div className="table-like">
            {providers.map((provider) => (
              <article key={provider.provider_type} className="table-item">
                <div className="table-item-main">
                  <div className="table-item-title">
                    <strong>{provider.provider_type}</strong>
                    <span className={provider.owner_type === "plugin" ? "badge badge-safe" : "badge badge-neutral"}>
                      {provider.owner_type === "plugin" ? provider.owner_name : "core"}
                    </span>
                  </div>
                  <p>
                    {provider.class_name} · {provider.module}
                  </p>
                </div>
                <div className="table-item-meta">
                  <p>Sources: {provider.source_count}</p>
                  <p>Mounts: {provider.mount_count}</p>
                  <p>Conflicts: {provider.conflict_count}</p>
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel
          title="Recent Dispatch Timeline"
          subtitle="可按 plugin / level / event / mount 过滤，也支持继续加载更早事件"
          actions={
            <button type="button" className="secondary-button" onClick={applyEventFilters}>
              Apply Filters
            </button>
          }
        >
          <div className="filters extension-filters">
            <select className="field" value={eventFilters.plugin} onChange={onEventFilterChange("plugin")}>
              <option value="">All plugins</option>
              {plugins.map((plugin) => (
                <option key={plugin.name} value={plugin.name}>
                  {plugin.name}
                </option>
              ))}
            </select>
            <select className="field" value={eventFilters.level} onChange={onEventFilterChange("level")}>
              <option value="">All levels</option>
              <option value="INFO">INFO</option>
              <option value="WARN">WARN</option>
              <option value="ERROR">ERROR</option>
            </select>
            <select className="field" value={eventFilters.event} onChange={onEventFilterChange("event")}>
              <option value="">All events</option>
              <option value="hook_dispatch_start">hook_dispatch_start</option>
              <option value="hook_dispatch_complete">hook_dispatch_complete</option>
              <option value="hook_dispatch_skipped">hook_dispatch_skipped</option>
              <option value="hook_dispatch_error">hook_dispatch_error</option>
              <option value="hook_failed">hook_failed</option>
            </select>
            <input
              className="field"
              placeholder="mount id"
              value={eventFilters.mountId}
              onChange={onEventFilterChange("mountId")}
            />
          </div>

          <div className="event-list">
            {visibleEvents.map((event) => (
              <article key={`${event.ts}-${event.event}-${String(event.data?.index ?? "na")}`} className="event-card">
                <div className="event-card-top">
                  <strong>{event.event}</strong>
                  <span
                    className={`badge ${
                      event.level === "ERROR" ? "badge-danger" : event.level === "WARN" ? "badge-warn" : "badge-neutral"
                    }`}
                  >
                    {event.level}
                  </span>
                </div>
                <p className="muted">{formatDate(event.ts)}</p>
                <p>
                  {String(event.data?.plugin || "-")} · {String(event.data?.handler || "-")} · {String(event.data?.hook_event || "-")}
                </p>
                <p>
                  mount {event.mount_id || "-"} · source {event.source || "-"}
                </p>
              </article>
            ))}
          </div>
          {eventsResponse.next_before_ts ? (
            <div className="inline-actions">
              <button type="button" className="secondary-button" onClick={loadMoreEvents} disabled={eventsQuery.isFetching}>
                {eventsQuery.isFetching ? "Loading..." : "Load More"}
              </button>
            </div>
          ) : null}
        </Panel>
      </div>

      {activePlugin ? (
        <div className="content-grid two-col">
          <Panel title={`Plugin Detail: ${activePlugin.name}`} subtitle="选中的 plugin 详细拓扑和绑定">
            <dl className="detail-list">
              <div>
                <dt>Origin</dt>
                <dd>{activePlugin.origin_file || activePlugin.resolved_path || activePlugin.module || "-"}</dd>
              </div>
              <div>
                <dt>Hook Handlers</dt>
                <dd>{formatList(activePlugin.hook_handlers)}</dd>
              </div>
              <div>
                <dt>Registered Providers</dt>
                <dd>{formatList(activePlugin.provider_types.map((item) => item.provider_type))}</dd>
              </div>
            </dl>

            <div className="stack">
              {activePlugin.bound_hooks.map((hook) => (
                <article key={hook.id} className="row-card">
                  <div>
                    <strong>
                      {hook.event}
                      {" -> "}
                      {hook.handler}
                    </strong>
                    <p>
                      priority {hook.priority} · fail_mode {hook.fail_mode}
                    </p>
                  </div>
                  <span className={hook.handler_available ? "badge badge-safe" : "badge badge-danger"}>
                    {hook.handler_available ? "bound" : "broken"}
                  </span>
                </article>
              ))}
            </div>
          </Panel>

          <Panel title="Selected Plugin JSON" subtitle="保留原始结构，方便人工和 AI 直接检查">
            <JsonViewer data={activePlugin} />
          </Panel>
        </div>
      ) : null}

      <div className="content-grid two-col">
        <Panel title="Configured Hooks" subtitle="所有 hook 绑定的结构化视图">
          <div className="table-like">
            {hooks.map((hook) => (
              <article key={hook.id} className="row-card">
                <div>
                  <strong>
                    {hook.event} / {hook.plugin}.{hook.handler}
                  </strong>
                  <p>
                    priority {hook.priority} · fail_mode {hook.fail_mode}
                  </p>
                </div>
                <span className={hook.enabled ? "badge badge-safe" : "badge badge-danger"}>
                  {hook.enabled ? "enabled" : "disabled"}
                </span>
              </article>
            ))}
          </div>
        </Panel>

        <Panel title="Provider Conflicts" subtitle="重复 provider 注册的当前治理结果">
          <JsonViewer data={pluginPayload.provider_conflicts} />
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Hook Payload Contracts" subtitle="当前已公开的 hook event 输入/可变更字段合同">
          <div className="table-like">
            {contracts.map((contract) => (
              <button
                key={contract.event}
                type="button"
                className={`row-card source-card-button ${selectedHookEvent === contract.event ? "focused" : ""}`}
                onClick={() => {
                  setSelectedHookEvent(contract.event);
                  applySampleContract(contract);
                }}
              >
                <div>
                  <strong>{contract.event}</strong>
                  <p>
                    {contract.stage} · mutable {formatList(contract.may_mutate)}
                  </p>
                </div>
                <span className="badge badge-neutral">{contract.payload_fields.length} fields</span>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Selected Hook Contract" subtitle="按事件查看 payload 字段和可变更范围">
          <JsonViewer data={selectedHookEvent ? contractByEvent.get(selectedHookEvent) ?? null : contracts[0] ?? null} />
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel
          title="Hook Lab"
          subtitle="输入 event、payload 和上下文，解释命中逻辑或直接模拟 handler 链"
          actions={
            <div className="explain-actions">
              <button type="button" className="secondary-button" onClick={() => applySampleContract(activeContract)}>
                Load Contract Sample
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void runHookLab(false)}
                disabled={explainDispatchMutation.isPending || simulateDispatchMutation.isPending}
              >
                {explainDispatchMutation.isPending ? "Explaining..." : "Explain Match"}
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => void runHookLab(true)}
                disabled={simulateDispatchMutation.isPending || explainDispatchMutation.isPending}
              >
                {simulateDispatchMutation.isPending ? "Simulating..." : "Simulate Handlers"}
              </button>
            </div>
          }
        >
          <div className="filters extension-filters">
            <select className="field" value={labEvent} onChange={(e) => setLabEvent(e.target.value)}>
              {eventNames.map((eventName) => (
                <option key={eventName} value={eventName}>
                  {eventName}
                </option>
              ))}
            </select>
            <input className="field" placeholder="mount id (optional)" value={labMountId} onChange={(e) => setLabMountId(e.target.value)} />
            <input className="field" placeholder="source name (optional)" value={labSourceName} onChange={(e) => setLabSourceName(e.target.value)} />
            <input className="field" value={selectedHookEvent || labEvent} readOnly />
          </div>
          <div className="filters extension-filters">
            <input className="field" placeholder="scenario name" value={scenarioName} onChange={(e) => setScenarioName(e.target.value)} />
            <input
              className="field"
              value={activeContract?.simulation.risk_level || "unknown"}
              readOnly
            />
            <input className="field" value={String(activeContract?.simulation.provider_calls_blocked ?? true)} readOnly />
            <button type="button" className="secondary-button" onClick={saveScenario}>
              Save Scenario
            </button>
          </div>
          <textarea
            className="json-input"
            value={labPayloadText}
            onChange={(e) => setLabPayloadText(e.target.value)}
            spellCheck={false}
          />
          {activeContract ? (
            <div className="inline-note">
              Risk: {activeContract.simulation.risk_level}. {activeContract.simulation.notes.join(" ")}
            </div>
          ) : null}
          {labError ? <div className="inline-error">{labError}</div> : null}
          {explainDispatchMutation.isError ? (
            <div className="inline-error">{explainDispatchMutation.error instanceof Error ? explainDispatchMutation.error.message : "Explain failed"}</div>
          ) : null}
          {simulateDispatchMutation.isError ? (
            <div className="inline-error">{simulateDispatchMutation.error instanceof Error ? simulateDispatchMutation.error.message : "Simulate failed"}</div>
          ) : null}
        </Panel>

        <Panel title="Hook Lab Result" subtitle="Explain 或 simulate 的结构化返回">
          <JsonViewer data={simulateDispatchMutation.data ?? explainDispatchMutation.data ?? null} />
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Saved Hook Scenarios" subtitle="浏览器本地保存的常用调试样本，可快速复用">
          <div className="table-like">
            {savedScenarios.length ? (
              savedScenarios.map((scenario) => (
                <article key={scenario.id} className="row-card">
                  <div>
                    <strong>{scenario.name}</strong>
                    <p>
                      {scenario.event} · {formatDate(scenario.updatedAt)}
                    </p>
                  </div>
                  <div className="table-item-meta">
                    <button type="button" className="secondary-button" onClick={() => loadScenario(scenario)}>
                      Load
                    </button>
                    <button type="button" className="secondary-button" onClick={() => removeScenario(scenario.id)}>
                      Delete
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <div className="inline-note">还没有保存场景。先在 Hook Lab 中配置一个样本再保存。</div>
            )}
          </div>
        </Panel>

        <Panel title="Simulation Boundaries" subtitle="当前 Hook Lab 的边界说明">
          <JsonViewer
            data={
              simulateDispatchMutation.data?.simulation ??
              activeContract?.simulation ?? {
                risk_level: "unknown",
                provider_calls_blocked: true,
                plugin_side_effects_possible: true,
              }
            }
          />
        </Panel>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function loadSavedHookScenarios(): SavedHookScenario[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(HOOK_LAB_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item) => item && typeof item === "object") as SavedHookScenario[];
  } catch {
    return [];
  }
}

function persistSavedHookScenarios(items: SavedHookScenario[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(HOOK_LAB_STORAGE_KEY, JSON.stringify(items));
}
