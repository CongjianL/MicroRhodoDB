import { href } from "../../app/routes";
import { CladeBadge, EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../../components/Badges";
import type { MrdbEntry, SourceRecord, Vocabulary } from "../../data/types";
import { domainLabel, fmtInt } from "../../lib/format";
import { afdbEntryUrl } from "../../lib/entry";
import { Ext, Row, Section, fmtNum, na } from "./ui";

/** Source accessions of this entry that are the E1 functional reference of some source in the entry. */
export function e1RepresentativeSet(entry: MrdbEntry): Set<string> {
  const accs = new Set(entry.sources.map((s) => s.source_acc));
  return new Set(entry.sources.map((s) => s.function.e1_representative).filter((a): a is string => !!a && accs.has(a)));
}

export function OverviewSection({ entry, src, vocab, caveats }: { entry: MrdbEntry; src: SourceRecord; vocab: Vocabulary; caveats: Map<string, string> }) {
  const statusDef = new Map(vocab.membership_status.map((m) => [m.status, m.definition]));
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const funcDef = new Map(vocab.func_class.map((f) => [f.func_class, f.definition]));
  const e1Reps = e1RepresentativeSet(entry);
  const m = src.membership;
  const g = src.gtdb;

  return (
    <Section id="overview" title="Overview">
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="card p-4">
          <h3 className="text-base">Identity and taxonomy</h3>
          <dl className="mt-2">
            <Row k="MRDB accession"><span className="font-mono">{entry.mrdb_acc}</span> <span className="text-sm text-ink-2">(stable; one per unique sequence)</span></Row>
            <Row k="Source accession">
              <Ext href={`https://www.uniprot.org/uniprotkb/${encodeURIComponent(src.source_acc)}/entry`}><span className="font-mono">{src.source_acc}</span></Ext>
              <span className="text-sm text-ink-2"> · {src.source_database}{src.reviewed === true ? ", reviewed (Swiss-Prot)" : src.reviewed === false ? ", unreviewed (TrEMBL)" : ""}</span>
            </Row>
            <Row k="Protein name">{na(src.protein_name)}</Row>
            <Row k="Organism">
              {na(src.organism)}
              {src.organism_id !== null ? <> <span className="text-sm">(<Ext href={`https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${src.organism_id}`}>NCBI Taxonomy {src.organism_id}</Ext>)</span></> : null}
            </Row>
            <Row k="Domain">{domainLabel(src.tax_domain)}</Row>
            <Row k="Lineage (source record)"><span className="text-sm">{na(src.lineage)}</span></Row>
            <Row k="GTDB taxonomy">
              <span className="text-sm">{na(g.taxonomy, "No GTDB match")}</span>
              {g.taxonomy ? (
                <span className="mt-1 block text-xs text-ink-2">
                  GTDB {na(g.release, "release not reported")} · match level {na(g.match_level)} · agreement {na(fmtNum(g.agreement, 3))} · genomes {na(g.n_genomes !== null ? fmtInt(g.n_genomes) : null)}
                </span>
              ) : null}
            </Row>
            <Row k="Length">{fmtInt(src.length)} aa</Row>
          </dl>
        </div>

        <div className="card p-4">
          <h3 className="text-base">Classification</h3>
          <dl className="mt-2">
            <Row k="Membership status" testId="ov-status">
              <MembershipBadge status={m.status} definition={statusDef.get(m.status)} /> <code className="text-xs text-ink-2">{m.status}</code>
              <span className="mt-1 block text-sm text-ink-2">{statusDef.get(m.status)}</span>
            </Row>
            <Row k="Membership score" testId="ov-score">
              {na(m.score !== null ? m.score.toFixed(4) : null)}
              <span className="mt-1 block text-xs text-ink-2">Score and status are reported separately; the status also reflects architecture rules and curation.</span>
            </Row>
            <Row k="Status reason">{na(m.status_reason)}</Row>
            {m.curated_override ? (
              <Row k="Curated override" testId="ov-curated">
                <FlagBadge tone="warn">curated</FlagBadge> {m.curated_override.rationale}
                <span className="mt-1 block text-xs text-ink-2">Rationale as recorded in {m.curated_override.source}.</span>
              </Row>
            ) : null}
            <Row k="Functional class" testId="ov-function">
              <FunctionLabel func={src.function.func_class} /> <code className="text-xs text-ink-2">{src.function.func_class}</code>
              <span className="mt-1 block text-sm text-ink-2">{funcDef.get(src.function.func_class)}</span>
            </Row>
            <Row k="Evidence level" testId="ov-evidence">
              <EvidenceBadge level={src.function.evidence_level} definition={evDef.get(src.function.evidence_level)} long />
              <span className="mt-1 block text-xs text-ink-2">How the functional class is supported; see Functional evidence.</span>
            </Row>
            <Row k="Clade (MR_RT_003)">
              <CladeBadge state={src.phylogeny.clade_state} cladeId={src.phylogeny.clade_id} tentativeId={src.phylogeny.tentative_clade_id} failing={caveats} />
            </Row>
            <Row k="Engineered construct" testId="ov-engineered">
              {src.engineering.is_engineered ? (
                <>
                  <FlagBadge tone="warn">engineered</FlagBadge> Not counted in corpus statistics.{" "}
                  {src.engineering.wild_type_acc ? <>Wild type: <a className="font-mono" href={href.record(src.engineering.wild_type_acc)} data-testid="wt-link">{src.engineering.wild_type_acc}</a></> : "Wild type not recorded."}
                </>
              ) : (
                "No"
              )}
            </Row>
          </dl>
        </div>
      </div>

      <SourcesTable entry={entry} src={src} e1Reps={e1Reps} />

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <div className="card p-4">
          <h3 className="text-base">Cross-references</h3>
          <ul className="mt-2 space-y-1 text-sm">
            <li>UniProtKB: <Ext href={`https://www.uniprot.org/uniprotkb/${encodeURIComponent(src.source_acc)}/entry`}>{src.source_acc}</Ext></li>
            <li>
              AlphaFold DB:{" "}
              {src.structures.afdb.status === "ok" && src.structures.afdb.model_id ? <Ext href={afdbEntryUrl(src.source_acc)}>{src.structures.afdb.model_id}</Ext> : <span className="text-ink-2">no model</span>}
            </li>
            <li>PDB: {src.structures.experimental.length ? `${src.structures.experimental.length} entr${src.structures.experimental.length === 1 ? "y" : "ies"} for this source record` : <span className="text-ink-2">none for this source record</span>}{entry.pdb_union.length !== src.structures.experimental.length ? ` (${entry.pdb_union.length} across all source records)` : ""}</li>
            {src.organism_id !== null ? <li>NCBI Taxonomy: <Ext href={`https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${src.organism_id}`}>{src.organism_id}</Ext></li> : null}
            {src.exact_duplicate_of ? <li>Exact duplicate of: <a className="font-mono" href={href.record(src.exact_duplicate_of)}>{src.exact_duplicate_of}</a></li> : null}
          </ul>
        </div>
        <div className="card p-4">
          <h3 className="text-base">Provenance</h3>
          <dl className="mt-2 text-sm">
            <Row k="Dataset release">v1.6.0 (frozen)</Row>
            <Row k="MRDB first release">{na(entry.first_release)}</Row>
            <Row k="Source added in release">{na(src.release_added)}</Row>
            <Row k="v1.6.0 function change">{na(src.function.v160_change, "None recorded")}</Row>
            <Row k="Sequence SHA-256"><code className="break-all text-xs">{entry.sequence_sha256}</code></Row>
          </dl>
        </div>
      </div>
    </Section>
  );
}

function SourcesTable({ entry, src, e1Reps }: { entry: MrdbEntry; src: SourceRecord; e1Reps: Set<string> }) {
  return (
    <div className="mt-6" data-testid="sources-block">
      <h3 className="text-base">Source records ({entry.n_source_records})</h3>
      <p className="mt-1 max-w-4xl text-sm text-ink-2">
        {entry.n_source_records > 1 ? (
          <>
            {entry.n_source_records} source accessions share the identical sequence of {entry.mrdb_acc}. Annotations, structures and publications on this page are shown for the
            selected source record and are not merged across sources. The <strong>MRDB representative</strong> ({entry.representative_source_acc}) is the source chosen to represent the
            sequence; an <strong>E1 representative</strong> is the experimentally characterized record used as the functional reference. They need not be the same record.
          </>
        ) : (
          <>One source accession has this sequence.</>
        )}
      </p>
      <div className="card relative mt-2 overflow-x-auto" role="region" aria-label="Source records" tabIndex={0}>
        <table className="data-table" data-testid="sources-table">
          <thead>
            <tr>
              <th scope="col">Source accession</th>
              <th scope="col">Role</th>
              <th scope="col">Organism</th>
              <th scope="col">Membership</th>
              <th scope="col">Evidence</th>
              <th scope="col" className="num">PDB</th>
              <th scope="col">AFDB</th>
            </tr>
          </thead>
          <tbody>
            {entry.sources.map((s) => {
              const cur = s.source_acc === src.source_acc;
              return (
                <tr key={s.source_acc} aria-current={cur ? "true" : undefined} className={cur ? "bg-accent-soft" : undefined} data-source={s.source_acc}>
                  <td>
                    {cur ? <strong className="font-mono">{s.source_acc} <span className="font-sans font-normal text-ink-2">(shown)</span></strong> : <a className="font-mono" href={href.record(s.source_acc)} data-testid="source-switch">{s.source_acc}</a>}
                  </td>
                  <td>
                    <span className="flex flex-wrap gap-1">
                      {s.is_mrdb_representative ? <FlagBadge tone="info" title="Source record chosen to represent this MRDB sequence">MRDB representative</FlagBadge> : null}
                      {e1Reps.has(s.source_acc) ? <FlagBadge tone="neutral" title="Experimentally characterized (E1) record used as the functional reference">E1 representative</FlagBadge> : null}
                      {s.engineering.is_engineered ? <FlagBadge tone="warn">engineered</FlagBadge> : null}
                      {!s.is_mrdb_representative && !e1Reps.has(s.source_acc) && !s.engineering.is_engineered ? <span className="text-ink-2">Source record</span> : null}
                    </span>
                  </td>
                  <td className="text-sm">{s.organism ?? <span className="text-ink-2">Not reported</span>}</td>
                  <td><MembershipBadge status={s.membership.status} /></td>
                  <td><EvidenceBadge level={s.function.evidence_level} /></td>
                  <td className="num">{s.structures.experimental.length}</td>
                  <td>{s.structures.afdb.status === "ok" ? "model" : <span className="text-ink-2">none</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
