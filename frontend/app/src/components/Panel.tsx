import { PropsWithChildren, ReactNode } from "react";

type PanelProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  kicker?: string;
}>;

export function Panel({ title, subtitle, actions, kicker, children }: PanelProps) {
  return (
    <section className="panel">
      <div className="panel-accent" aria-hidden="true" />
      <div className="panel-header">
        <div>
          {kicker ? <p className="panel-kicker">{kicker}</p> : null}
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
