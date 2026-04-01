import { Panel } from "../components/ui";

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="page">
      <Panel title={title} eyebrow="Coming Next">
        <div className="placeholder-block">
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
      </Panel>
    </div>
  );
}
