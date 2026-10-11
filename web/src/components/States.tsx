
export function LoadingSkeleton({ label = "Loading data", lines = 4 }: { label?: string; lines?: number }) {
  return (
    <div role="status" aria-live="polite" className="py-4">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="animate-pulse space-y-3">
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className="h-4 rounded bg-line" style={{ width: `${92 - i * 11}%` }} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ error, retry, what = "data" }: { error: Error; retry?: () => void; what?: string }) {
  return (
    <div role="alert" className="card border-danger/40 bg-danger-soft p-4">
      <p className="font-semibold text-danger">Could not load {what}.</p>
      <p className="mt-1 text-sm text-ink">{error.message}</p>
      {retry ? (
        <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={retry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="card p-6 text-center">
      <p className="font-semibold">{title}</p>
      {children ? <div className="mt-2 text-sm text-ink-2">{children}</div> : null}
    </div>
  );
}

/** Clearly labelled placeholder for destinations implemented in later PRs (never a working tool). */
