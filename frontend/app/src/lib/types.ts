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

export type ReliabilityStatusPayload = {
  defaults: {
    timeout_seconds: number;
    retry?: {
      max_attempts: number;
      backoff?: {
        strategy?: string;
        base_delay_ms?: number;
      };
    };
    concurrency?: {
      max_inflight_per_source: number;
      max_inflight_global: number;
      queue_timeout_seconds: number;
    };
  } | null;
  configured_budget_count: number;
  configured_budgets: Record<
    string,
    {
      requests_per_second?: number | null;
      requests_per_minute?: number | null;
      requests_per_hour?: number | null;
      max_inflight?: number | null;
    }
  >;
  status: {
    rate_limits: Record<
      string,
      {
        name: string;
        tokens: number;
        requests_in_window: number;
        total_requests: number;
        total_limited: number;
        last_limited_at?: number | null;
        budget: Record<string, unknown>;
      }
    >;
    concurrency: Record<
      string,
      {
        source?: string;
        current_concurrent?: number;
        max_concurrent?: number;
        total_acquired?: number;
        total_timeouts?: number;
        exists?: boolean;
      }
    >;
    idempotency: {
      total_records: number;
      pending: number;
      completed: number;
      failed: number;
      cache_dir: string;
    };
  };
};

export type AuthSummary = {
  profile_count: number;
  state_counts: Record<string, number>;
  active_count: number;
  login_required_count: number;
  expired_count: number;
};

export type AuthProfileStatus = {
  name: string;
  configured: boolean;
  state: string;
  reason?: string | null;
  profile: Record<string, unknown> | null;
  session: Record<string, unknown> | null;
  source_names: string[];
  source_count: number;
  source_types: string[];
  resolved_credentials: Record<string, unknown> | null;
  status?: Record<string, unknown>;
};

export type AuthInventoryResponse = {
  items: AuthProfileStatus[];
  summary: AuthSummary;
};

export type AuthActionResponse = {
  ok: boolean;
  action: "auth_login" | "auth_logout" | "auth_refresh";
  profile: AuthProfileStatus;
};

export type ConfigMutationSummary = {
  mount_count: number;
  source_count: number;
};

export type SourceMutationResponse = {
  ok: boolean;
  action: "source_add" | "source_remove";
  source_name: string;
  file: string;
  summary?: ConfigMutationSummary & Record<string, unknown>;
  [key: string]: unknown;
};

export type MountMutationResponse = {
  ok: boolean;
  action: "mount_add" | "mount_remove";
  mount_id: string;
  file: string;
  summary?: ConfigMutationSummary & Record<string, unknown>;
  [key: string]: unknown;
};

export type AliasRecord = {
  from: string[];
  to: string[];
};

export type AliasListResponse = {
  items: AliasRecord[];
};

export type AliasMutationResponse = {
  ok: boolean;
  action: "alias_add" | "alias_remove";
  file: string;
  alias: AliasRecord;
  summary?: ConfigMutationSummary & Record<string, unknown>;
  [key: string]: unknown;
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

export type DriftState = {
  source?: string;
  mount_id?: string;
  provider_type?: string | null;
  drift?: Record<string, unknown>;
  status?: string;
  report_generated_at?: string;
  affected_mount_ids?: string[];
  affected_aliases?: string[][];
  blocked_mount_ids?: string[];
  accepted_mount_ids?: string[];
  affected_mount_count?: number;
  blocked_mount_count?: number;
  accepted_mount_count?: number;
  accepted_by_policy?: boolean;
  blocked?: boolean;
  action?: string;
  severity?: string;
  reasons?: string[];
  changes?: Array<Record<string, unknown>>;
  aliases?: string[][];
  supported_surfaces?: string[];
  report_path?: string;
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
    status?: Record<string, unknown>;
  };
  discovery_state?: Record<string, unknown>;
  drift_state?: DriftState | null;
  health?: SourceHealth;
};

export type SourceDetail = SourceSummary & {
  compiled_operation_count: number;
  operation_ids: string[];
  operations: unknown[];
};

export type SourceTestResponse = SourceHealth & {
  origin_file?: string | null;
  discovery_state?: Record<string, unknown>;
  auth?: Record<string, unknown>;
  provider_ok?: boolean;
  discovery?: Record<string, unknown>;
  discovery_report_path?: string;
  capability_snapshot_path?: string;
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

export type InvokeResponse = {
  ok: boolean;
  mount_id: string;
  stable_name: string;
  source: string;
  provider_type: string;
  operation_id: string;
  data?: unknown;
  text?: string | null;
  stderr?: string | null;
  status_code?: number | null;
  metadata?: Record<string, unknown>;
  reliability?: Record<string, unknown>;
  run_id: string;
  trace_id: string | null;
};

export type CatalogResponse = {
  mounts: MountSummary[];
  drift_summary?: DriftSummary | null;
  conflicts: Array<Record<string, unknown>>;
};

export type DriftSummary = {
  severity?: string;
  changed_sources?: number;
  [key: string]: unknown;
};

export type DriftReportItem = {
  source: string;
  provider_type?: string;
  operation_count?: number;
  ok?: boolean;
  error?: string;
  drift?: {
    changed?: boolean;
    severity?: string;
    changes?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  governance_state?: DriftState;
  [key: string]: unknown;
};

export type DriftReport = {
  version: number;
  kind: string;
  generated_at: string;
  requested_source?: string | null;
  profile?: string | null;
  config_files?: string[];
  items: DriftReportItem[];
  drift_summary?: DriftSummary | null;
  drift_governance?: {
    sources?: Record<string, DriftState>;
    mounts?: Record<string, DriftState>;
  };
  discovery_errors?: Record<string, unknown>;
  capability_snapshot_path?: string;
  report_path?: string;
  source_drift_state?: DriftState;
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

export type LogEvent = {
  ts: string;
  level: string;
  event: string;
  profile?: string | null;
  source?: string | null;
  mount_id?: string | null;
  operation_id?: string | null;
  provider_type?: string | null;
  run_id?: string | null;
  trace_id?: string | null;
  surface?: string | null;
  message?: string | null;
  data: Record<string, unknown>;
};

export type LogResponse = {
  items: LogEvent[];
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
