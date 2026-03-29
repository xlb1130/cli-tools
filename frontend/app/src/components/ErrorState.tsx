type ErrorStateProps = {
  title: string;
  error: unknown;
  compact?: boolean;
};

export function ErrorState({ title, error, compact = false }: ErrorStateProps) {
  const message = error instanceof Error ? error.message : "Unknown error";

  return (
    <div className={compact ? "state state-compact state-error" : "state state-error"}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}
