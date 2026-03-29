type LoadingStateProps = {
  label: string;
  compact?: boolean;
};

export function LoadingState({ label, compact = false }: LoadingStateProps) {
  return <div className={compact ? "state state-compact" : "state"}>{label}...</div>;
}
