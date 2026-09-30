export function LoadingState() {
  return <p data-testid="loading">Loading…</p>;
}

export function ErrorState({ message }: { message: string }) {
  return <p data-testid="error">Error: {message}</p>;
}

export function EmptyState({ label }: { label: string }) {
  return <p data-testid="empty">No {label} yet.</p>;
}

export function NotAvailableState({ feature }: { feature: string }) {
  return (
    <p data-testid="not-available">
      {feature} is not available: Core has not published this endpoint yet.
    </p>
  );
}
