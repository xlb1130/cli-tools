import { FormEvent, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PageTitle } from "../components/PageTitle";
import { useAddAlias, useAliases, useRemoveAlias } from "../lib/api";
import { formatList } from "../lib/format";

export function AliasPage() {
  const aliasesQuery = useAliases();
  const addAliasMutation = useAddAlias();
  const removeAliasMutation = useRemoveAlias();
  const [formState, setFormState] = useState({ aliasFrom: "", aliasTo: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (aliasesQuery.isLoading) {
    return <LoadingState label="加载 aliases" />;
  }

  if (aliasesQuery.isError) {
    return <ErrorState title="Alias 页面加载失败" error={aliasesQuery.error} />;
  }

  const aliases = aliasesQuery.data ?? [];

  const handleAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setErrorMessage(null);
    try {
      const result = await addAliasMutation.mutateAsync(formState);
      setMessage(`Alias 已创建，指向 mount ${String(result.mount_id || "-")}。`);
      setFormState({ aliasFrom: "", aliasTo: "" });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Alias 创建失败");
    }
  };

  const handleRemove = async (aliasFrom: string[]) => {
    setMessage(null);
    setErrorMessage(null);
    try {
      await removeAliasMutation.mutateAsync(aliasFrom.join(" "));
      setMessage(`Alias ${aliasFrom.join(" ")} 已删除。`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Alias 删除失败");
    }
  };

  return (
    <div className="page-stack">
      <section className="hero">
        <div>
          <PageTitle
            icon="aliases"
            eyebrow="Aliases"
            title="Alias 管理界面"
            description="这里对应 `cts alias list/add/remove`，适合给常用 mount 做更好记的命令入口。"
          />
          {message ? <div className="inline-note">{message}</div> : null}
          {errorMessage ? <div className="inline-error">{errorMessage}</div> : null}
        </div>
      </section>

      <div className="content-grid two-col">
        <Panel title="Create Alias" subtitle="from 必须是新命令路径，to 必须指向现有 mount 命令路径">
          <form className="form-grid" onSubmit={handleAdd}>
            <label>
              <span className="field-label">Alias From</span>
              <input className="field" value={formState.aliasFrom} onChange={(event) => setFormState((current) => ({ ...current, aliasFrom: event.target.value }))} placeholder="jira issue get" />
            </label>
            <label>
              <span className="field-label">Alias To</span>
              <input className="field" value={formState.aliasTo} onChange={(event) => setFormState((current) => ({ ...current, aliasTo: event.target.value }))} placeholder="ops jira issue get" />
            </label>
            <div className="inline-actions">
              <button type="submit" className="primary-button" disabled={addAliasMutation.isPending}>
                {addAliasMutation.isPending ? "Creating..." : "Create Alias"}
              </button>
            </div>
          </form>
        </Panel>

        <Panel title="Alias Inventory" subtitle="现有 alias 与目标路径">
          {aliases.length ? (
            <div className="table-like">
              {aliases.map((alias, index) => (
                <article key={`${alias.from.join(" ")}:${index}`} className="row-card">
                  <div>
                    <strong>{formatList(alias.from)}</strong>
                    <p>{formatList(alias.to)}</p>
                  </div>
                  <button type="button" className="secondary-button" onClick={() => handleRemove(alias.from)} disabled={removeAliasMutation.isPending}>
                    Remove
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="还没有 alias" body="给高频 mount 建一个更短的入口，会让 CLI 和 UI 都更顺手。" />
          )}
        </Panel>
      </div>
    </div>
  );
}
