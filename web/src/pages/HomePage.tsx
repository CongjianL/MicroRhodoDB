/**
 * Home (#/). Loads only lightweight files: manifest, summary, clades, vocabulary, phylogeny/tips.json
 * and the rooted Newick. Never loads records-index, accessions, per-record files or FASTA.
 */
import { useMemo } from "react";
import { SECTION_PAGES, href, routeForQuery } from "../app/routes";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { Callout, PageTitle, SearchBox, StatCard } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadClades, loadManifest, loadNewick, loadSummary, loadTips, loadVocabulary, useResource, type Resource } from "../data/loaders";
import type { Clades, FuncClass, Manifest, Summary, Tips, Vocabulary } from "../data/types";
import { BarChart, type BarItem } from "../features/charts/BarChart";
import { TREE_RADIUS, TreePreview, buildTreeModel, type TreeModel } from "../features/tree/TreePreview";
import { CladeLegend } from "../features/tree/CladeLegend";
import { FUNC_LABEL, FUNC_ORDER, GROUP_LABEL, STATUS_LABEL, STATUS_ORDER, STATUS_GROUP, fmtInt } from "../lib/format";
import { distCount, distribution, mv } from "../lib/summary";

const GROUP_COLOR = { member: "#1b7f4b", candidate: "#3b4fb8", boundary: "#6b3fb0", outgroup: "#526175", rejected: "#b42318" } as const;
const EV_COLOR = { E1: "#0f4f91", E2: "#1665b5", E3: "#4a8fd6", E4: "#6b7f96", E5: "#a5b3c2" } as const;

export default function HomePage() {
  const core = useResource(() => Promise.all([loadManifest(), loadSummary(), loadClades(), loadVocabulary()]));
  const tree = useResource(() => Promise.all([loadNewick(), loadTips()]));
  return (
    <div className="container-page pt-8">
      <PageTitle docTitle="MicroRhodoDB - microbial rhodopsin knowledgebase" eyebrow={<span className="font-medium text-teal">MicroRhodoDB knowledgebase</span>}>
        Explore the diversity of microbial rhodopsins
      </PageTitle>
      {core.state === "loading" ? <LoadingSkeleton lines={6} /> : null}
      {core.state === "error" ? <ErrorState error={core.error} retry={core.retry} what="the release summary" /> : null}
      {core.state === "ready" ? <HomeBody manifest={core.data[0]} summary={core.data[1]} clades={core.data[2]} vocab={core.data[3]} tree={tree} /> : null}
    </div>
  );
}

function HomeBody({ manifest, summary, clades, vocab, tree }: {
  manifest: Manifest;
  summary: Summary;
  clades: Clades;
  vocab: Vocabulary;
  tree: Resource<[string, Tips]>;
}) {
  const S = (id: string) => mv(summary, id);
  const memberDist = distribution(summary, "membership_group");
  const statusDist = distribution(summary, "membership_status");
  const evDist = distribution(summary, "evidence_level_counted");
  const funcDist = distribution(summary, "func_class_counted");
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));

  const memberItems: BarItem[] = useMemo(
    () => (Object.keys(GROUP_LABEL) as (keyof typeof GROUP_LABEL)[]).map((g) => ({
      key: g,
      label: GROUP_LABEL[g],
      value: distCount(memberDist, g),
      color: GROUP_COLOR[g],
      href: href.browse(`group=${g}&eng=1`),
      note: STATUS_ORDER.filter((s) => STATUS_GROUP[s] === g).map((s) => `${STATUS_LABEL[s]} ${fmtInt(distCount(statusDist, s))}`).join("; "),
    })),
    [memberDist, statusDist],
  );
  const evItems: BarItem[] = useMemo(
    () => (["E1", "E2", "E3", "E4", "E5"] as const).map((e) => ({
      key: e, label: e, value: distCount(evDist, e), color: EV_COLOR[e], href: href.browse(`group=all&evidence=${e}`), note: evDef.get(e),
    })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [evDist],
  );

  const treeModel = useMemo((): { model: TreeModel } | { error: Error } | null => {
    if (tree.state !== "ready") return null;
    try {
      return { model: buildTreeModel(tree.data[0], tree.data[1], TREE_RADIUS) };
    } catch (e) {
      return { error: e as Error };
    }
  }, [tree]);

  const examples: [string, string, string][] = [
    ["P02945", "UniProt accession", routeForQuery("P02945")],
    ["MRDB000011", "MRDB accession", routeForQuery("MRDB000011")],
    ["halorhodopsin", "protein name", routeForQuery("halorhodopsin")],
    ["MR_CLD3_012", "level-1 clade", routeForQuery("MR_CLD3_012")],
    ["1C3W", "PDB ID", routeForQuery("1C3W")],
    ["DTE", "helix-C motif", href.browse("group=all&motif=DTE&eng=1")],
  ];

  return (
    <>
      {/* ---------------- Hero ---------------- */}
      <section aria-labelledby="hero-sub" className="-mt-3">
        <p id="hero-sub" className="max-w-3xl text-lg text-ink-2">
          An evidence-aware knowledgebase integrating sequences, phylogeny, structures and functional evidence
        </p>
        <div className="mt-5 max-w-3xl">
          <SearchBox />
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
            <span>Try:</span>
            {examples.map(([q, kind, h]) => (
              <a key={q} href={h} className="rounded border border-line bg-surface px-1.5 font-mono text-[0.8125rem] no-underline" title={`${kind} example`}>
                {q}
              </a>
            ))}
          </p>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <a href={href.browse()} className="btn btn-primary">Browse proteins</a>
          <a href={href.phylogeny()} className="btn btn-secondary">Explore phylogeny</a>
          <a href={href.section("search", "mode=sequence")} className="btn btn-secondary">Sequence search</a>
        </div>
        <p className="mt-4 text-sm text-ink-2" data-testid="release-line">
          Data release <strong className="text-ink">v{manifest.dataset_release}</strong> ({manifest.release_date}) · {fmtInt(S("records_total"))} source records ·{" "}
          {fmtInt(S("mrdb_accessions"))} MRDB accessions · License: <a href={`${href.about()}`}>{manifest.license}</a>
        </p>
      </section>

      {/* ---------------- Statistics ---------------- */}
      <section aria-labelledby="stats-h" className="mt-10">
        <h2 id="stats-h" className="text-xl">Release v{manifest.dataset_release} at a glance</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="stat-cards">
          <StatCard testId="stat-records" value={S("records_total")} label="Source records" href={href.browse("group=all&eng=1")}
            detail={<>UniProt source records, engineered constructs included. {fmtInt(S("records_counted"))} counted ({fmtInt(S("records_engineered"))} engineered constructs excluded from counts).</>} />
          <StatCard testId="stat-members" value={S("typeI_members")} label="Type-I members" href={href.browse("group=member&eng=1")}
            detail={<>of {fmtInt(S("records_total"))} source records (all member statuses). A further {fmtInt(S("typeI_candidates"))} are candidates.</>} />
          <StatCard testId="stat-e1" value={S("e1_counted")} label="Experimentally characterized (E1)" href={href.browse("group=all&evidence=E1")}
            detail={<>of {fmtInt(S("records_counted"))} counted records; {fmtInt(S("e1_total"))} including engineered constructs; {fmtInt(S("e1_unique_sequences"))} unique MRDB sequences.</>} />
          <StatCard testId="stat-tips" value={S("tree_tips")} label="Reference-tree tips (MR_RT_003)"
            detail={<>{S("level1_clades")} level-1 clades + {S("backbone_groups")} backbone groups. Tree tips are representatives, not a record count.</>} />
          <StatCard testId="stat-pubs" value={S("publications")} label="Publications"
            detail={<>{fmtInt(S("publication_links_active"))} active record links ({fmtInt(S("publication_links_support"))} count as supporting evidence), covering {fmtInt(S("records_with_publications"))} source records.</>} />
          <StatCard testId="stat-watchlist" value={S("watchlist")} label="Novel-family watchlist"
            detail={<>Research candidates kept outside the corpus; not included in any record count.</>} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border border-line bg-surface p-4 text-sm sm:grid-cols-3 lg:grid-cols-6" data-testid="context-metrics">
          {([
            ["records_counted", "Counted records", "engineered excluded"],
            ["mrdb_accessions", "MRDB accessions", `unique sequences; ${fmtInt(S("mrdb_multi_source"))} with >1 source accession`],
            ["typeI_candidates", "Type-I candidates", `of ${fmtInt(S("records_total"))} records`],
            ["records_with_pdb", "Records with PDB entries", `${fmtInt(S("pdb_entries"))} distinct PDB entries`],
            ["records_with_afdb", "Records with AlphaFold DB model", `of ${fmtInt(S("records_total"))} records`],
            ["call_conflict", "Function-call conflicts", `of ${fmtInt(S("records_total"))} records`],
          ] as const).map(([id, label, note]) => (
            <div key={id}>
              <dt className="text-ink-2">{label}</dt>
              <dd className="text-lg font-semibold tabular" data-testid={`ctx-${id}`}>{fmtInt(S(id))}</dd>
              <dd className="text-xs text-ink-2">{note}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ---------------- Charts ---------------- */}
      <section aria-labelledby="dist-h" className="mt-10">
        <h2 id="dist-h" className="text-xl">Membership and functional evidence</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-2">
          Release v{manifest.dataset_release}. Membership status and evidence level are separate axes: a Type-I member can have any evidence level.
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <BarChart testId="chart-membership" title="Membership composition" items={memberItems} denominator={memberDist.denominator.value}
            denominatorLabel="All source records, engineered constructs included" />
          <BarChart testId="chart-evidence" title="Functional evidence level (E1–E5)" items={evItems} denominator={evDist.denominator.value}
            denominatorLabel="Counted records, engineered constructs excluded"
            footer={
              <ul className="grid gap-0.5" data-testid="evidence-definitions">
                {vocab.evidence_level.map((e) => (
                  <li key={e.level}><span className="font-mono font-semibold text-ink">{e.level}</span> {e.definition}</li>
                ))}
              </ul>
            } />
        </div>
      </section>

      {/* ---------------- Tree ---------------- */}
      <section aria-labelledby="tree-h" className="mt-10">
        <h2 id="tree-h" className="text-xl">MR_RT_003 reference phylogeny</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-2">
          {clades.display}. The rooted reference tree drawn from the release file with branch lengths to scale; tip labels are omitted in this preview.
          Clade support is the original IQ-TREE value mapped to the rooted tree by bipartition.
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          <div className="card p-3 sm:p-4">
            {tree.state === "loading" ? <LoadingSkeleton label="Loading reference tree" /> : null}
            {tree.state === "error" ? <ErrorState error={tree.error} retry={tree.retry} what="the reference tree" /> : null}
            {treeModel && "model" in treeModel ? <TreePreview model={treeModel.model} clades={clades} /> : null}
            {treeModel && "error" in treeModel ? <ErrorState error={treeModel.error} what="the reference tree" /> : null}
            <p className="mt-2 text-sm">
              <a href={href.phylogeny()} data-testid="home-explore-tree">Explore tree</a>
            </p>
          </div>
          <div className="min-w-0 space-y-3">
            <CladeLegend clades={clades} colorOf={treeModel && "model" in treeModel ? treeModel.model.colorOf : undefined} />
          </div>
        </div>
        <div className="mt-4">
          <CladeSupportNotice clades={clades} />
        </div>
      </section>

      {/* ---------------- Quick exploration ---------------- */}
      <section aria-labelledby="func-h" className="mt-10">
        <h2 id="func-h" className="text-xl">Explore by functional class</h2>
        <p className="mt-1 text-sm text-ink-2">
          Official v{manifest.dataset_release} functional classes, each opening Browse over all membership groups. Counts: counted records (n = {fmtInt(funcDist.denominator.value)}, engineered constructs excluded).
        </p>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="func-links">
          {FUNC_ORDER.map((f: FuncClass) => (
            <li key={f}>
              <a href={href.browse(`group=all&func=${f}`)} className="card flex items-baseline justify-between gap-3 px-3 py-2.5 no-underline hover:border-accent hover:no-underline" data-func={f}>
                <span className={f === "unresolved" || f === "unassigned" ? "text-ink-2" : "font-medium text-ink"}>{FUNC_LABEL[f]}</span>
                <span className="tabular text-sm text-ink-2" data-testid={`func-count-${f}`}>{fmtInt(distCount(funcDist, f))}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Scientific transparency" className="mt-8">
        <Callout title="How to read these annotations" testId="transparency-note">
          <p>Membership status is distinct from functional evidence level. E1–E5 describe evidence types, not calibrated probabilities of correctness.</p>
          <p className="mt-1">
            Methods for membership scoring, the evidence ladder and phylogenetic placement: <a href={href.section("methods")}>Methods</a>; scope and definitions: <a href={href.about()}>About</a>.
          </p>
        </Callout>
      </section>

      {/* ---------------- Entry points ---------------- */}
      <section aria-labelledby="entry-h" className="mt-10">
        <h2 id="entry-h" className="text-xl">Where to go next</h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { h: href.browse(), t: "Browse", d: "Filter, sort and export source records by membership, function, evidence, clade, taxonomy and structure availability." },
            { h: href.phylogeny(), t: "Phylogeny", d: "Interactive explorer for the 472-tip MR_RT_003 reference tree: rectangular and radial layouts, search, corrected support values, placements and clade pages." },
            { h: href.section("structures"), t: "Structures", d: SECTION_PAGES.structures.summary },
            { h: href.section("search"), t: "Search", d: SECTION_PAGES.search.summary },
            { h: href.section("downloads"), t: "Downloads", d: SECTION_PAGES.downloads.summary },
            { h: href.about(), t: "About", d: "Scope, definitions of membership statuses and evidence levels, release provenance and license." },
          ].map((e) => (
            <li key={e.t}>
              <a href={e.h} className="card block h-full p-4 no-underline hover:border-accent hover:no-underline" data-testid={`entry-${e.t.toLowerCase()}`}>
                <span className="flex items-center gap-2 font-semibold text-accent-strong">
                  {e.t}
                </span>
                <span className="mt-1 block text-sm text-ink-2">{e.d}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
