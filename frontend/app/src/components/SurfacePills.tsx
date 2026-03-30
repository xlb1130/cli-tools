type SurfacePillsProps = {
  surfaces: Record<string, boolean> | string[];
};

export function SurfacePills({ surfaces }: SurfacePillsProps) {
  const items = Array.isArray(surfaces)
    ? surfaces.map((surface) => [surface, true] as const)
    : Object.entries(surfaces);

  return (
    <div className="pill-row">
      {items.map(([surface, enabled]) => (
        <span key={surface} className={enabled ? "pill pill-on" : "pill pill-off"}>
          <span className="pill-dot" aria-hidden="true" />
          <span>{surface}</span>
        </span>
      ))}
    </div>
  );
}
