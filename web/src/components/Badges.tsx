/**
 * Scientific status indicators. Every badge carries a text label (never colour alone) and keeps the
 * raw database code available in the title attribute / exports.
 */
import type { CladeState, EvidenceLevel, FuncClass, MembershipStatus } from "../data/types";
import { CLADE_STATE_LABEL, FUNC_LABEL, STATUS_GROUP, STATUS_LABEL } from "../lib/format";

export function MembershipBadge({ status, definition }: { status: MembershipStatus; definition?: string }) {
  const g = STATUS_GROUP[status];
  return (
    <span className={`badge badge-${g}`} title={definition ? `${status}: ${definition}` : status}>
      {STATUS_LABEL[status]}
    </span>
  );
}

export function EvidenceBadge({ level, definition, long = false }: { level: EvidenceLevel; definition?: string; long?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`ev ev-${level}`} title={definition ? `${level}: ${definition}` : level}>
        {level}
      </span>
      {long && definition ? <span className="text-ink-2 text-sm">{definition}</span> : null}
    </span>
  );
}

export function FunctionLabel({ func }: { func: FuncClass }) {
  const muted = func === "unresolved" || func === "unassigned";
  return (
    <span className={muted ? "text-ink-2" : undefined} title={func}>
      {FUNC_LABEL[func]}
    </span>
  );
}

/** Warning marker for records whose (tentative) clade fails the corrected run1 support thresholds. */
export function SupportCaveat({ cladeId, label }: { cladeId: string; label: string }) {
  return (
    <span className="badge badge-warn" title={`${cladeId}: ${label}`}>
      <span aria-hidden="true">!</span>
      <span>support caveat</span>
    </span>
  );
}

export interface CladeCellProps {
  state: CladeState;
  cladeId: string | null;
  tentativeId: string | null;
  failing: Map<string, string>; // clade_id -> short caveat text
  compact?: boolean;
}

/** Clade display: confident assignment, tentative placement (italic, labelled) or the non-clade state. */
export function CladeBadge({ state, cladeId, tentativeId, failing, compact = false }: CladeCellProps) {
  const id = state === "tentative" ? tentativeId : cladeId;
  if (id && (state === "confident" || state === "tentative" || cladeId)) {
    const tentative = state === "tentative";
    const caveat = failing.get(id);
    return (
      <span className="inline-flex flex-wrap items-center gap-1">
        <span
          className={`font-mono text-[0.8125rem] ${tentative ? "italic text-ink-2" : "text-ink"}`}
          title={tentative ? `Tentative placement near ${id} (not a confident assignment)` : `Assigned to ${id}`}
        >
          {tentative ? `~${id}` : id}
        </span>
        {tentative ? <span className="badge badge-neutral italic">tentative</span> : null}
        {caveat ? (compact ? <span className="badge badge-warn" title={`${id}: ${caveat}`}>caveat</span> : <SupportCaveat cladeId={id} label={caveat} />) : null}
      </span>
    );
  }
  return <span className="text-ink-2" title={state}>{CLADE_STATE_LABEL[state]}</span>;
}

export function FlagBadge({ children, tone = "neutral", title }: { children: React.ReactNode; tone?: "neutral" | "warn" | "info"; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}
