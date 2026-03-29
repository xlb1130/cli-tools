import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AppSummary,
  CatalogResponse,
  ExtensionEvent,
  ExtensionEventsResponse,
  ExplainResponse,
  ExtensionsSummary,
  HookBinding,
  HookDispatchExplainResponse,
  HookDispatchSimulateResponse,
  HookContract,
  MountDetail,
  MountHelp,
  MountSummary,
  PluginDetail,
  ProviderInventoryItem,
  ReloadResponse,
  RunRecord,
  SourceDetail,
  SourceSummary,
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

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: ["runs", limit],
    queryFn: async () => {
      const payload = await request<{ items: RunRecord[] }>(`/api/runs?limit=${limit}`);
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
