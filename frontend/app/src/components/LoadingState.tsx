type LoadingStateProps = {
  label: string;
  compact?: boolean;
};

export function LoadingState({ label, compact = false }: LoadingStateProps) {
  return (
    <div className={compact ? "state state-compact loading-state" : "state loading-state"}>
      <span className="loading-spinner" aria-hidden="true" />
      <span>{label}...</span>
    </div>
  );
}
