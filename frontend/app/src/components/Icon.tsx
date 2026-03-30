export type IconName =
  | "dashboard"
  | "governance"
  | "sources"
  | "aliases"
  | "auth"
  | "drift"
  | "logs"
  | "extensions"
  | "mounts"
  | "catalog"
  | "runs";

type IconProps = {
  name: IconName;
  size?: number;
  decorative?: boolean;
  className?: string;
};

export function Icon({ name, size = 18, decorative = true, className = "icon" }: IconProps) {
  const commonProps = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden={decorative}
      role={decorative ? undefined : "img"}
    >
      {name === "dashboard" ? (
        <>
          <rect x="3.5" y="3.5" width="7" height="7" rx="2" {...commonProps} />
          <rect x="13.5" y="3.5" width="7" height="4.5" rx="2" {...commonProps} />
          <rect x="13.5" y="10.5" width="7" height="10" rx="2" {...commonProps} />
          <rect x="3.5" y="13" width="7" height="7.5" rx="2" {...commonProps} />
        </>
      ) : null}
      {name === "governance" ? (
        <>
          <path d="M12 3.5 18.5 6v5.1c0 4.1-2.5 7.8-6.5 9.4-4-1.6-6.5-5.3-6.5-9.4V6L12 3.5Z" {...commonProps} />
          <path d="m9.4 12 1.7 1.7 3.7-4.2" {...commonProps} />
        </>
      ) : null}
      {name === "sources" ? (
        <>
          <ellipse cx="12" cy="6" rx="6.5" ry="2.5" {...commonProps} />
          <path d="M5.5 6v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5V6" {...commonProps} />
          <path d="M5.5 11v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-5" {...commonProps} />
        </>
      ) : null}
      {name === "aliases" ? (
        <>
          <path d="M9 7H5.5A2.5 2.5 0 0 0 3 9.5 2.5 2.5 0 0 0 5.5 12H9" {...commonProps} />
          <path d="M15 12h3.5A2.5 2.5 0 0 1 21 14.5 2.5 2.5 0 0 1 18.5 17H15" {...commonProps} />
          <path d="M8 12h8" {...commonProps} />
        </>
      ) : null}
      {name === "auth" ? (
        <>
          <rect x="4" y="11" width="16" height="9" rx="2.5" {...commonProps} />
          <path d="M8 11V8a4 4 0 1 1 8 0v3" {...commonProps} />
          <circle cx="12" cy="15.5" r="1.1" fill="currentColor" stroke="none" />
        </>
      ) : null}
      {name === "drift" ? (
        <>
          <path d="M5 16c1.7-4.2 4.4-7 8-8.5" {...commonProps} />
          <path d="M13.5 7.5h5v5" {...commonProps} />
          <path d="M19 18c-1.9-2-4-3-6.5-3S7.8 16 5 19" {...commonProps} />
        </>
      ) : null}
      {name === "logs" ? (
        <>
          <rect x="4" y="4" width="16" height="16" rx="3" {...commonProps} />
          <path d="M8 9h8" {...commonProps} />
          <path d="M8 13h8" {...commonProps} />
          <path d="M8 17h5" {...commonProps} />
        </>
      ) : null}
      {name === "extensions" ? (
        <path d="M8.5 5.5a2.5 2.5 0 1 1 5 0V8h2.5a2.5 2.5 0 1 1 0 5H13.5v2.5a2.5 2.5 0 1 1-5 0V13H6a2.5 2.5 0 1 1 0-5h2.5V5.5Z" {...commonProps} />
      ) : null}
      {name === "mounts" ? (
        <>
          <path d="M12 3.5 5 7.5v9l7 4 7-4v-9l-7-4Z" {...commonProps} />
          <path d="M5 7.5 12 12l7-4.5" {...commonProps} />
          <path d="M12 12v8.5" {...commonProps} />
        </>
      ) : null}
      {name === "catalog" ? (
        <>
          <rect x="4" y="5" width="7" height="14" rx="2" {...commonProps} />
          <rect x="13" y="5" width="7" height="6" rx="2" {...commonProps} />
          <rect x="13" y="13" width="7" height="6" rx="2" {...commonProps} />
        </>
      ) : null}
      {name === "runs" ? (
        <>
          <circle cx="12" cy="12" r="8.5" {...commonProps} />
          <path d="m10 8.5 5 3.5-5 3.5v-7Z" fill="currentColor" stroke="none" />
        </>
      ) : null}
    </svg>
  );
}
