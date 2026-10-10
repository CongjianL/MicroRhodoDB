/**
 * Interim record view for #/record/<MRDB or source accession> (legacy deep links keep working).
 * Loads one per-MRDB file (records/<MRDB>.json); source accessions are resolved via accessions.json.
 * The full Protein Entry page (tabs, sequence features, Mol* viewer) is PR-3.
 */
import { href } from "../app/routes";
import { CladeBadge, EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../components/Badges";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { Breadcrumbs, Callout, PageTitle, SearchBox } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadAccessions, loadClades, loadRecord, loadVocabulary, useResource } from "../data/loaders";
import type { Clades, MrdbEntry, SourceRecord, Vocabulary } from "../data/types";
import { CLADE_STATE_LABEL, domainLabel, fmtInt } from "../lib/format";
import { caveatMap } from "../lib/summary";

type Resolved = { entry: MrdbEntry; focus: string; via: "mrdb" | "source" } | null;

async function resolve(acc: string): Promise<Resolved> {
  const a = acc.trim().toUpperCase();
  if (/^MRDB\d{6}$/.test(a)) {
    // Check the accession map first so unknown MRDB IDs never trigger a 404 request.
    const map = await loadAccessions();
    if (!map.by_mrdb[a]) return null;
    const entry = await loadRecord(a);
    return entry ? { entry, focus: entry.representative_source_acc, via: "mrdb" } : null;
  }
  const map = await loadAccessions();
  const mrdb = map.by_source[a];
  if (!mrdb) return null;
  const entry = await loadRecord(mrdb);
  return entry ? { entry, focus: a, via: "source" } : null;
}

export default function RecordPage({ accession }: { accession: string }) {
  const res = useResource(() => Promise.all([resolve(accession), loadClades(), loadVocabulary()]), [accession]);
  if (res.state === "loading") return <div className="container-page pt-6"><LoadingSkeleton label={`Loading ${accession}`} lines={8} /></div>;
  if (res.state === "error") return <div className="container-page pt-6"><ErrorState error={res.error} retry={res.retry} what={`record ${accession}`} /></div>;
  const [resolved, clades, vocab] = res.data;
  if (!resolved) return <RecordNotFound accession={accession} />;
  return <RecordView {...resolved} clades={clades} vocab={vocab} />;
}

function RecordNotFound({ accession }: { accession: string }) {
  return (
    <div className="container-page pt-6" data-testid="record-not-found">
      <PageTitle docTitle={`${accession} not found - MicroRhodoDB`}>Accession not found</PageTitle>
      <p className="max-w-3xl text-ink-2">
        <code className="text-ink">{accession}</code> is not an MRDB accession or a source (UniProt) accession in release v1.6.0.
        Watchlist candidates are not database records.
      </p>
      <div className="mt-5 max-w-2xl">
        <SearchBox size="md" initial={accession} label="Search again" />
      </div>
      <p className="mt-4 text-sm"><a href={href.browse("group=all&eng=1")}>Browse all records</a></p>
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-line py-2 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm font-medium text-ink-2">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

const na = (v: React.ReactNode, label = "Not reported") => (v === null || v === undefined || v === "" ? <span className="text-ink-2">{label}</span> : v);

function RecordView({ entry, focus, via, clades, vocab }: { entry: MrdbEntry; focus: string; via: "mrdb" | "source"; clades: Clades; vocab: Vocabulary }) {
  const src = entry.sources.find((s) => s.source_acc === focus) ?? entry.sources[0];
  const caveats = caveatMap(clades);
  const statusDef = new Map(vocab.membership_status.map((m) => [m.status, m.definition]));
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const ph = src.phylogeny;
  const cladeKey = ph.clade_state === "tentative" ? ph.tentative_clade_id : ph.clade_id;
  const name = src.protein_name ?? "Unnamed protein";

  return (
    <div className="container-page pt-6" data-testid="record-page" data-mrdb={entry.mrdb_acc} data-focus={src.source_acc}>
      <Breadcrumbs items={[{ label: "Home", href: href.home() }, { label: "Browse", href: href.browse() }, { label: entry.mrdb_acc }]} />
      <PageTitle
        docTitle={`${entry.mrdb_acc} (${src.source_acc}) ${name} - MicroRhodoDB`}
        eyebrow={<span className="font-mono">{entry.mrdb_acc} · source record {src.source_acc}</span>}
        lead={<>{src.organism ?? "Organism not reported"} · {fmtInt(src.length)} aa</>}
      >
        {name}
      </PageTitle>

      <div className="mb-5">
        <Callout title="Interim record view">
          This development build shows the core annotations of the record. The complete Protein Entry page (sequence features, structure viewer,
          publication evidence) is planned for PR-3.
          {via === "source" ? <> Opened from source accession <code>{focus}</code>, which resolves to <code>{entry.mrdb_acc}</code>.</> : null}
        </Callout>
      </div>

      {entry.sources.length > 1 ? (
        <section aria-labelledby="sources-h" className="mb-6">
          <h2 id="sources-h" className="text-lg">Source records sharing {entry.mrdb_acc}</h2>
          <p className="mt-1 text-sm text-ink-2">
            {entry.n_source_records} source accessions have the identical sequence. The MRDB representative is{" "}
            <code>{entry.representative_source_acc}</code>; annotations below are for the selected source record. Source-specific structures and publications are not merged.
          </p>
          <div className="card mt-2 overflow-x-auto" role="region" aria-label="Source records" tabIndex={0}>
            <table className="data-table" data-testid="sources-table">
              <thead>
                <tr>
                  <th scope="col">Source accession</th>
                  <th scope="col">Role</th>
                  <th scope="col">Membership</th>
                  <th scope="col">Evidence</th>
                  <th scope="col">Clade</th>
                  <th scope="col" className="num">PDB entries</th>
                </tr>
              </thead>
              <tbody>
                {entry.sources.map((s) => (
                  <tr key={s.source_acc} aria-current={s.source_acc === src.source_acc ? "true" : undefined} className={s.source_acc === src.source_acc ? "bg-accent-soft" : undefined}>
                    <td>
                      {s.source_acc === src.source_acc ? <strong className="font-mono">{s.source_acc} (shown)</strong> : <a className="font-mono" href={href.record(s.source_acc)}>{s.source_acc}</a>}
                    </td>
                    <td className="space-x-1">
                      {s.is_mrdb_representative ? <FlagBadge tone="info">MRDB representative</FlagBadge> : null}
                      {s.engineering.is_engineered ? <FlagBadge tone="warn">engineered</FlagBadge> : null}
                      {!s.is_mrdb_representative && !s.engineering.is_engineered ? <span className="text-ink-2">Source record</span> : null}
                    </td>
                    <td><MembershipBadge status={s.membership.status} definition={statusDef.get(s.membership.status)} /></td>
                    <td><EvidenceBadge level={s.function.evidence_level} definition={evDef.get(s.function.evidence_level)} /></td>
                    <td><CladeBadge state={s.phylogeny.clade_state} cladeId={s.phylogeny.clade_id} tentativeId={s.phylogeny.tentative_clade_id} failing={caveats} compact /></td>
                    <td className="num">{s.structures.experimental.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="mem-h" className="card p-4">
          <h2 id="mem-h" className="text-lg">Membership</h2>
          <dl className="mt-2">
            <Row k="Status"><MembershipBadge status={src.membership.status} /> <span className="mt-1 block text-sm text-ink-2">{statusDef.get(src.membership.status)}</span></Row>
            <Row k="Membership score">{na(src.membership.score?.toFixed(4))}</Row>
            <Row k="Architecture">{na(src.membership.architecture_class)}</Row>
            <Row k="Status reason">{na(src.membership.status_reason)}</Row>
            {src.membership.curated_override ? <Row k="Curated override">{src.membership.curated_override.rationale}</Row> : null}
            <Row k="Engineered construct">{src.engineering.is_engineered ? <>Yes; not counted. Wild type: {na(src.engineering.wild_type_acc)}</> : "No"}</Row>
          </dl>
        </section>

        <section aria-labelledby="fn-h" className="card p-4">
          <h2 id="fn-h" className="text-lg">Function and evidence</h2>
          <dl className="mt-2">
            <Row k="Functional class"><FunctionLabel func={src.function.func_class} /> <code className="text-xs text-ink-2">{src.function.func_class}</code></Row>
            <Row k="Evidence level"><EvidenceBadge level={src.function.evidence_level} definition={evDef.get(src.function.evidence_level)} long /></Row>
            <Row k="Function basis">{na(src.function.function_basis)}</Row>
            <Row k="E1 representative">
              {src.function.e1_representative ? <a className="font-mono" href={href.record(src.function.e1_representative)}>{src.function.e1_representative}</a> : na(null, "Not applicable")}
              <span className="mt-1 block text-xs text-ink-2">Experimentally characterized record used as functional reference; distinct from the MRDB representative ({entry.representative_source_acc}).</span>
            </Row>
            <Row k="E2 transfer reference">{src.function.e2_ref ? <>{src.function.e2_ref}{src.function.e2_identity !== null ? ` (identity ${src.function.e2_identity})` : ""}</> : na(null, "Not applicable")}</Row>
            <Row k="Function-call conflict">{src.function.call_conflict ? <><FlagBadge tone="warn">conflict</FlagBadge> {src.function.call_conflict_detail}</> : "No"}</Row>
          </dl>
        </section>

        <section aria-labelledby="ph-h" className="card p-4">
          <h2 id="ph-h" className="text-lg">Phylogenetic placement (MR_RT_003)</h2>
          <dl className="mt-2">
            <Row k="Placement state">{CLADE_STATE_LABEL[ph.clade_state]} <code className="text-xs text-ink-2">{ph.clade_state}</code></Row>
            <Row k="Clade"><CladeBadge state={ph.clade_state} cladeId={ph.clade_id} tentativeId={ph.tentative_clade_id} failing={caveats} /></Row>
            <Row k="Clade name">
              {na(ph.clade_state === "tentative" ? ph.tentative_clade_name : ph.clade_name)}
              {cladeKey ? <>{" "}<a href={href.clade(cladeKey)} className="text-sm whitespace-nowrap" data-testid="record-clade-link">Clade summary</a></> : null}
            </Row>
            <Row k="Subclade">{na(ph.subclade_id, "None")}</Row>
            <Row k="Reference-tree tip">{ph.is_reference_tip ? `Yes${ph.tip_role ? ` (${ph.tip_role})` : ""}` : "No (placed)"}</Row>
          </dl>
          {cladeKey && caveats.has(cladeKey) ? <div className="mt-3"><CladeSupportNotice clades={clades} only={[cladeKey]} compact /></div> : null}
        </section>

        <section aria-labelledby="tx-h" className="card p-4">
          <h2 id="tx-h" className="text-lg">Taxonomy and sequence</h2>
          <dl className="mt-2">
            <Row k="Domain">{domainLabel(src.tax_domain)}</Row>
            <Row k="Lineage"><span className="text-sm">{na(src.lineage)}</span></Row>
            <Row k="GTDB taxonomy"><span className="text-sm">{na(src.gtdb.taxonomy)}</span></Row>
            <Row k="Helix-C motif">{na(src.motifs.helixC_motif && <code>{src.motifs.helixC_motif}</code>)}</Row>
            <Row k="Retinal-site residue">{na(src.motifs.retinal_site_residue && <code>{src.motifs.retinal_site_residue}</code>)}</Row>
            <Row k="UniProt">
              <a href={`https://www.uniprot.org/uniprotkb/${encodeURIComponent(src.source_acc)}/entry`} rel="noopener noreferrer" target="_blank">{src.source_acc}</a>
              {src.reviewed ? " (reviewed)" : ""}
            </Row>
          </dl>
        </section>

        <section aria-labelledby="st-h" className="card p-4 lg:col-span-2">
          <h2 id="st-h" className="text-lg">Structures</h2>
          <StructureSummary src={src} />
        </section>

        <section aria-labelledby="seq-h" className="card p-4 lg:col-span-2">
          <h2 id="seq-h" className="text-lg">Sequence <span className="text-sm font-normal text-ink-2">({fmtInt(src.length)} aa)</span></h2>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all rounded bg-subtle p-3 font-mono text-[0.8125rem] leading-relaxed" data-testid="sequence">{src.sequence}</pre>
        </section>
      </div>
    </div>
  );
}

function StructureSummary({ src }: { src: SourceRecord }) {
  const exp = src.structures.experimental;
  const af = src.structures.afdb;
  return (
    <div className="mt-2 space-y-3 text-sm">
      <p>
        <strong>Experimental (PDB): </strong>
        {exp.length ? (
          <>
            {exp.length} entr{exp.length === 1 ? "y" : "ies"} linked to {src.source_acc}:{" "}
            <span className="font-mono" data-testid="pdb-list">
              {exp.map((p, i) => (
                <span key={p.pdb_id}>
                  {i ? ", " : ""}
                  <a href={`https://www.rcsb.org/structure/${p.pdb_id}`} rel="noopener noreferrer" target="_blank" title={`${p.title} (${p.method}${typeof p.resolution_A === "number" ? `, ${p.resolution_A} Å` : ""})`}>{p.pdb_id}</a>
                </span>
              ))}
            </span>
          </>
        ) : (
          <span className="text-ink-2">None linked to this source record.</span>
        )}
      </p>
      <p>
        <strong>AlphaFold DB: </strong>
        {af.status === "ok" && af.model_id ? (
          <>
            <a href={`https://alphafold.ebi.ac.uk/entry/${encodeURIComponent(src.source_acc)}`} rel="noopener noreferrer" target="_blank">{af.model_id}</a>
            {af.global_plddt !== null ? `, mean pLDDT ${af.global_plddt}` : ""} (predicted model)
          </>
        ) : (
          <span className="text-ink-2">No model.</span>
        )}
      </p>
      <p className="text-ink-2">Interactive structure viewing is planned for PR-3.</p>
    </div>
  );
}
