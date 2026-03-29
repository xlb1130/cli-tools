type RiskBadgeProps = {
  risk: string;
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  const tone = risk === "write" || risk === "destructive" ? "danger" : risk === "read" ? "safe" : "warn";
  return <span className={`badge badge-${tone}`}>{risk}</span>;
}
