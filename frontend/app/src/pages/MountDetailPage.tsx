import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";

import { CopyButton } from "../components/CopyButton";
import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { RiskBadge } from "../components/RiskBadge";
import { SurfacePills } from "../components/SurfacePills";
import { useExplainMount, useMount, useMountHelp } from "../lib/api";

export function MountDetailPage() {
  const { mountId = "" } = useParams();
  const mountQuery = useMount(mountId);
  const helpQuery = useMountHelp(mountId);
  const explainMutation = useExplainMount(mountId);
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

  const invokeExample = `cts invoke ${mount.mount_id} --input-json '${inputText.replace(/\n/g, " ")}' --format json`;

  const handleExplain = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    try {
      const parsed = inputText.trim() ? JSON.parse(inputText) : {};
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Explain 输入必须是 JSON object。");
      }
      await explainMutation.mutateAsync(parsed as Record<string, unknown>);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Explain 输入解析失败。");
    }
  };

  return (
    <div className="page-stack">
      <section className="detail-hero">
        <div>
          <p className="eyebrow">Mount Detail</p>
          <h2>{mount.mount_id}</h2>
          <p className="hero-copy">{mount.summary}</p>
        </div>
        <div className="detail-hero-side">
          <RiskBadge risk={mount.risk} />
          <SurfacePills surfaces={mount.supported_surfaces} />
        </div>
      </section>

      <div className="content-grid two-col">
        <Panel title="Human Path" subtitle="人类 CLI 入口">
          <p className="code-line">cts {mount.command_path.join(" ")}</p>
          <CopyButton value={`cts ${mount.command_path.join(" ")}`} />
        </Panel>

        <Panel title="Machine Contract" subtitle="给 AI 和自动化系统的稳定入口">
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
        <Panel title="Machine Examples" subtitle="给自动化和 AI 的推荐入口">
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

        <Panel title="Explain From UI" subtitle="通过 HTTP API 预演 provider 请求，不直接执行操作">
          <form className="explain-form" onSubmit={handleExplain}>
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
            <div className="explain-actions">
              <button type="submit" className="primary-button" disabled={explainMutation.isPending}>
                {explainMutation.isPending ? "Explaining..." : "Explain"}
              </button>
              <CopyButton value={invokeExample} />
            </div>
          </form>
        </Panel>
      </div>

      {help ? (
        <Panel title="Dynamic Help" subtitle="后端动态编译出来的 help 视图">
          <p className="code-line">{help.usage}</p>
          <pre className="help-block">{help.description}</pre>
          <pre className="help-block secondary">{help.epilog}</pre>
        </Panel>
      ) : null}

      {explainMutation.data ? (
        <Panel title="Explain Result" subtitle="结构化计划结果，可用于前端、AI 或调试">
          <JsonViewer data={explainMutation.data} />
        </Panel>
      ) : null}

      <div className="content-grid two-col">
        <Panel title="Mount Payload" subtitle="挂载后的结构摘要">
          <JsonViewer data={mount} />
        </Panel>

        <Panel title="Operation Schema" subtitle="原始 operation 描述与 schema">
          <JsonViewer data={mount.operation} />
        </Panel>
      </div>
    </div>
  );
}
