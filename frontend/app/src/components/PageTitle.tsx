import { Icon } from "./Icon";
import type { IconName } from "./Icon";

type PageTitleProps = {
  icon: IconName;
  eyebrow: string;
  title: string;
  description?: string;
  compact?: boolean;
};

export function PageTitle({ icon, eyebrow, title, description, compact = false }: PageTitleProps) {
  return (
    <div className={compact ? "title-block title-block-compact" : "title-block"}>
      <div className="title-row">
        <span className="page-icon" aria-hidden="true">
          <Icon name={icon} size={18} />
        </span>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      {description ? <p className="hero-copy">{description}</p> : null}
    </div>
  );
}
