import { ErrorState } from "../components/ErrorState";
import { JsonViewer } from "../components/JsonViewer";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { useCatalog } from "../lib/api";

export function CatalogPage() {
  const catalogQuery = useCatalog();

  if (catalogQuery.isLoading) {
    return <LoadingState label="加载 catalog" />;
  }

  if (catalogQuery.isError) {
    return <ErrorState title="Catalog 加载失败" error={catalogQuery.error} />;
  }

  return (
    <div className="page-stack">
      <Panel title="Catalog Export" subtitle="机器视角的 capability catalog">
        <JsonViewer data={catalogQuery.data} />
      </Panel>
    </div>
  );
}
