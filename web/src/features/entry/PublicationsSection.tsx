import { FlagBadge } from "../../components/Badges";
import type { SourceRecord } from "../../data/types";
import { LINK_ROLE_LABEL, groupPublications, type PubGroup } from "../../lib/entry";
import { Ext, Section } from "./ui";

export function PublicationsSection({ src }: { src: SourceRecord }) {
  const { support, other } = groupPublications(src.publications);
  const nSupportLinks = src.publications.filter((p) => p.counts_as_support).length;
  return (
    <Section
      id="publications"
      title="Publications"
      lead={<>Literature links curated for {src.source_acc}. Links that count as support are listed first; compilation, context and conflicting links are listed separately and do not count as support.</>}
    >
      {!src.publications.length ? (
        <div className="card p-4 text-sm text-ink-2" data-testid="pubs-none">No publication is linked to {src.source_acc} in v1.6.0.</div>
      ) : (
        <div className="space-y-6">
          <div data-testid="pubs-support" data-n={support.length}>
            <h3 className="text-base">Supporting publications ({support.length}; {nSupportLinks} assertion{nSupportLinks === 1 ? "" : "s"})</h3>
            {support.length ? <PubList groups={support} /> : <p className="mt-1 text-sm text-ink-2">None. No publication link counts as functional support for this source record.</p>}
          </div>
          {other.length ? (
            <div data-testid="pubs-other" data-n={other.length}>
              <h3 className="text-base">Other linked publications ({other.length}; not counted as support)</h3>
              <PubList groups={other} />
            </div>
          ) : null}
        </div>
      )}
    </Section>
  );
}

function PubList({ groups }: { groups: PubGroup[] }) {
  return (
    <ol className="mt-2 space-y-3">
      {groups.map((g) => (
        <li key={g.publication_id} className="card p-3" data-pub={g.publication_id}>
          <p className="font-medium">{g.title ?? <span className="italic text-ink-2">Title not recorded in v1.6.0</span>}</p>
          <p className="mt-0.5 text-sm text-ink-2">
            {[g.journal, g.year].filter((x) => x !== null && x !== undefined).join(", ") || "Journal and year not recorded"}
            {g.doi ? <> · DOI <Ext href={`https://doi.org/${g.doi}`}>{g.doi}</Ext></> : null}
            {g.pmid ? <> · PMID <Ext href={`https://pubmed.ncbi.nlm.nih.gov/${g.pmid}/`}>{g.pmid}</Ext></> : null}
          </p>
          <ul className="mt-2 space-y-1 border-l-2 border-line pl-3 text-sm">
            {g.links.map((l) => (
              <li key={l.assertion_id}>
                <span className="flex flex-wrap items-center gap-1">
                  <FlagBadge tone={l.counts_as_support ? "info" : l.link_role === "conflicting_evidence" ? "warn" : "neutral"}>{LINK_ROLE_LABEL[l.link_role] ?? l.link_role}</FlagBadge>
                  <span>{l.assertion ?? <span className="text-ink-2">Assertion not recorded</span>}</span>
                </span>
                <span className="block text-xs text-ink-2">
                  Verdict: {l.verdict ?? "not recorded"} · basis: {l.evidence_basis ?? "not recorded"}
                  {l.caveat ? <> · caveat: {l.caveat}</> : null}
                </span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
