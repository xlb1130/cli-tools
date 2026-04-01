import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AppSummary,
  MountDetail,
  MountSummary,
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
    throw new Error(payload?.error?.message || `Request failed: ${response.status}`);
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

export function useSource(sourceName: string) {
  return useQuery({
    queryKey: ["source", sourceName],
    queryFn: () => request<SourceDetail>(`/api/sources/${encodeURIComponent(sourceName)}`),
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
      const payload = await request<{ items: MountSummary[] }>(`/api/mounts${params.toString() ? `?${params.toString()}` : ""}`);
      return payload.items;
    },
  });
}

export function useMount(mountId: string) {
  return useQuery({
    queryKey: ["mount", mountId],
    queryFn: () => request<MountDetail>(`/api/mounts/${encodeURIComponent(mountId)}`),
    enabled: Boolean(mountId),
  });
}

export function useRuns(limit = 24) {
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
    queryFn: () => request<RunRecord>(`/api/runs/${encodeURIComponent(runId)}`),
    enabled: Boolean(runId),
  });
}

function invalidateCore(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["app-summary"] }),
    queryClient.invalidateQueries({ queryKey: ["sources"] }),
    queryClient.invalidateQueries({ queryKey: ["mounts"] }),
    queryClient.invalidateQueries({ queryKey: ["runs"] }),
  ]);
}

export function useReloadApp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      request<ReloadResponse>("/api/reload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => invalidateCore(queryClient),
  });
}

export function useSyncAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      request<SyncResponse>("/api/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }),
    onSuccess: async () => invalidateCore(queryClient),
  });
}
