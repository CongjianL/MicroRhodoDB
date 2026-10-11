/** About (#/about). Lightweight: manifest, summary, clades and vocabulary only. */
import { href } from "../app/routes";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { PageTitle } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadClades, loadManifest, loadSummary, loadVocabulary, useResource } from "../data/loaders";
import { FUNC_LABEL, STATUS_LABEL, fmtInt } from "../lib/format";
import { mv, thresholdText } from "../lib/summary";

export default function AboutPage() {
  const res = useResource(() => Promise.all([loadManifest(), loadSummary(), loadClades(), loadVocabulary()]));
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="About - MicroRhodoDB" lead="Scope, definitions and provenance of the MicroRhodoDB release served by this site.">About MicroRhodoDB</PageTitle>
      {res.state === "loading" ? <LoadingSkeleton lines={8} /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} /> : null}
      {res.state === "ready" ? (() => {
        const [m, s, c, v] = res.data;
        const S = (id: string) => fmtInt(mv(s, id));
        const r = c.clade_rule;
        return (
          <div className="prose-sci max-w-4xl">
            <h2>Scope</h2>
            <p>
              MicroRhodoDB is a curated knowledgebase of microbial (type-I) rhodopsins and related families. Release v{m.dataset_release} ({m.release_date})
              contains <strong>{S("records_total")}</strong> UniProt source records ({S("records_counted")} counted; {S("records_engineered")} engineered constructs are kept
              but excluded from counts), grouped into <strong>{S("mrdb_accessions")}</strong> MRDB accessions (one per unique sequence). Membership status
              separates {S("typeI_members")} Type-I members from candidates, boundary families, heliorhodopsins and decoys, all of which remain browsable and exportable.
            </p>
            <p>
              The novel-family watchlist ({S("watchlist")} entries) is a separate research layer and is not part of the record corpus or its counts.
            </p>

            <h2>Membership statuses</h2>
            <div className="not-prose card overflow-x-auto" role="region" aria-label="Membership statuses" tabIndex={0}>
              <table className="data-table">
                <thead><tr><th scope="col">Status</th><th scope="col">Group</th><th scope="col">Definition</th></tr></thead>
                <tbody>
                  {v.membership_status.map((x) => (
                    <tr key={x.status}>
                      <td><span className="font-medium">{STATUS_LABEL[x.status]}</span><code className="block text-xs text-ink-2">{x.status}</code></td>
                      <td>{x.group}</td>
                      <td className="min-w-[16rem]">{x.definition}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h2>Functional evidence levels</h2>
            <ul>
              {v.evidence_level.map((e) => <li key={e.level}><strong className="font-mono">{e.level}</strong>: {e.definition}</li>)}
            </ul>
            <p>{v.evidence_note} Membership status is distinct from functional evidence level; E1–E5 describe evidence types, not calibrated probabilities of correctness.</p>

            <h2>Functional classes</h2>
            <ul>
              {v.func_class.map((f) => <li key={f.func_class}><strong>{FUNC_LABEL[f.func_class]}</strong> <code className="text-xs">{f.func_class}</code>: {f.definition}</li>)}
            </ul>

            <h2>Reference phylogeny and clades</h2>
            <p>
              Records are placed on the {S("tree_tips")}-tip MR_RT_003 reference tree, rooted on the heliorhodopsin outgroup. The classification comprises{" "}
              <strong>{c.display}</strong>. Level-1 clades are {r.level1.min_tips}–{r.level1.max_tips}-tip clades with {thresholdText(c)}; subclades are{" "}
              {r.subclade.min_tips}–{r.subclade.max_tips}-tip clades with SH-aLRT ≥ {r.subclade.min_sh_alrt} and UFBoot ≥ {r.subclade.min_ufboot}. {r.backbone_group}
            </p>
            <p>
              Support values shown on this site are the original IQ-TREE values mapped to the rooted tree by bipartition. Internal-node labels in the rooted
              tree file are not used because several were found to be attached to the wrong nodes after re-rooting.
            </p>
            <div className="not-prose my-4"><CladeSupportNotice clades={c} /></div>

            <h2>Release provenance</h2>
            <dl className="not-prose grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_minmax(0,1fr)]">
              <dt className="text-ink-2">Dataset release</dt><dd>v{m.dataset_release} ({m.release_date}), schema revision {m.schema_revision}</dd>
              <dt className="text-ink-2">Source database</dt><dd className="break-all font-mono text-xs leading-5">{m.source_db.file}<br />SHA-256 {m.source_db.sha256}</dd>
              <dt className="text-ink-2">Reference tree</dt><dd className="break-all font-mono text-xs leading-5">MR_RT_003.rooted.treefile SHA-256 {m.refpkg.rooted_treefile_sha256}</dd>
              <dt className="text-ink-2">Website data schema</dt><dd>{m.schema_version} (website {m.website_version})</dd>
              <dt className="text-ink-2" id="license">License</dt><dd>{m.license}</dd>
            </dl>

            <h2>This website</h2>
            <p>
              This is a development build of the redesigned website (website {m.website_version}). Every page reads the same exported files for data
              release v{m.dataset_release}; the website computes no new classifications. See <a href={href.section("methods")}>Methods</a> for how each
              page is derived, <a href={href.section("downloads")}>Downloads</a> for checksummed release files and{" "}
              <a href={href.section("citation")}>Citation</a> for how to cite the data release.
            </p>
          </div>
        );
      })() : null}
    </div>
  );
}
