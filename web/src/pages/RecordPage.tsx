/**
 * Protein Entry page: #/record/<MRDB or source accession>[?section=<id>][&structure=pdb:<ID>|afdb|pred]
 *
 * One page with a sticky section navigation (overview, sequence and motifs, experimental structures,
 * predicted structures, phylogenetic placement, functional evidence, publications) and an on-demand
 * Mol* viewer. An MRDB accession opens its MRDB representative source; a source accession opens that
 * source within its MRDB entry. Section navigation and viewer selection replace the URL (no history
 * entry); switching source record is a normal link (new history entry).
 *
 * Loads one per-MRDB record file (records/<MRDB>.json) plus accessions.json for resolution;
 * malformed accessions are rejected without any request.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { replaceHash } from "../app/navigation";
import { MRDB_RE, UNIPROT_RE, href } from "../app/routes";
import { CladeBadge, EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../components/Badges";
import { Breadcrumbs, Disclosure, PageTitle, SearchBox } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadAccessions, loadClades, loadRecord, loadVocabulary, releaseFileUrl, useResource } from "../data/loaders";
import type { Clades, MrdbEntry, SourceRecord, Vocabulary } from "../data/types";
import { EvidenceSection } from "../features/entry/EvidenceSection";
import { HabitatSection } from "../features/entry/HabitatSection";
import { OverviewSection } from "../features/entry/OverviewSection";
import { PhylogenySection } from "../features/entry/PhylogenySection";
import { PublicationsSection } from "../features/entry/PublicationsSection";
import { SequenceSection } from "../features/entry/SequenceSection";
import { ExperimentalSection, PredictedSection } from "../features/entry/StructureSections";
import { Section, copyText, downloadText } from "../features/entry/ui";
import { StructureViewer } from "../features/structure/StructureViewer";
import {
  SECTIONS, defaultStructure, fasta, parseRecordQuery, permalinkQuery, recordQueryString, resolveSelection, sourcePosition,
  structureOptions, type SectionId, type StructureSel,
} from "../lib/entry";
import { fmtInt } from "../lib/format";
import { caveatMap } from "../lib/summary";

type Resolved = { entry: MrdbEntry; focus: string; via: "mrdb" | "source" } | null;

export const isWellFormedAccession = (a: string) => MRDB_RE.test(a) || UNIPROT_RE.test(a);

async function resolve(acc: string): Promise<Resolved> {
  const a = acc.trim().toUpperCase();
  if (!isWellFormedAccession(a)) return null;
  // The accession map is checked first so unknown accessions never trigger a 404 request.
  const map = await loadAccessions();
  if (MRDB_RE.test(a)) {
    if (!map.by_mrdb[a]) return null;
    const entry = await loadRecord(a);
    return entry ? { entry, focus: entry.representative_source_acc, via: "mrdb" } : null;
  }
  const mrdb = map.by_source[a];
  if (!mrdb) return null;
  const entry = await loadRecord(mrdb);
  return entry ? { entry, focus: a, via: "source" } : null;
}

export default function RecordPage({ accession, params }: { accession: string; params?: URLSearchParams }) {
  const wellFormed = isWellFormedAccession(accession);
  const res = useResource(() => (wellFormed ? Promise.all([resolve(accession), loadClades(), loadVocabulary()]) : Promise.resolve(null)), [accession]);
  if (!wellFormed) return <RecordNotFound accession={accession} malformed />;
  if (res.state === "loading") return <div className="container-page pt-6"><LoadingSkeleton label={`Loading ${accession}`} lines={8} /></div>;
  if (res.state === "error") return <div className="container-page pt-6"><ErrorState error={res.error} retry={res.retry} what={`record ${accession}`} /></div>;
  if (!res.data || !res.data[0]) return <RecordNotFound accession={accession} />;
  const [resolved, clades, vocab] = res.data;
  return <RecordView {...resolved} routeAcc={accession} params={params ?? new URLSearchParams()} clades={clades} vocab={vocab} />;
}

function RecordNotFound({ accession, malformed = false }: { accession: string; malformed?: boolean }) {
  return (
    <div className="container-page pt-6" data-testid="record-not-found" data-malformed={malformed ? "true" : "false"}>
      <PageTitle docTitle={`${accession} not found - MicroRhodoDB`}>Accession not found</PageTitle>
      <p className="max-w-3xl text-ink-2">
        <code className="break-all text-ink">{accession}</code>{" "}
        {malformed
          ? "is not a valid accession. MRDB accessions look like MRDB000001; source (UniProt) accessions look like P02945 or A0A135LS53."
          : "is not an MRDB accession or a source (UniProt) accession in release v1.6.0."}{" "}
        Watchlist candidates are not database records.
      </p>
      <div className="mt-5 max-w-2xl">
        <SearchBox size="md" initial={accession} label="Search again" />
      </div>
      <p className="mt-4 text-sm"><a href={href.browse("group=all&eng=1")}>Browse all records</a></p>
    </div>
  );
}

function RecordView({ entry, focus, via, routeAcc, params, clades, vocab }: {
  entry: MrdbEntry;
  focus: string;
  via: "mrdb" | "source";
  routeAcc: string;
  params: URLSearchParams;
  clades: Clades;
  vocab: Vocabulary;
}) {
  const src = entry.sources.find((s) => s.source_acc === focus) ?? entry.sources[0];
  const caveats = useMemo(() => caveatMap(clades), [clades]);
  const query = parseRecordQuery(params);
  const options = useMemo(() => structureOptions(entry, src), [entry, src]);
  const fallback = useMemo(() => defaultStructure(src), [src]);
  const selected = resolveSelection(options, query.structure, fallback);
  const [activate, setActivate] = useState(0);
  const [active, setActive] = useState<SectionId>(query.section ?? "overview");
  const [releaseUrl, setReleaseUrl] = useState<string | null>(null);
  const name = src.protein_name ?? "Unnamed protein";
  const ph = src.phylogeny;
  const pos = sourcePosition(entry, src.source_acc);

  useEffect(() => {
    const pm = src.structures.predicted[0];
    if (pm) releaseFileUrl(pm.file).then(setReleaseUrl, () => setReleaseUrl(null));
  }, [src]);

  const setUrl = useCallback(
    (q: { section?: SectionId | null; structure?: StructureSel | null }) => {
      const cur = parseRecordQuery(new URLSearchParams(window.location.hash.split("?")[1] ?? ""));
      const next = { section: q.section !== undefined ? q.section : cur.section, structure: q.structure !== undefined ? q.structure : cur.structure };
      replaceHash(href.record(routeAcc, recordQueryString(next)));
    },
    [routeAcc],
  );

  const goSection = useCallback(
    (id: SectionId | "viewer", smooth = true) => {
      const el = document.getElementById(`section-${id}`);
      if (!el) return;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: smooth && !reduce ? "smooth" : "auto", block: "start" });
      (el.querySelector("h2") as HTMLElement | null)?.focus({ preventScroll: true });
    },
    [],
  );

  // Deep links: scroll once after first render (section has priority over structure).
  const didInitialScroll = useRef(false);
  useEffect(() => {
    if (didInitialScroll.current) return;
    didInitialScroll.current = true;
    if (query.section) requestAnimationFrame(() => goSection(query.section!, false));
    else if (query.structure) requestAnimationFrame(() => goSection("viewer", false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Scroll-spy for the section navigation highlight only (the URL is changed on click, not on scroll).
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const els = SECTIONS.map((s) => document.getElementById(`section-${s.id}`)).filter((e): e is HTMLElement => !!e);
    const vis = new Map<string, number>();
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) vis.set(e.target.id, e.isIntersecting ? e.boundingClientRect.top : Number.POSITIVE_INFINITY);
        let best: string | null = null;
        let bestTop = Number.POSITIVE_INFINITY;
        for (const [id, top] of vis) if (top < bestTop) { best = id; bestTop = top; }
        if (best) setActive(best.replace("section-", "") as SectionId);
      },
      { rootMargin: "-120px 0px -55% 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [src]);

  const onNav = (id: SectionId) => {
    setActive(id);
    setUrl({ section: id });
    goSection(id);
  };

  const onView = (sel: StructureSel) => {
    setUrl({ structure: sel });
    setActivate((n) => n + 1);
    goSection("viewer");
  };

  const cladeKey = ph.clade_state === "tentative" ? ph.tentative_clade_id : ph.clade_id;

  return (
    <div className="container-page pt-6" data-testid="record-page" data-mrdb={entry.mrdb_acc} data-focus={src.source_acc}>
      <Breadcrumbs items={[{ label: "Home", href: href.home() }, { label: "Browse", href: href.browse() }, { label: entry.mrdb_acc }]} />
      <PageTitle
        docTitle={`${entry.mrdb_acc} (${src.source_acc}) ${name} - MicroRhodoDB`}
        eyebrow={<span className="font-mono" data-testid="record-eyebrow">{entry.mrdb_acc} · source record {src.source_acc}{pos && pos.total > 1 ? <span data-testid="source-position" data-index={pos.index} data-total={pos.total}>{` (${pos.index} of ${pos.total})`}</span> : null}</span>}
        lead={<>{src.organism ?? "Organism not reported"} · {fmtInt(src.length)} aa</>}
      >
        {name}
      </PageTitle>

      <div className="-mt-3 mb-4 flex flex-wrap items-center gap-2" data-testid="record-badges">
        <MembershipBadge status={src.membership.status} />
        <EvidenceBadge level={src.function.evidence_level} />
        <FunctionLabel func={src.function.func_class} />
        <CladeBadge state={ph.clade_state} cladeId={ph.clade_id} tentativeId={ph.tentative_clade_id} failing={caveats} />
        {src.is_mrdb_representative ? <FlagBadge tone="info">MRDB representative</FlagBadge> : null}
        {src.engineering.is_engineered ? <FlagBadge tone="warn">engineered</FlagBadge> : null}
        {src.membership.curated_override ? <FlagBadge tone="warn">curated override</FlagBadge> : null}
        {src.function.call_conflict ? <FlagBadge tone="warn">call conflict</FlagBadge> : null}
      </div>

      <HeaderActions entry={entry} src={src} routeAcc={routeAcc} />

      {via === "source" && !src.is_mrdb_representative ? (
        <p className="mb-4 max-w-4xl text-sm text-ink-2" data-testid="source-note">
          Opened from source accession <code>{src.source_acc}</code>, one of {entry.n_source_records} source records of <code>{entry.mrdb_acc}</code>. The MRDB representative is{" "}
          <a className="font-mono" href={href.record(entry.representative_source_acc)}>{entry.representative_source_acc}</a>.
        </p>
      ) : null}
      {cladeKey && caveats.has(cladeKey) ? (
        <p className="mb-4 max-w-4xl text-sm" data-testid="record-caveat-hint">
          <FlagBadge tone="warn">support caveat</FlagBadge> {cladeKey} fails the corrected clade-support thresholds; see <a href={href.record(routeAcc, "section=phylogeny")} onClick={(e) => { e.preventDefault(); onNav("phylogeny"); }}>Phylogenetic placement</a>.
        </p>
      ) : null}

      <div className="lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-8">
        <SectionNav active={active} onNav={onNav} routeAcc={routeAcc} />
        <div className="min-w-0 space-y-10 pb-8">
          <OverviewSection entry={entry} src={src} vocab={vocab} caveats={caveats} />
          <SequenceSection entry={entry} src={src} />
          <Section id="viewer" title="3D structure viewer" testId="section-viewer" lead="Select an experimental PDB entry or a predicted model. The viewer loads only when requested.">
            <StructureViewer
              key={src.source_acc}
              options={options}
              selected={selected}
              onSelect={(o) => setUrl({ structure: o.sel })}
              activate={activate}
            />
          </Section>
          <ExperimentalSection entry={entry} src={src} onView={onView} />
          <PredictedSection src={src} releaseUrl={releaseUrl} onView={onView} />
          <PhylogenySection entry={entry} src={src} clades={clades} vocab={vocab} caveats={caveats} />
          <EvidenceSection entry={entry} src={src} vocab={vocab} />
          <HabitatSection entry={entry} src={src} />
          <PublicationsSection src={src} />
        </div>
      </div>
    </div>
  );
}

function SectionNav({ active, onNav, routeAcc }: { active: SectionId; onNav: (id: SectionId) => void; routeAcc: string }) {
  const list = useRef<HTMLUListElement>(null);
  // Mobile/tablet: keep the active item visible in the horizontally scrolling strip (no page scroll).
  useEffect(() => {
    const ul = list.current;
    const a = ul?.querySelector<HTMLElement>(`[data-section="${active}"]`);
    if (!ul || !a || ul.scrollWidth <= ul.clientWidth) return;
    const left = a.getBoundingClientRect().left - ul.getBoundingClientRect().left + ul.scrollLeft;
    if (left < ul.scrollLeft || left + a.offsetWidth > ul.scrollLeft + ul.clientWidth) ul.scrollTo({ left: Math.max(0, left - 16) });
  }, [active]);
  return (
    <nav aria-label="Record sections" className="sticky top-16 z-20 -mx-4 mb-6 border-b border-line bg-canvas/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:top-20 lg:mx-0 lg:mb-0 lg:self-start lg:border-b-0 lg:bg-transparent lg:px-0" data-testid="section-nav">
      <ul ref={list} className="relative flex gap-1 overflow-x-auto py-2 lg:flex-col lg:gap-0.5 lg:overflow-visible lg:py-0">
        {SECTIONS.map((s) => (
          <li key={s.id} className="shrink-0">
            <a
              href={href.record(routeAcc, `section=${s.id}`)}
              aria-current={active === s.id ? "location" : undefined}
              className={`block whitespace-nowrap rounded-md px-3 py-2 text-sm no-underline ${active === s.id ? "bg-accent-soft font-semibold text-accent-strong" : "text-ink hover:bg-subtle"}`}
              onClick={(e) => {
                e.preventDefault();
                onNav(s.id);
              }}
              data-section={s.id}
            >
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function HeaderActions({ entry, src, routeAcc }: { entry: MrdbEntry; src: SourceRecord; routeAcc: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [jsonUrl, setJsonUrl] = useState<string | null>(null);
  // The record file exactly as served (all source records of the MRDB entry).
  useEffect(() => {
    releaseFileUrl(`records/${entry.mrdb_acc}.json`).then(setJsonUrl, () => setJsonUrl(null));
  }, [entry.mrdb_acc]);
  // Keeps the current (valid) section and structure parameters, so the link reopens the same view.
  const permalink = () => {
    const u = new URL(window.location.href);
    u.hash = href.record(routeAcc, permalinkQuery(window.location.hash)).slice(1);
    return u.toString();
  };
  return (
    <div className="mb-6 flex flex-wrap items-center gap-2" data-testid="record-actions">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={async () => {
          const link = permalink();
          setMsg((await copyText(link)) ? "Link copied (includes the selected section and structure)." : `Copy failed. Link: ${link}`);
        }}
        data-testid="copy-link"
      >
        Copy link
      </button>
      <Disclosure label="Download FASTA" align="left">
        {(close) => (
          <div className="flex min-w-[14rem] flex-col p-1">
            <button type="button" className="rounded px-3 py-2 text-left text-sm hover:bg-subtle" onClick={() => { downloadText(`${src.source_acc}.fasta`, fasta(entry, [src])); close(); }}>
              This source record ({src.source_acc})
            </button>
            {entry.sources.length > 1 ? (
              <button type="button" className="rounded px-3 py-2 text-left text-sm hover:bg-subtle" onClick={() => { downloadText(`${entry.mrdb_acc}_all_sources.fasta`, fasta(entry, entry.sources)); close(); }}>
                All {entry.sources.length} source records
              </button>
            ) : null}
          </div>
        )}
      </Disclosure>
      {jsonUrl ? (
        <a className="btn btn-secondary btn-sm" href={jsonUrl} download={`${entry.mrdb_acc}.json`} data-testid="export-json">
          Export record JSON
        </a>
      ) : null}
      <span role="status" aria-live="polite" className="text-sm text-ink-2">{msg}</span>
    </div>
  );
}
