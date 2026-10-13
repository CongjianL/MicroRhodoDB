/**
 * PR-7c.2 Ecology and habitat section of the Protein Entry page.
 *
 * Displays observed environmental metadata, not inferred habitats: values are shown verbatim with their provenance
 * (evidence ID, source record, field). Physical habitat, host association, collection metadata and organism-level
 * literature context are separate blocks; a host is never shown as a habitat and organism context is never shown as
 * the sampling habitat. Loads one habitat file per MRDB accession, lazily; failures degrade to a neutral message.
 */
import { useState, type ReactNode } from "react";
import { href } from "../../app/routes";
import { FlagBadge } from "../../components/Badges";
import { LoadingSkeleton } from "../../components/States";
import type { HabitatItem, HabitatRecordFile, HabitatSummary } from "../../data/habitatTypes";
import { loadHabitat, loadHabitatSummary, useResource, type Resource } from "../../data/loaders";
import type { MrdbEntry, SourceRecord } from "../../data/types";
import { fmtInt } from "../../lib/format";
import {
  GRADE_INFO, HOST_INFO, HOST_TISSUE_NOTE, NOT_USABLE_TEXT, NO_LINK_TEXT, ORGANISM_CONTEXT_LABEL, QUARANTINE_TEXT, ROLE_LABEL,
  SOURCE_LABEL, accessionUrl, checkHabitatFile, doiUrl, envoLinks, habitatView, itemUrl, hostStatusText, pubmedUrl, sourceRows, valueText,
  type HabitatView, type ValueGroup,
} from "../../lib/habitat";
import { Ext, Row, Section } from "./ui";

const LEAD = "Observed environmental metadata from the sample records and literature linked to this source record, shown verbatim with provenance. Nothing here is inferred, normalised or mapped to an ontology.";

export function HabitatSection({ entry, src }: { entry: MrdbEntry; src: SourceRecord }) {
  const res = useResource(() => loadHabitat(entry.mrdb_acc), [entry.mrdb_acc]);
  return (
    <Section id="habitat" title="Ecology and habitat" lead={LEAD}>
      <HabitatBody res={res} entry={entry} src={src} />
    </Section>
  );
}

function Unavailable() {
  return (
    <p className="card p-4 text-sm text-ink-2" data-testid="habitat-unavailable" role="status">
      Habitat metadata unavailable in this build. The rest of this record is not affected.
    </p>
  );
}

function HabitatBody({ res, entry, src }: { res: Resource<HabitatRecordFile | null>; entry: MrdbEntry; src: SourceRecord }) {
  if (res.state === "loading") return <LoadingSkeleton label="Loading habitat metadata" lines={3} />;
  if (res.state === "error") return <Unavailable />;
  const chk = checkHabitatFile(res.data, entry.mrdb_acc, entry.sources.map((s) => s.source_acc), src.source_acc);
  if (!chk.ok) return <Unavailable />;
  const file = res.data as HabitatRecordFile;
  const v = habitatView(chk.entry);
  return (
    <div className="space-y-4" data-testid="habitat-body" data-grade={v.grade.id} data-host={v.entry.host_association_status} data-source={src.source_acc}>
      <div className="flex flex-wrap items-center gap-2" data-testid="habitat-badges">
        <span className="text-sm text-ink-2">Physical habitat evidence:</span>
        <FlagBadge tone={v.grade.tone}><span data-testid="habitat-grade">{v.grade.label}</span></FlagBadge>
        <FlagBadge tone={HOST_INFO[v.entry.host_association_status].tone}><span data-testid="habitat-host-status">{HOST_INFO[v.entry.host_association_status].label}</span></FlagBadge>
        {v.noLink ? <FlagBadge tone="warn">no traceable sample link</FlagBadge> : null}
      </div>
      {file.sources.length > 1 ? <SourceTable file={file} focus={src.source_acc} /> : null}
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <PhysicalCard v={v} />
        <HostCard v={v} />
        <CollectionCard v={v} />
        {v.organismContext.length ? <OrganismCard v={v} /> : null}
      </div>
      <LiteratureChecked v={v} />
      <AboutData />
    </div>
  );
}

function SourceTable({ file, focus }: { file: HabitatRecordFile; focus: string }) {
  const rows = sourceRows(file, focus);
  return (
    <div data-testid="habitat-sources">
      <p className="max-w-4xl text-sm">
        This MRDB accession has {rows.length} source records. Habitat metadata belong to each source record, not to the
        MRDB sequence.{" "}
        {file.source_grades_differ ? (
          <strong data-testid="habitat-grades-differ">Their habitat evidence differs, so no MRDB-level habitat is asserted.</strong>
        ) : (
          "Choosing a source record opens the whole page for that record."
        )}
      </p>
      <div className="card relative mt-2 overflow-x-auto" role="region" aria-label="Habitat evidence by source record" tabIndex={0}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Source accession</th>
              <th scope="col">Physical habitat evidence</th>
              <th scope="col">Host association</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.source_acc} aria-current={r.current ? "true" : undefined} className={r.current ? "bg-accent-soft" : undefined} data-source={r.source_acc} data-grade={r.grade}>
                <td>
                  {r.current ? (
                    <strong className="font-mono">{r.source_acc} <span className="font-sans font-normal text-ink-2">(shown)</span></strong>
                  ) : (
                    <a className="font-mono" href={href.record(r.source_acc, "section=habitat")} data-testid="habitat-source-switch">{r.source_acc}</a>
                  )}
                  {r.representative ? <span className="ml-2"><FlagBadge tone="info">MRDB representative</FlagBadge></span> : null}
                </td>
                <td><FlagBadge tone={GRADE_INFO[r.grade].tone}>{GRADE_INFO[r.grade].label}</FlagBadge></td>
                <td className="text-sm">{HOST_INFO[r.host].label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Sidecar URLs are linked only when https on an allowlisted host; anything else is shown as text. */
function MaybeLink({ url, children }: { url: string | null; children?: ReactNode }) {
  const u = itemUrl(url);
  const body = children ?? url;
  return u ? <Ext href={u}>{body}</Ext> : <span data-unsafe-link="">{body}</span>;
}

function Provenance({ i }: { i: HabitatItem }) {
  return (
    <details className="mt-1 text-xs" data-testid="habitat-provenance">
      <summary className="cursor-pointer py-1 text-accent">Provenance</summary>
      <dl className="grid grid-cols-[minmax(0,1fr)] gap-x-3 gap-y-2 sm:grid-cols-[8rem_minmax(0,1fr)] [&>dd]:min-w-0">
        <dt className="text-ink-2">Evidence ID</dt><dd><code data-testid="habitat-evidence-id">{i.evidence_id}</code></dd>
        <dt className="text-ink-2">Source</dt><dd>{SOURCE_LABEL[i.evidence_source] ?? i.evidence_source} <span className="font-mono">{i.entity_accession}</span></dd>
        <dt className="text-ink-2">Field</dt><dd><code>{i.field}</code>{i.link_index !== null ? <span className="text-ink-2"> · link {i.link_index}</span> : null}</dd>
        <dt className="text-ink-2">Value status</dt><dd><code>{i.value_status}</code></dd>
        <dt className="text-ink-2">Linkage</dt><dd>{i.linkage_route}{i.mapping_confidence ? ` · ${i.mapping_confidence}` : ""}</dd>
        <dt className="text-ink-2">Record</dt><dd className="break-all"><MaybeLink url={i.browser_url} /></dd>
        {i.source_url ? (<><dt className="text-ink-2">Retrieved from</dt><dd className="break-all"><MaybeLink url={i.source_url} /></dd></>) : null}
      </dl>
    </details>
  );
}

/** One verbatim value. ENVO identifiers are linked only when verified in OLS and the item is not quarantined. */
function ItemValue({ i, note, showSource }: { i: HabitatItem; note?: string; showSource?: boolean }) {
  const links = envoLinks(i);
  return (
    <div data-testid="habitat-item" data-evidence-id={i.evidence_id} data-role={i.role} data-status={i.value_status} data-quarantine={i.quarantine ?? undefined}>
      <span className="break-words" data-testid="habitat-value">{valueText(i)}</span>
      {links.length ? (
        <span className="ml-2 text-xs">
          {links.map(({ id, url }) => (
            <span key={id} className="mr-1" data-testid="habitat-envo-link" data-envo={id}>
              <Ext href={url}>{links.length === 1 && i.value?.includes(id) ? <>ENVO term page<span className="sr-only"> for {id}</span></> : id}</Ext>
            </span>
          ))}
        </span>
      ) : null}
      {i.quarantine ? (
        <span className="mt-0.5 block text-xs text-ink-2" data-testid="habitat-quarantine"><FlagBadge tone="warn">not an ontology term</FlagBadge> {QUARANTINE_TEXT[i.quarantine] ?? i.quarantine}</span>
      ) : null}
      {note ? <span className="mt-0.5 block text-xs text-ink-2">{note}</span> : null}
      {showSource ? (
        <span className="mt-0.5 block text-xs text-ink-2" data-testid="habitat-item-source">
          {SOURCE_LABEL[i.evidence_source] ?? i.evidence_source} <span className="font-mono">{i.entity_accession}</span>
        </span>
      ) : null}
      <Provenance i={i} />
    </div>
  );
}

function Groups({ groups, testId, note }: { groups: ValueGroup[]; testId: string; note?: (i: HabitatItem) => string | undefined }) {
  return (
    <div className="space-y-3" data-testid={testId}>
      {groups.map((g) => (
        <div key={g.key} className="rounded-md border border-line p-3" data-testid="habitat-entity" data-entity={g.entity}>
          <p className="text-xs text-ink-2">
            Reported by {SOURCE_LABEL[g.source] ?? g.source}{" "}
            <MaybeLink url={g.items[0].browser_url}><span className="font-mono">{g.entity}</span></MaybeLink>
          </p>
          <dl className="mt-1">
            {g.items.map((i) => (
              <Row key={i.evidence_id} k={ROLE_LABEL[i.role] ?? i.role}><ItemValue i={i} note={note?.(i)} /></Row>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function NotUsable({ items, testId, title }: { items: HabitatItem[]; testId: string; title: string }) {
  if (!items.length) return null;
  return (
    <details className="mt-3 text-sm" data-testid={testId}>
      <summary className="cursor-pointer text-accent">{title} ({items.length})</summary>
      <dl className="mt-1">
        {items.map((i) => (
          <Row key={i.evidence_id} k={ROLE_LABEL[i.role] ?? i.role}>
            <ItemValue i={i} note={NOT_USABLE_TEXT[i.value_status] ? `Not usable: ${NOT_USABLE_TEXT[i.value_status]}` : undefined} />
          </Row>
        ))}
      </dl>
    </details>
  );
}

function LiteratureItem({ i, label }: { i: HabitatItem; label?: string }) {
  const L = i.literature;
  const pm = L ? pubmedUrl(L.pmid) : null;
  const doi = L ? doiUrl(L.doi) : null;
  return (
    <figure className="rounded-md border border-line p-3" data-testid="habitat-literature" data-evidence-id={i.evidence_id} data-scope={L?.scope}>
      {label ? <p className="mb-1 text-xs font-medium text-ink-2">{label}</p> : null}
      <blockquote className="text-sm">&ldquo;{valueText(i)}&rdquo;</blockquote>
      <figcaption className="mt-1 text-xs text-ink-2">
        {L?.locator ? <>{L.locator} · </> : null}
        {pm ? <Ext href={pm}>PMID {L!.pmid}</Ext> : L ? `PMID ${L.pmid}` : null}
        {doi ? <> · <Ext href={doi}>doi:{L!.doi}</Ext></> : null}
        {L?.access ? <> · {L.access.replace(/_/g, " ")}</> : null}
      </figcaption>
      {i.value_status.startsWith("rejected:") ? (
        <p className="mt-1 text-xs" data-testid="habitat-rejected">Not used: {i.value_status.slice("rejected:".length).replace(/_/g, " ")}.</p>
      ) : null}
      <Provenance i={i} />
    </figure>
  );
}

function PhysicalCard({ v }: { v: HabitatView }) {
  return (
    <div className="card p-4" data-testid="habitat-physical">
      <h3 className="text-base">Physical habitat</h3>
      <p className="mt-1 text-sm">{v.grade.text}</p>
      {v.missing ? <p className="mt-2 text-sm" data-testid="habitat-missingness">{v.missing}</p> : null}
      {v.noLink && !v.missing ? <p className="mt-2 text-sm" data-testid="habitat-no-link">{NO_LINK_TEXT}</p> : null}
      {v.hostOnly ? <p className="mt-2 text-sm" data-testid="habitat-host-only">{v.hostOnly}</p> : null}
      {v.ambiguity ? (
        <p className="mt-2 text-sm" data-testid="habitat-ambiguity" data-class={v.entry.ambiguity_class ?? undefined}>
          <strong>{v.ambiguity.label}.</strong> {v.ambiguity.text}
        </p>
      ) : null}
      {v.physical.length ? (
        <div className="mt-3">
          <Groups groups={v.physical} testId="habitat-physical-values" note={(i) => (v.hostTissue && i.role === "isolation_source" ? HOST_TISSUE_NOTE : undefined)} />
        </div>
      ) : null}
      {v.literatureIsolate.length ? (
        <div className="mt-3 space-y-2" data-testid="habitat-literature-isolate">
          <h4 className="text-sm font-semibold">Literature isolation statements</h4>
          {v.literatureIsolate.map((i) => <LiteratureItem key={i.evidence_id} i={i} />)}
        </div>
      ) : null}
      {v.nonstandard.length ? (
        <div className="mt-3" data-testid="habitat-nonstandard">
          <h4 className="text-sm font-semibold">Non-standard habitat fields (not used for the grade)</h4>
          <dl className="mt-1">{v.nonstandard.map((i) => <Row key={i.evidence_id} k={<code>{i.field}</code>}><ItemValue i={i} showSource /></Row>)}</dl>
        </div>
      ) : null}
      {v.literatureRejected.length ? (
        <details className="mt-3 text-sm" data-testid="habitat-literature-rejected">
          <summary className="cursor-pointer text-accent">Rejected literature statements ({v.literatureRejected.length})</summary>
          <div className="mt-2 space-y-2">{v.literatureRejected.map((i) => <LiteratureItem key={i.evidence_id} i={i} />)}</div>
        </details>
      ) : null}
      <NotUsable items={v.notUsable} testId="habitat-not-usable" title="Reported but not usable" />
    </div>
  );
}

function HostCard({ v }: { v: HabitatView }) {
  return (
    <div className="card p-4" data-testid="habitat-host">
      <h3 className="text-base">Host association</h3>
      <p className="mt-1 text-sm">{hostStatusText(v.entry)}</p>
      {v.hostAmbiguity ? (
        <p className="mt-2 text-sm" data-testid="habitat-host-ambiguity" data-class={v.entry.host_ambiguity_class ?? undefined}>
          <strong>{v.hostAmbiguity.label}.</strong> {v.hostAmbiguity.text}
        </p>
      ) : null}
      {v.host.length ? <div className="mt-3"><Groups groups={v.host} testId="habitat-host-values" /></div> : null}
      {v.hostDetail.length ? (
        <div className="mt-3" data-testid="habitat-host-detail">
          <h4 className="text-sm font-semibold">Host detail</h4>
          <dl className="mt-1">{v.hostDetail.map((i) => <Row key={i.evidence_id} k={<code>{i.field}</code>}><ItemValue i={i} showSource /></Row>)}</dl>
        </div>
      ) : null}
      <NotUsable items={v.hostNotUsable} testId="habitat-host-not-usable" title="Reported but not usable" />
    </div>
  );
}

const ACC_LABEL: [keyof HabitatView["entry"]["accessions"], string][] = [
  ["biosamples", "BioSample"], ["bioprojects", "BioProject"], ["insdc", "INSDC entry"], ["embl_protein_ids", "INSDC protein"],
  ["proteomes", "UniProt proteome"], ["assemblies", "Assembly"],
];

function CollectionCard({ v }: { v: HabitatView }) {
  const e = v.entry;
  const acc = ACC_LABEL.filter(([k]) => e.accessions[k].length);
  return (
    <div className="card p-4" data-testid="habitat-collection">
      <h3 className="text-base">Collection metadata</h3>
      {v.noLink ? <p className="mt-1 text-sm" data-testid="habitat-collection-no-link">{NO_LINK_TEXT}</p> : null}
      <dl className="mt-2">
        {acc.map(([k, label]) => (
          <Row key={k} k={label} testId={`habitat-acc-${k}`}>
            <ul className="flex flex-wrap gap-x-3 gap-y-1">
              {e.accessions[k].map((a) => {
                const u = accessionUrl(k, a);
                return <li key={a} className="font-mono text-sm">{u ? <Ext href={u}>{a}</Ext> : a}</li>;
              })}
            </ul>
          </Row>
        ))}
        <Row k="Sample type">{e.linkage.sample_type.replace(/_/g, " ").toLowerCase()}</Row>
        <Row k="Linkage">{e.linkage.route ? `${e.linkage.route.replace(/_/g, " ")}${e.linkage.mapping_confidence ? ` (${e.linkage.mapping_confidence.toLowerCase()} confidence)` : ""}` : <span className="text-ink-2">none</span>}</Row>
        {v.collection.map((i) => (
          <Row key={i.evidence_id} k={ROLE_LABEL[i.role] ?? i.role}><ItemValue i={i} showSource /></Row>
        ))}
      </dl>
      {v.notes.length ? <ul className="mt-2 list-disc pl-5 text-sm" data-testid="habitat-collection-notes">{v.notes.map((n) => <li key={n}>{n}</li>)}</ul> : null}
      <p className="mt-2 text-xs text-ink-2">Country, coordinates and dates are shown as text; they are collection context, not habitat.</p>
      <NotUsable items={v.collectionMissing} testId="habitat-collection-missing" title="Reported as missing" />
    </div>
  );
}

function OrganismCard({ v }: { v: HabitatView }) {
  return (
    <div className="card p-4" data-testid="habitat-organism-context">
      <h3 className="text-base">Organism ecological context</h3>
      <p className="mt-1 text-sm"><FlagBadge tone="neutral">organism-level</FlagBadge> {ORGANISM_CONTEXT_LABEL}.</p>
      <div className="mt-3 space-y-2">
        {v.organismContext.map((i) => <LiteratureItem key={i.evidence_id} i={i} />)}
      </div>
    </div>
  );
}

function LiteratureChecked({ v }: { v: HabitatView }) {
  const e = v.entry;
  if (e.literature_status === "NOT_SEARCHED") return null;
  const status = {
    ORGANISM_CONTEXT: "organism-level context found",
    ISOLATE_EVIDENCE: "isolation statement found",
    LOOKUP_FAILED: "the relevant literature could not be accessed",
    NOT_REPORTED: "no habitat statement found in the reviewed literature",
    NOT_SEARCHED: "not reviewed",
  }[e.literature_status];
  return (
    <details className="card p-4 text-sm" data-testid="habitat-literature-checked" data-status={e.literature_status}>
      <summary className="cursor-pointer text-accent">Literature reviewed for this record: {status} ({e.literature_sources_checked.length} source{e.literature_sources_checked.length === 1 ? "" : "s"})</summary>
      <ul className="mt-2 space-y-1">
        {e.literature_sources_checked.map((s, k) => {
          const pm = s.pmid ? pubmedUrl(s.pmid) : null;
          const doi = doiUrl(s.doi);
          return (
            <li key={k}>
              {s.title ?? <span className="text-ink-2">Untitled source</span>}
              <span className="text-xs text-ink-2">
                {pm ? <> · <Ext href={pm}>PMID {s.pmid}</Ext></> : null}
                {doi ? <> · <Ext href={doi}>doi:{s.doi}</Ext></> : null}
                {s.access ? <> · {s.access.replace(/_/g, " ")}</> : null}
                {s.found_habitat_statement === true ? " · habitat statement found" : s.found_habitat_statement === false ? " · no habitat statement" : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

const ABOUT_METRICS: [string, string][] = [
  ["physical_habitat_usable", "Usable physical habitat (direct sample or verified isolate)"],
  ["grade:DIRECT_SAMPLE", "Direct sample"],
  ["grade:VERIFIED_ISOLATE", "Verified isolate (literature)"],
  ["grade:ORGANISM_CONTEXT_ONLY", "Organism context only"],
  ["grade:AMBIGUOUS", "Conflicting records"],
  ["grade:NOT_REPORTED", "Not reported"],
  ["has_host_association", "Host reported (including conflicting host values)"],
  ["host_association_only", "Host reported, no usable physical habitat value"],
  ["host_without_usable_physical_habitat", "Host present without a usable physical habitat"],
  ["not_reported_scope:database_only_literature_not_reviewed", "Not reported: literature not reviewed"],
  ["not_reported_scope:database_only_literature_inaccessible", "Not reported: literature not accessible"],
  ["not_reported_scope:database_and_literature", "Not reported in sample records or reviewed literature"],
  ["no_traceable_sample_link", "No traceable INSDC or sample link"],
  ["literature_status:LOOKUP_FAILED", "Literature lookup failed"],
  ["multi_source_mrdb:grades_differ", "MRDB accessions whose source records differ in habitat evidence"],
];

function AboutData() {
  const [open, setOpen] = useState(false);
  return (
    <details className="card p-4 text-sm" data-testid="habitat-about" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-accent">About these data</summary>
      {open ? <AboutBody /> : null}
    </details>
  );
}

function AboutBody() {
  const res = useResource<HabitatSummary>(loadHabitatSummary, []);
  if (res.state === "loading") return <LoadingSkeleton label="Loading habitat coverage" lines={2} />;
  if (res.state === "error") return <p className="mt-2 text-ink-2">Coverage figures unavailable in this build.</p>;
  const s = res.data;
  const byId = new Map(s.metrics.map((m) => [m.id, m]));
  return (
    <div className="mt-2 space-y-2" data-testid="habitat-about-body">
      <p>
        Source: habitat audit {s.audit_id}, status <code>{s.audit_status}</code>. {s.audit_status_reason}
      </p>
      <p>{s.interpretation}</p>
      <table className="data-table">
        <caption className="sr-only">Habitat metadata availability, release v{s.dataset_release}</caption>
        <thead><tr><th scope="col">Measure</th><th scope="col" className="num">Records</th><th scope="col" className="num">Of</th><th scope="col" className="num">%</th></tr></thead>
        <tbody>
          {ABOUT_METRICS.map(([id, label]) => {
            const m = byId.get(id);
            if (!m) return null;
            return (
              <tr key={id} data-metric={id}>
                <td>{label}</td>
                <td className="num tabular">{fmtInt(m.numerator)}</td>
                <td className="num tabular">{fmtInt(m.denominator)}</td>
                <td className="num tabular">{m.percent.toFixed(2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-ink-2">Denominator: {fmtInt(s.denominators.source_records)} source records ({fmtInt(s.denominators.mrdb_accessions)} MRDB accessions) unless stated. Counts describe metadata availability only.</p>
    </div>
  );
}
