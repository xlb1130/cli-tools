import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AliasListResponse,
  AliasMutationResponse,
  AliasRecord,
  AppSummary,
  AuthActionResponse,
  AuthInventoryResponse,
  AuthProfileStatus,
  CatalogResponse,
  DriftReport,
  ExtensionEvent,
  ExtensionEventsResponse,
  ExplainResponse,
  ExtensionsSummary,
  HookBinding,
  HookDispatchExplainResponse,
  HookDispatchSimulateResponse,
  HookContract,
  InvokeResponse,
  LogEvent,
  LogResponse,
  MountDetail,
  MountHelp,
  MountMutationResponse,
  MountSummary,
  PluginDetail,
  ProviderInventoryItem,
  ReliabilityStatusPayload,
  ReloadResponse,
  RunRecord,
  SourceDetail,
  SourceMutationResponse,
  SourceSummary,
  SourceTestResponse,
  SyncResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.error?.message || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function useAppSummary() {
  return useQuery({
    queryKey: ["app-summary"],
    queryFn: () => request<AppSummary>("/api/app/summary"),
  });
}

export function useReliabilityStatus() {
  return useQuery({
    queryKey: ["reliability-status"],
    queryFn: () => request<ReliabilityStatusPayload>("/api/reliability"),
  });
}

export function useAuthProfiles() {
  return useQuery({
    queryKey: ["auth-profiles"],
    queryFn: () => request<AuthInventoryResponse>("/api/auth/profiles"),
  });
}

export function useAuthProfile(name: string) {
  return useQuery({
    queryKey: ["auth-profile", name],
    queryFn: () => request<AuthProfileStatus>(`/api/auth/profiles/${encodeURIComponent(name)}`),
    enabled: Boolean(name),
  });
}

export function useAliases() {
  return useQuery({
    queryKey: ["aliases"],
    queryFn: async () => {
      const payload = await request<AliasListResponse>("/api/aliases");
      return payload.items;
    },
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: async () => {
      const payload = await request<{ items: SourceSummary[] }>("/api/sources");
      return payload.items;
    },
  });
}

export function useExtensionsSummary() {
  return useQuery({
    queryKey: ["extensions-summary"],
    queryFn: () => request<ExtensionsSummary>("/api/extensions/summary"),
  });
}

export function usePlugins() {
  return useQuery({
    queryKey: ["extensions-plugins"],
    queryFn: async () => {
      const payload = await request<{ items: PluginDetail[]; provider_conflicts: Array<Record<string, unknown>> }>(
        "/api/extensions/plugins",
      );
      return payload;
    },
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ["extensions-providers"],
    queryFn: async () => {
      const payload = await request<{ items: ProviderInventoryItem[] }>("/api/extensions/providers");
      return payload.items;
    },
  });
}

export function useHooks(filters?: { event?: string; plugin?: string }) {
  return useQuery({
    queryKey: ["extensions-hooks", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.event) params.set("event", filters.event);
      if (filters?.plugin) params.set("plugin", filters.plugin);
      const payload = await request<{ items: HookBinding[] }>(
        `/api/extensions/hooks${params.toString() ? `?${params.toString()}` : ""}`,
      );
      return payload.items;
    },
  });
}

export function useHookContracts() {
  return useQuery({
    queryKey: ["extensions-contracts"],
    queryFn: async () => {
      const payload = await request<{ version: number; items: HookContract[] }>("/api/extensions/contracts");
      return payload.items;
    },
  });
}

export function useExtensionEvents(filters?: {
  limit?: number;
  event?: string;
  plugin?: string;
  hookEvent?: string;
  level?: string;
  mountId?: string;
  source?: string;
  beforeTs?: string;
}) {
  return useQuery({
    queryKey: ["extensions-events", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.limit) params.set("limit", String(filters.limit));
      if (filters?.event) params.set("event", filters.event);
      if (filters?.plugin) params.set("plugin", filters.plugin);
      if (filters?.hookEvent) params.set("hook_event", filters.hookEvent);
      if (filters?.level) params.set("level", filters.level);
      if (filters?.mountId) params.set("mount_id", filters.mountId);
      if (filters?.source) params.set("source", filters.source);
      if (filters?.beforeTs) params.set("before_ts", filters.beforeTs);
      return request<ExtensionEventsResponse>(`/api/extensions/events${params.toString() ? `?${params.toString()}` : ""}`);
    },
  });
}

export function useSource(sourceName: string) {
  return useQuery({
    queryKey: ["source", sourceName],
    queryFn: () => request<SourceDetail>(`/api/sources/${sourceName}`),
    enabled: Boolean(sourceName),
  });
}

export function useTestSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sourceName, discover }: { sourceName: string; discover: boolean }) =>
      request<SourceTestResponse>(`/api/sources/${encodeURIComponent(sourceName)}/test`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ discover }),
      }),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["source", variables.sourceName] }),
        queryClient.invalidateQueries({ queryKey: ["catalog"] }),
        queryClient.invalidateQueries({ queryKey: ["drift-report"] }),
      ]);
    },
  });
}

export function useMounts(filters?: { q?: string; risk?: string; source?: string; surface?: string }) {
  return useQuery({
    queryKey: ["mounts", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.q) params.set("q", filters.q);
      if (filters?.risk) params.set("risk", filters.risk);
      if (filters?.source) params.set("source", filters.source);
      if (filters?.surface) params.set("surface", filters.surface);
      const payload = await request<{ items: MountSummary[] }>(
        `/api/mounts${params.toString() ? `?${params.toString()}` : ""}`,
      );
      return payload.items;
    },
  });
}

export function useMount(mountId: string) {
  return useQuery({
    queryKey: ["mount", mountId],
    queryFn: () => request<MountDetail>(`/api/mounts/${mountId}`),
    enabled: Boolean(mountId),
  });
}

export function useMountHelp(mountId: string) {
  return useQuery({
    queryKey: ["mount-help", mountId],
    queryFn: () => request<MountHelp>(`/api/mounts/${mountId}/help`),
    enabled: Boolean(mountId),
  });
}

export function useCatalog() {
  return useQuery({
    queryKey: ["catalog"],
    queryFn: () => request<CatalogResponse>("/api/catalog"),
  });
}

export function useDriftReport(sourceName?: string) {
  return useQuery({
    queryKey: ["drift-report", sourceName],
    queryFn: () => request<DriftReport>(sourceName ? `/api/drift/${encodeURIComponent(sourceName)}` : "/api/drift"),
    enabled: sourceName !== "",
  });
}

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: ["runs", limit],
    queryFn: async () => {
      const payload = await request<{ items: RunRecord[] }>(`/api/runs?limit=${limit}`);
      return payload.items;
    },
  });
}

export function useConfigLogs(limit = 50, beforeTs?: string) {
  return useQuery({
    queryKey: ["config-logs", limit, beforeTs],
    queryFn: async () => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (beforeTs) params.set("before_ts", beforeTs);
      const payload = await request<LogResponse>(`/api/logs/config?${params.toString()}`);
      return payload.items;
    },
  });
}

export function useDiscoveryLogs(filters?: { limit?: number; source?: string; eventPrefix?: string; beforeTs?: string }) {
  return useQuery({
    queryKey: ["discovery-logs", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("limit", String(filters?.limit ?? 50));
      if (filters?.source) params.set("source", filters.source);
      if (filters?.eventPrefix) params.set("event_prefix", filters.eventPrefix);
      if (filters?.beforeTs) params.set("before_ts", filters.beforeTs);
      const payload = await request<LogResponse>(`/api/logs/discovery?${params.toString()}`);
      return payload.items;
    },
  });
}

export function useAppLogs(filters?: {
  limit?: number;
  events?: string;
  level?: string;
  source?: string;
  mountId?: string;
  beforeTs?: string;
}) {
  return useQuery({
    queryKey: ["app-logs", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("limit", String(filters?.limit ?? 50));
      if (filters?.events) params.set("events", filters.events);
      if (filters?.level) params.set("level", filters.level);
      if (filters?.source) params.set("source", filters.source);
      if (filters?.mountId) params.set("mount_id", filters.mountId);
      if (filters?.beforeTs) params.set("before_ts", filters.beforeTs);
      const payload = await request<LogResponse>(`/api/logs/app?${params.toString()}`);
      return payload.items;
    },
  });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => request<RunRecord>(`/api/runs/${runId}`),
    enabled: Boolean(runId),
  });
}

export function useExplainMount(mountId: string) {
  return useMutation({
    mutationFn: (input: Record<string, unknown>) =>
      request<ExplainResponse>(`/api/mounts/${mountId}/explain`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ input }),
      }),
  });
}

export function useInvokeMount(mountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ input, dryRun }: { input: Record<string, unknown>; dryRun?: boolean }) =>
      request<InvokeResponse>(`/api/mounts/${mountId}/invoke`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ input, dry_run: Boolean(dryRun) }),
      }),
    onSuccess: async (payload) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
        queryClient.invalidateQueries({ queryKey: ["run", payload.run_id] }),
      ]);
    },
  });
}

export function useExplainHookDispatch() {
  return useMutation({
    mutationFn: (input: {
      event: string;
      payload: Record<string, unknown>;
      mountId?: string;
      sourceName?: string;
    }) =>
      request<HookDispatchExplainResponse>("/api/extensions/hooks/explain", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          event: input.event,
          payload: input.payload,
          mount_id: input.mountId,
          source_name: input.sourceName,
        }),
      }),
  });
}

export function useSimulateHookDispatch() {
  return useMutation({
    mutationFn: (input: {
      event: string;
      payload: Record<string, unknown>;
      executeHandlers: boolean;
      mountId?: string;
      sourceName?: string;
    }) =>
      request<HookDispatchSimulateResponse>("/api/extensions/hooks/simulate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          event: input.event,
          payload: input.payload,
          execute_handlers: input.executeHandlers,
          mount_id: input.mountId,
          source_name: input.sourceName,
        }),
      }),
  });
}

export function useReloadApp() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      request<ReloadResponse>("/api/reload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-plugins"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-providers"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-hooks"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-contracts"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-events"] }),
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["mounts"] }),
        queryClient.invalidateQueries({ queryKey: ["catalog"] }),
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
      ]);
    },
  });
}

export function useAuthLogin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      request<AuthActionResponse>("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }),
    onSuccess: async (_, variables) => {
      const profileName = typeof variables.name === "string" ? variables.name : undefined;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["auth-profiles"] }),
        queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        profileName ? queryClient.invalidateQueries({ queryKey: ["auth-profile", profileName] }) : Promise.resolve(),
      ]);
    },
  });
}

export function useAuthRefresh() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) =>
      request<AuthActionResponse>(`/api/auth/refresh/${encodeURIComponent(name)}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async (_, name) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["auth-profiles"] }),
        queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["auth-profile", name] }),
      ]);
    },
  });
}

export function useAuthLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) =>
      request<AuthActionResponse>(`/api/auth/logout/${encodeURIComponent(name)}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async (_, name) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["auth-profiles"] }),
        queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["auth-profile", name] }),
      ]);
    },
  });
}

export function useSyncAll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      request<SyncResponse>("/api/sync", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-plugins"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-providers"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-hooks"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-contracts"] }),
        queryClient.invalidateQueries({ queryKey: ["extensions-events"] }),
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["mounts"] }),
        queryClient.invalidateQueries({ queryKey: ["catalog"] }),
      ]);
    },
  });
}

function invalidateManagementQueries(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
    queryClient.invalidateQueries({ queryKey: ["sources"] }),
    queryClient.invalidateQueries({ queryKey: ["mounts"] }),
    queryClient.invalidateQueries({ queryKey: ["catalog"] }),
    queryClient.invalidateQueries({ queryKey: ["aliases"] }),
    queryClient.invalidateQueries({ queryKey: ["drift-report"] }),
  ]);
}

export function useAddSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      request<SourceMutationResponse>("/api/sources", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}

export function useRemoveSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceName, force }: { sourceName: string; force: boolean }) =>
      request<SourceMutationResponse>(`/api/sources/${encodeURIComponent(sourceName)}/remove`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ force }),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}

export function useAddMount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      request<MountMutationResponse>("/api/mounts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}

export function useRemoveMount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mountId: string) =>
      request<MountMutationResponse>(`/api/mounts/${encodeURIComponent(mountId)}/remove`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}

export function useAddAlias() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { aliasFrom: string; aliasTo: string }) =>
      request<AliasMutationResponse>("/api/aliases", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          alias_from: payload.aliasFrom,
          alias_to: payload.aliasTo,
        }),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}

export function useRemoveAlias() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aliasFrom: string) =>
      request<AliasMutationResponse>(`/api/aliases/${encodeURIComponent(aliasFrom)}/remove`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => invalidateManagementQueries(queryClient),
  });
}
