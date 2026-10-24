/** Small presentational helpers shared by the Protein Entry sections. */
import type { ReactNode } from "react";
import type { SectionId } from "../../lib/entry";
import { safeExternalUrl } from "../../lib/safe";
import { RELEASE_LABEL } from "../../data/release";

export function Row({ k, children, testId }: { k: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <div className="grid gap-1 border-b border-line py-2 last:border-b-0 sm:grid-cols-[14rem_minmax(0,1fr)] sm:gap-4" data-testid={testId}>
      <dt className="text-sm font-medium text-ink-2">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

/** Explicit placeholder for a missing value; the label says why it is missing. */
export const na = (v: ReactNode, label = "Not reported") =>
  v === null || v === undefined || v === "" ? <span className="text-ink-2">{label}</span> : v;

export const NOT_AVAILABLE = `Not available in the ${RELEASE_LABEL} export`;

export function Section({ id, title, lead, children, testId }: { id: SectionId | "viewer"; title: ReactNode; lead?: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <section id={`section-${id}`} aria-labelledby={`h-${id}`} className="scroll-mt-32 lg:scroll-mt-20" data-testid={testId ?? `section-${id}`}>
      <h2 id={`h-${id}`} tabIndex={-1} className="text-xl outline-none">{title}</h2>
      {lead ? <div className="prose-links mt-1 max-w-4xl text-sm text-ink-2">{lead}</div> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Ext({ href, children }: { href: string; children: ReactNode }) {
  const safe = safeExternalUrl(href);
  // PR-6: a non-http(s) URL is never rendered as a link; the text stays visible.
  if (!safe) return <span data-unsafe-link="">{children}</span>;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export const fmtNum = (v: number | null | undefined, digits = 2) => (v === null || v === undefined ? null : Number.isInteger(v) ? String(v) : v.toFixed(digits));

export function downloadText(filename: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
