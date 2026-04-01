export function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function joinPath(parts: string[]) {
  return parts.length ? parts.join(" / ") : "-";
}

export function summarizeSurfaceMap(surfaces: Record<string, boolean>) {
  return Object.entries(surfaces)
    .filter(([, enabled]) => enabled)
    .map(([name]) => name);
}
