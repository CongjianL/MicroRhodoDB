/** Small presentational building blocks shared across pages. */
import { useEffect, useId, useRef, useState } from "react";
import { routeForQuery } from "../app/routes";
import { pushHash } from "../app/navigation";
import { fmtInt } from "../lib/format";

/* ---------------------------------------------------------------- PageTitle */

let focusOnNextTitle = false;
/** Called by the router on client-side route changes (not on first load). */
export function requestTitleFocus() {
  focusOnNextTitle = true;
}

export function PageTitle({ children, docTitle, eyebrow, lead }: {
  children: React.ReactNode;
  docTitle: string;
  eyebrow?: React.ReactNode;
  lead?: React.ReactNode;
}) {
  const h1 = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = docTitle;
  }, [docTitle]);
  useEffect(() => {
    if (focusOnNextTitle) {
      focusOnNextTitle = false;
      h1.current?.focus({ preventScroll: true });
    }
  }, []);
  return (
    <div className="mb-6">
      {eyebrow ? <div className="mb-2 text-sm text-ink-2">{eyebrow}</div> : null}
      <h1 ref={h1} tabIndex={-1} className="text-2xl outline-none sm:text-3xl">
        {children}
      </h1>
      {lead ? <div className="mt-2 max-w-3xl text-ink-2">{lead}</div> : null}
    </div>
  );
}

/* ---------------------------------------------------------------- Breadcrumbs */

export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3 text-sm">
      <ol className="flex flex-wrap items-center gap-1 text-ink-2">
        {items.map((it, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 ? <span aria-hidden="true">/</span> : null}
            {it.href ? <a href={it.href}>{it.label}</a> : <span aria-current="page" className="text-ink">{it.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/* ---------------------------------------------------------------- StatCard */

export function StatCard({ value, label, detail, href, testId }: {
  value: number;
  label: string;
  detail: React.ReactNode;
  href?: string;
  testId?: string;
}) {
  const body = (
    <>
      <div className="text-[1.75rem] font-semibold leading-tight tabular text-ink" data-testid={testId ? `${testId}-value` : undefined}>
        {fmtInt(value)}
      </div>
      <div className="mt-0.5 font-medium text-ink">{label}</div>
      <div className="mt-1.5 text-sm text-ink-2">{detail}</div>
    </>
  );
  return (
    <div className="card flex h-full flex-col p-4" data-testid={testId}>
      {href ? (
        <a href={href} className="block h-full text-inherit no-underline hover:no-underline">
          {body}
        </a>
      ) : (
        body
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- SearchBox */

export function SearchBox({ size = "lg", initial = "", label = "Search MicroRhodoDB" }: { size?: "lg" | "md"; initial?: string; label?: string }) {
  const id = useId();
  const [q, setQ] = useState(initial);
  return (
    <form
      role="search"
      aria-label={label}
      onSubmit={(e) => {
        e.preventDefault();
        pushHash(routeForQuery(q));
      }}
      className="w-full"
    >
      <label htmlFor={id} className="sr-only">{label}</label>
      <div className="flex gap-2">
        <input
          id={id}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="MRDB ID, UniProt accession, protein, organism, clade, PDB ID or motif"
          autoComplete="off"
          spellCheck={false}
          className={`field min-w-0 flex-1 ${size === "lg" ? "text-base" : ""}`}
          style={size === "lg" ? { minHeight: "3rem" } : undefined}
        />
        <button type="submit" className="btn btn-primary shrink-0" style={size === "lg" ? { minHeight: "3rem" } : undefined}>
          Search
        </button>
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------- Callout */

export function Callout({ tone = "info", title, children, testId }: { tone?: "info" | "warn"; title?: React.ReactNode; children: React.ReactNode; testId?: string }) {
  const cls = tone === "warn" ? "border-warn-line bg-warn-soft" : "border-[#b6d0ee] bg-accent-soft";
  return (
    <div className={`rounded-lg border p-4 text-sm ${cls}`} data-testid={testId} role={tone === "warn" ? "note" : undefined}>
      {title ? <p className={`font-semibold ${tone === "warn" ? "text-[#8a3c04]" : "text-accent-strong"}`}>{title}</p> : null}
      <div className={title ? "prose-links mt-1 text-ink" : "prose-links text-ink"}>{children}</div>
    </div>
  );
}

/* ---------------------------------------------------------------- Pagination */

export function Pagination({ page, pageCount, total, size, onPage }: {
  page: number;
  pageCount: number;
  total: number;
  size: number;
  onPage: (p: number) => void;
}) {
  const first = total === 0 ? 0 : (page - 1) * size + 1;
  const last = Math.min(total, page * size);
  const [jump, setJump] = useState(String(page));
  useEffect(() => setJump(String(page)), [page]);
  const jumpId = useId();
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="text-ink-2" aria-live="polite">
        Rows <span className="tabular text-ink">{fmtInt(first)}–{fmtInt(last)}</span> of <span className="tabular text-ink">{fmtInt(total)}</span>
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPage(1)} disabled={page <= 1} aria-label="First page">«</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPage(page - 1)} disabled={page <= 1}>Previous</button>
        <form
          className="flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            const n = Number(jump);
            if (Number.isInteger(n)) onPage(Math.min(Math.max(1, n), Math.max(1, pageCount)));
          }}
        >
          <label htmlFor={jumpId} className="text-ink-2">Page</label>
          <input id={jumpId} inputMode="numeric" className="field w-16 text-center tabular" style={{ minHeight: "2.25rem" }} value={jump} onChange={(e) => setJump(e.target.value.replace(/\D/g, ""))} />
          <span className="text-ink-2">of {fmtInt(Math.max(1, pageCount))}</span>
        </form>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPage(page + 1)} disabled={page >= pageCount}>Next</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPage(pageCount)} disabled={page >= pageCount} aria-label="Last page">»</button>
      </div>
    </nav>
  );
}

/* ---------------------------------------------------------------- Disclosure menu */

/** Button + panel disclosure (Escape and outside click close it; focus returns to the button). */
export function Disclosure({ label, children, align = "right", buttonClass = "btn btn-secondary btn-sm" }: {
  label: React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
  buttonClass?: string;
}) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (!btn.current?.contains(e.target as Node) && !panel.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);
  return (
    <div className="relative">
      <button ref={btn} type="button" className={buttonClass} aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        {label}
        <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
      </button>
      <div
        ref={panel}
        id={id}
        hidden={!open}
        className={`absolute top-full z-20 mt-1 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-2 shadow-lg ${align === "right" ? "right-0" : "left-0"}`}
      >
        {open ? children(() => {
          setOpen(false);
          btn.current?.focus();
        }) : null}
      </div>
    </div>
  );
}
