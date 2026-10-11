/** Client-side pagination helper for explorer tables. */
import { useEffect, useState } from "react";
import { Pagination } from "./common";

export function usePaged<T>(rows: readonly T[], size = 50, resetKey = ""): { page: number; setPage: (p: number) => void; slice: T[]; pageCount: number; pager: React.ReactNode } {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [resetKey]);
  const pageCount = Math.max(1, Math.ceil(rows.length / size));
  const p = Math.min(page, pageCount);
  const slice = rows.slice((p - 1) * size, p * size);
  const pager = rows.length > size ? <Pagination page={p} pageCount={pageCount} total={rows.length} size={size} onPage={setPage} /> : null;
  return { page: p, setPage, slice, pageCount, pager };
}

/** Horizontally scrollable, keyboard-focusable table wrapper. */
export function TableRegion({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="card relative overflow-x-auto" role="region" aria-label={label} tabIndex={0} data-testid={testId}>
      {children}
    </div>
  );
}
