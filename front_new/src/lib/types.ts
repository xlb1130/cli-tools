export type AppSummary = {
  app: string;
  profile: string | null;
  config_files: string[];
  source_count: number;
  mount_count: number;
  surfaces: Record<string, boolean>;
  runtime_paths: {
    app_log: string;
    audit_log: string;
    history_db: string;
  };
  discovery_error_count: number;
};

export type SourceHealth = {
  source: string;
  ok: boolean;
  provider_type: string;
  operation_count: number;
};

export type DriftState = {
  severity?: string;
  blocked?: boolean;
  action?: string;
  reasons?: string[];
};

export type SourceSummary = {
  name: string;
  type: string;
  enabled: boolean;
  auth_ref: string | null;
  discovery_mode: string;
  operation_count: number;
  origin_file: string | null;
  expose_to_surfaces: string[];
  profile_scope: string[];
  auth?: {
    required: boolean;
    auth_ref: string | null;
    state: string;
    reason?: string;
  };
  drift_state?: DriftState | null;
  health?: SourceHealth;
};

export type SourceDetail = SourceSummary & {
  compiled_operation_count: number;
  operation_ids: string[];
  operations: unknown[];
};

export type MountSummary = {
  mount_id: string;
  source: string;
  provider_type: string;
  command_path: string[];
  aliases: string[][];
  stable_name: string;
  summary: string;
  risk: string;
  operation: string;
  supported_surfaces: string[];
};

export type MountDetail = {
  mount_id: string;
  command_path: string[];
  aliases: string[][];
  stable_name: string;
  source: string;
  provider_type: string;
  operation_id: string;
  risk: string;
  supported_surfaces: string[];
  summary: string;
  description: string | null;
  generated: boolean;
  generated_from: string | null;
  origin_file: string | null;
  source_origin_file: string | null;
  machine: Record<string, unknown>;
  help: Record<string, unknown>;
  params: Record<string, unknown>;
  operation: Record<string, unknown>;
};

export type RunRecord = {
  run_id: string;
  trace_id: string | null;
  ts_start: string;
  ts_end: string;
  surface: string;
  mode: string;
  ok: boolean;
  exit_code: number;
  profile: string | null;
  mount_id: string | null;
  stable_name: string | null;
  source: string | null;
  operation_id: string | null;
  provider_type: string | null;
  summary: string | null;
  error_type: string | null;
  error_code: string | null;
  metadata?: Record<string, unknown>;
};

export type ReloadResponse = {
  ok: boolean;
  action: "reload";
  summary: AppSummary;
};

export type SyncResponse = {
  ok: boolean;
  action: "sync";
  items: Array<{
    source: string;
    provider_type: string;
    operation_count: number;
    ok: boolean;
    error?: string;
  }>;
};
