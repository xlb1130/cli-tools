import { Link } from "react-router-dom";
import type { PropsWithChildren, ReactNode } from "react";

export function Panel({
  title,
  eyebrow,
  aside,
  children,
}: PropsWithChildren<{ title: string; eyebrow?: string; aside?: ReactNode }>) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        {aside ? <div className="panel-aside">{aside}</div> : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  meta,
}: {
  label: string;
  value: string;
  meta?: string;
}) {
  return (
    <article className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {meta ? <small>{meta}</small> : null}
    </article>
  );
}

export function SurfaceStack({ items }: { items: string[] }) {
  if (!items.length) return <span className="muted">none</span>;
  return (
    <div className="surface-stack">
      {items.map((item) => (
        <span key={item} className="surface-chip">
          {item}
        </span>
      ))}
    </div>
  );
}

export function StatusPill({ tone, children }: PropsWithChildren<{ tone: "good" | "warn" | "bad" | "neutral" }>) {
  return <span className={`status-pill status-${tone}`}>{children}</span>;
}

export function MetricLine({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function RouteCard({
  to,
  title,
  description,
  meta,
}: {
  to: string;
  title: string;
  description: string;
  meta?: ReactNode;
}) {
  return (
    <Link className="route-card" to={to}>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {meta ? <div className="route-card-meta">{meta}</div> : null}
    </Link>
  );
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="state-block">
      <div className="spinner" />
      <div>
        <strong>{label}</strong>
        <p>正在从本地 API 拉取最新视图。</p>
      </div>
    </div>
  );
}

export function ErrorBlock({ title, error }: { title: string; error: unknown }) {
  return (
    <div className="state-block error">
      <div>
        <strong>{title}</strong>
        <p>{error instanceof Error ? error.message : "Unknown error"}</p>
      </div>
    </div>
  );
}
