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

export type ExtensionsSummary = {
  plugin_count: number;
  provider_count: number;
  plugin_provider_count: number;
  core_provider_count: number;
  hook_count: number;
  enabled_hook_count: number;
  provider_conflict_count: number;
  hooks_by_event: Array<{
    event: string;
    count: number;
  }>;
  recent_event_count: number;
};

export type PluginProviderRegistration = {
  provider_type: string;
  active: boolean;
  class_name: string;
  module: string;
};

export type HookBinding = {
  id: string;
  index: number;
  event: string;
  plugin: string;
  handler: string;
  enabled: boolean;
  priority: number;
  fail_mode: string;
  when: Record<string, unknown>;
  config: Record<string, unknown>;
  plugin_loaded: boolean;
  handler_available: boolean;
};

export type HookContract = {
  event: string;
  stage: string;
  description: string;
  payload_fields: Array<{
    name: string;
    type: string;
    required: boolean;
  }>;
  may_mutate: string[];
  sample_payload: Record<string, unknown>;
  sample_context: {
    mount_required: boolean;
    source_required: boolean;
  };
  simulation: {
    risk_level: string;
    provider_calls_blocked: boolean;
    plugin_side_effects_possible: boolean;
    notes: string[];
  };
};

export type HookMatchCriterion = {
  key: string;
  source: string;
  expected: unknown;
  actual: unknown;
  matched: boolean;
};

export type HookExplainItem = {
  id: string;
  index: number;
  event: string;
  plugin: string;
  handler: string;
  priority: number;
  fail_mode: string;
  plugin_loaded: boolean;
  handler_available: boolean;
  matched: boolean;
  criteria: HookMatchCriterion[];
  when: Record<string, unknown>;
  status?: string;
  mutated?: boolean;
  error?: Record<string, unknown>;
  result_payload?: Record<string, unknown>;
};

export type PluginDetail = {
  name: string;
  enabled: boolean;
  module: string | null;
  path: string | null;
  resolved_path: string | null;
  factory: string | null;
  config: Record<string, unknown>;
  origin_file: string | null;
  provider_types: PluginProviderRegistration[];
  hook_handlers: string[];
  bound_hooks: HookBinding[];
};

export type ProviderInventoryItem = {
  provider_type: string;
  owner_type: "core" | "plugin";
  owner_name: string;
  class_name: string;
  module: string;
  source_names: string[];
  source_count: number;
  mount_ids: string[];
  mount_count: number;
  conflicts: Array<Record<string, unknown>>;
  conflict_count: number;
};

export type ExtensionEvent = {
  ts: string;
  level: string;
  event: string;
  run_id: string | null;
  trace_id: string | null;
  surface: string | null;
  profile: string | null;
  source: string | null;
  mount_id: string | null;
  operation_id: string | null;
  message: string | null;
  data: Record<string, unknown>;
};

export type ExtensionEventsResponse = {
  items: ExtensionEvent[];
  filters: Record<string, string | number | null>;
  next_before_ts: string | null;
};

export type HookDispatchExplainResponse = {
  ok: boolean;
  action: "hook_explain";
  event: string;
  contract: HookContract | null;
  context: Record<string, unknown>;
  payload: Record<string, unknown>;
  hooks: HookExplainItem[];
};

export type HookDispatchSimulateResponse = {
  ok: boolean;
  action: "hook_simulate";
  event: string;
  context: Record<string, unknown>;
  payload: Record<string, unknown>;
  hooks: HookExplainItem[];
  execute_handlers: boolean;
  simulation: {
    risk_level?: string;
    provider_calls_blocked: boolean;
    plugin_side_effects_possible?: boolean;
    notes?: string[];
    mode: string;
    execute_handlers: boolean;
    mount_execution_blocked: boolean;
  };
  steps: HookExplainItem[];
  halted: boolean;
  final_payload: Record<string, unknown>;
};

export type SourceHealth = {
  source: string;
  ok: boolean;
  provider_type: string;
  operation_count: number;
  executable?: string;
  base_url?: string;
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
  health?: SourceHealth;
};

export type SourceDetail = SourceSummary & {
  compiled_operation_count: number;
  operation_ids: string[];
  operations: unknown[];
};

export type MountSummary = {
  id: string;
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

export type MountHelp = {
  mount_id: string;
  stable_name: string;
  summary: string;
  description: string;
  epilog: string;
  usage: string;
  risk: string;
  supported_surfaces: string[];
  schema_provenance: Record<string, unknown> | null;
};

export type ExplainResponse = {
  ok: boolean;
  mount_id: string;
  stable_name: string;
  source: string;
  provider_type: string;
  operation_id: string;
  risk: string;
  plan: Record<string, unknown>;
  run_id: string;
  trace_id: string | null;
};

export type CatalogResponse = {
  mounts: MountSummary[];
  conflicts: Array<Record<string, unknown>>;
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

export type SyncItem = {
  source: string;
  provider_type: string;
  operation_count: number;
  ok: boolean;
  error?: string;
};

export type ReloadResponse = {
  ok: boolean;
  action: "reload";
  summary: AppSummary;
};

export type SyncResponse = {
  ok: boolean;
  action: "sync";
  items: SyncItem[];
};
