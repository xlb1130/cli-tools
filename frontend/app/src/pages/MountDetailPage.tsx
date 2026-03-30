import { FormEvent, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useExplainMount, useInvokeMount, useMount, useMountHelp, useRuns } from "../lib/api";

type SchemaField = {
  name: string;
  type: string;
  title: string;
  required: boolean;
};

export function MountDetailPage() {
  const { mountId = "" } = useParams();
  const mountQuery = useMount(mountId);
  const helpQuery = useMountHelp(mountId);
  const explainMutation = useExplainMount(mountId);
  const invokeMutation = useInvokeMount(mountId);
  const runsQuery = useRuns(20);
  const [inputText, setInputText] = useState('{\n  "text": "hello"\n}');
  const [localError, setLocalError] = useState<string | null>(null);

  if (mountQuery.isLoading || helpQuery.isLoading) {
    return <LoadingState label="加载 mount 详情" />;
  }

  if (mountQuery.isError) {
    return <ErrorState title="Mount 详情加载失败" error={mountQuery.error} />;
  }

  const mount = mountQuery.data;
  const help = helpQuery.data;

  if (!mount) {
    return <ErrorState title="Mount 不存在" error={new Error(mountId)} />;
  }

  const schema = ((mount.operation as { input_schema?: Record<string, unknown> }).input_schema ?? {}) as Record<string, unknown>;
  const schemaFields = getSchemaFields(schema);
  const currentInput = parseInputObject(inputText, true);
  const recentRuns = (runsQuery.data ?? []).filter((item) => item.mount_id === mountId).slice(0, 5);
  const invokeExample = `cts invoke ${mount.mount_id} --input-json '${inputText.replace(/\n/g, " ")}' --format json`;

  const handleExplain = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    try {
      await explainMutation.mutateAsync(parseInputObject(inputText));
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Explain 输入解析失败。");
    }
  };

  const handleInvoke = async (dryRun = false) => {
    setLocalError(null);
    try {
      await invokeMutation.mutateAsync({ input: parseInputObject(inputText), dryRun });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Invoke 输入解析失败。");
    }
  };

  const schemaForm = useMemo(() => {
    if (!schemaFields.length) {
      return null;
    }
    return (
      <div className="form-grid">
        {schemaFields.map((field) => {
          const value = currentInput[field.name];
          if (field.type === "boolean") {
            return (
              <label key={field.name}>
                <span className="field-label">
                  {field.title}
                  {field.required ? " *" : ""}
                </span>
                <select
                  className="field"
                  value={typeof value === "boolean" ? String(value) : ""}
                  onChange={(event) => handleSchemaFieldChange(field, event.target.value === "true", inputText, setInputText, setLocalError)}
                >
                  <option value="">Unset</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </label>
            );
          }

          return (
            <label key={field.name}>
              <span className="field-label">
                {field.title}
                {field.required ? " *" : ""}
              </span>
              <input
                className="field"
                value={value == null ? "" : String(value)}
                inputMode={field.type === "number" || field.type === "integer" ? "numeric" : undefined}
                onChange={(event) => handleSchemaFieldChange(field, event.target.value, inputText, setInputText, setLocalError)}
              />
            </label>
          );
        })}
      </div>
    );
  }, [currentInput, inputText, schemaFields]);

  return (
    <div className="page-stack">
      <section className="detail-hero">
        <div>
          <p className="eyebrow">Mount Detail</p>
          <h2>{mount.mount_id}</h2>
          <p className="hero-copy">{mount.summary}</p>
        </div>
        <div className="detail-hero-side">
          <div className="hero-summary-grid hero-summary-grid-single">
            <article className="hero-summary-card">
              <span>Stable Name</span>
              <strong>{mount.stable_name}</strong>
            </article>
            <article className="hero-summary-card">
              <span>Operation</span>
              <strong>{mount.operation_id}</strong>
            </article>
          </div>
          <RiskBadge risk={mount.risk} />
          <SurfacePills surfaces={mount.supported_surfaces} />
        </div>
      </section>

      <div className="content-grid two-col">
        <Panel title="Human Path" subtitle="人类 CLI 入口" kicker="Operator Entry">
          <p className="code-line">cts {mount.command_path.join(" ")}</p>
          <CopyButton value={`cts ${mount.command_path.join(" ")}`} />
        </Panel>

        <Panel title="Machine Contract" subtitle="给 AI 和自动化系统的稳定入口" kicker="Contract">
          <dl className="detail-list">
            <div>
              <dt>mount.id</dt>
              <dd>{mount.mount_id}</dd>
            </div>
            <div>
              <dt>stable_name</dt>
              <dd>{mount.stable_name}</dd>
            </div>
            <div>
              <dt>source</dt>
              <dd>{mount.source}</dd>
            </div>
            <div>
              <dt>operation</dt>
              <dd>{mount.operation_id}</dd>
            </div>
          </dl>
        </Panel>
      </div>

      <div className="content-grid two-col">
        <Panel title="Machine Examples" subtitle="给自动化和 AI 的推荐入口" kicker="Usage">
          <div className="stack">
            <div>
              <p className="eyebrow">Explain</p>
              <p className="code-line">cts explain {mount.mount_id} --input-json '{`{"text":"hello"}`}' --format json</p>
            </div>
            <div>
              <p className="eyebrow">Invoke</p>
              <p className="code-line">{invokeExample}</p>
            </div>
          </div>
        </Panel>

        <Panel title="Explain & Invoke" subtitle="自动表单 + 原始 JSON 输入都可用" kicker="Preview">
          <form className="explain-form" onSubmit={handleExplain}>
            {schemaForm}
            <label className="field-label" htmlFor="explain-input">
              JSON Input
            </label>
            <textarea
              id="explain-input"
              className="json-input"
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              rows={8}
              spellCheck={false}
            />
            {localError ? <div className="inline-error">{localError}</div> : null}
            {explainMutation.isError ? (
              <div className="inline-error">
                {explainMutation.error instanceof Error ? explainMutation.error.message : "Explain 请求失败。"}
              </div>
            ) : null}
            {invokeMutation.isError ? (
              <div className="inline-error">
                {invokeMutation.error instanceof Error ? invokeMutation.error.message : "Invoke 请求失败。"}
              </div>
            ) : null}
            <div className="explain-actions">
              <button type="submit" className="primary-button" disabled={explainMutation.isPending}>
                {explainMutation.isPending ? "Explaining..." : "Explain"}
              </button>
              <button type="button" className="secondary-button" disabled={invokeMutation.isPending} onClick={() => void handleInvoke(true)}>
                {invokeMutation.isPending ? "Running..." : "Dry Run Invoke"}
              </button>
              <button type="button" className="primary-button" disabled={invokeMutation.isPending} onClick={() => void handleInvoke(false)}>
                {invokeMutation.isPending ? "Running..." : "Invoke"}
              </button>
              <CopyButton value={invokeExample} />
            </div>
          </form>
        </Panel>
      </div>

      {help ? (
        <Panel title="Dynamic Help" subtitle="后端动态编译出来的 help 视图" kicker="Compiled Help">
          <p className="code-line">{help.usage}</p>
          <pre className="help-block">{help.description}</pre>
          <pre className="help-block secondary">{help.epilog}</pre>
        </Panel>
      ) : null}

      {explainMutation.data ? (
        <Panel title="Explain Result" subtitle="结构化计划结果，可用于前端、AI 或调试" kicker="Plan Output">
          <JsonViewer data={explainMutation.data} />
        </Panel>
      ) : null}

      {invokeMutation.data ? (
        <Panel title="Invoke Result" subtitle="HTTP 执行返回与 run_id" kicker="Execution">
          <JsonViewer data={invokeMutation.data} />
        </Panel>
      ) : null}

      <Panel title="Recent Runs" subtitle="当前 mount 的最近执行记录" kicker="History">
        {runsQuery.isLoading ? (
          <LoadingState label="加载 run 历史" compact />
        ) : recentRuns.length ? (
          <div className="table-like">
            {recentRuns.map((run) => (
              <article key={run.run_id} className="row-card">
                <div>
                  <strong>{run.mode}</strong>
                  <p>{run.summary || run.operation_id || run.run_id}</p>
                  <p className="muted">{run.ts_start}</p>
                </div>
                <span className={run.ok ? "badge badge-safe" : "badge badge-danger"}>{run.ok ? "ok" : "failed"}</span>
              </article>
            ))}
          </div>
        ) : (
          <div className="state">还没有与当前 mount 相关的 run。</div>
        )}
      </Panel>

      <div className="content-grid two-col">
        <Panel title="Mount Payload" subtitle="挂载后的结构摘要" kicker="Raw View">
          <JsonViewer data={mount} />
        </Panel>

        <Panel title="Operation Schema" subtitle="原始 operation 描述与 schema" kicker="Schema">
          <JsonViewer data={mount.operation} />
        </Panel>
      </div>
    </div>
  );
}

function parseInputObject(inputText: string, permissive = false): Record<string, unknown> {
  if (!inputText.trim()) {
    return {};
  }
  try {
    const parsed = JSON.parse(inputText);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("输入必须是 JSON object。");
    }
    return parsed as Record<string, unknown>;
  } catch (error) {
    if (permissive) {
      return {};
    }
    throw error;
  }
}

function getSchemaFields(schema: Record<string, unknown>): SchemaField[] {
  if (schema.type !== "object") {
    return [];
  }
  const properties = schema.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return [];
  }
  const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
  return Object.entries(properties)
    .map(([name, descriptor]) => {
      const item = descriptor as { type?: string; title?: string };
      return {
        name,
        type: item.type || "string",
        title: item.title || name,
        required: required.has(name),
      };
    })
    .filter((field) => ["string", "number", "integer", "boolean"].includes(field.type));
}

function handleSchemaFieldChange(
  field: SchemaField,
  rawValue: string | boolean,
  inputText: string,
  setInputText: (value: string) => void,
  setLocalError: (value: string | null) => void,
) {
  try {
    const nextValue =
      field.type === "boolean"
        ? Boolean(rawValue)
        : field.type === "number" || field.type === "integer"
          ? rawValue === ""
            ? null
            : Number(rawValue)
          : rawValue;
    const current = parseInputObject(inputText, true);
    const next = { ...current };
    if (nextValue === null || nextValue === "") {
      delete next[field.name];
    } else {
      next[field.name] = nextValue;
    }
    setInputText(JSON.stringify(next, null, 2));
    setLocalError(null);
  } catch (error) {
    setLocalError(error instanceof Error ? error.message : "字段更新失败。");
  }
}
