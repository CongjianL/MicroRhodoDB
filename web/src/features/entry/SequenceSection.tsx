import { useState } from "react";
import { href } from "../../app/routes";
import { FlagBadge } from "../../components/Badges";
import { loadEvidenceIndex, useResource } from "../../data/loaders";
import type { MrdbEntry, SourceRecord } from "../../data/types";
import { fmtInt } from "../../lib/format";
import { fastaRecord, sequenceLines, variantsOf } from "../../lib/entry";
import { NOT_AVAILABLE, Row, Section, copyText, downloadText, fmtNum, na } from "./ui";

export function SequenceSection({ entry, src }: { entry: MrdbEntry; src: SourceRecord }) {
  const [copied, setCopied] = useState<string | null>(null);
  const lines = sequenceLines(src.sequence);
  const mo = src.motifs;
  const ar = src.architecture;
  const ev = useResource(loadEvidenceIndex, []);
  const variants = ev.state === "ready" ? variantsOf(ev.data.engineered, src.source_acc) : [];

  return (
    <Section id="sequence" title={<>Sequence and motifs <span className="text-base font-normal text-ink-2">({fmtInt(src.length)} aa)</span></>}>
      <div className="card p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={async () => setCopied((await copyText(src.sequence)) ? "Sequence copied." : "Copy failed; select the sequence manually.")}
          >
            Copy sequence
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => downloadText(`${src.source_acc}.fasta`, fastaRecord(entry, src))}>Download FASTA</button>
          <span role="status" aria-live="polite" className="text-sm text-ink-2">{copied}</span>
        </div>
        <div className="relative overflow-x-auto" role="region" aria-label={`Amino-acid sequence of ${src.source_acc}, ${src.length} residues`} tabIndex={0}>
          <pre className="font-mono text-[0.8125rem] leading-relaxed" data-testid="sequence" data-length={src.sequence.length}>
            {lines.map((l) => (
              <span key={l.start} className="block whitespace-pre">
                <span className="inline-block w-12 select-none pr-3 text-right text-ink-2" aria-hidden="true">{l.start}</span>
                {l.blocks.join(" ")}
              </span>
            ))}
          </pre>
        </div>
        <p className="mt-2 text-xs text-ink-2">Blocks of 10 residues; numbers give the position of the first residue on each line (source sequence numbering).</p>
      </div>

      <div className="mt-4 grid gap-6 xl:grid-cols-2">
        <div className="card p-4" data-testid="motifs">
          <h3 className="text-base">Motifs and retinal pocket</h3>
          <dl className="mt-2">
            <Row k="Helix-C motif">
              {na(mo.helixC_motif && <code>{mo.helixC_motif}</code>)}
              <span className="mt-1 block text-xs text-ink-2">Residues at BR positions 85/89/96 on helix C (TM3), read from the PF01036 alignment.</span>
            </Row>
            <Row k="Motif class">{na(mo.motif_class)}</Row>
            <Row k="Retinal-site residue">
              {na(mo.retinal_site_residue && <code>{mo.retinal_site_residue}</code>)}
              <span className="mt-1 block text-xs text-ink-2">Residue at PF01036 match state 210 (BR K216 retinal Schiff-base site); &quot;-&quot; = gap.</span>
            </Row>
            <Row k="Retinal-pocket string">
              {na(mo.pocket_string_br && <code className="break-all">{mo.pocket_string_br}</code>)}
              <span className="mt-1 block text-xs text-ink-2">BR-reference annotation: residues at the 20 retinal-pocket positions in BR-number order (&quot;-&quot; = gap). Mapping of these positions onto this sequence is not available in the v1.6.0 export.</span>
            </Row>
            <Row k="Pocket positions observed">{na(mo.n_pocket_observed)}</Row>
            <Row k="Pocket AFDB pLDDT (mean / min)">{mo.pocket_mean_plddt !== null ? `${fmtNum(mo.pocket_mean_plddt)} / ${na(fmtNum(mo.pocket_min_plddt))}` : na(null)}</Row>
          </dl>
        </div>
        <div className="card p-4" data-testid="architecture">
          <h3 className="text-base">Architecture</h3>
          <dl className="mt-2">
            <Row k="Primary architecture">{na(ar.arch_primary)}</Row>
            <Row k="Architecture class">{na(src.membership.architecture_class)}</Row>
            <Row k="Fusion">{ar.fusion_type && ar.fusion_type !== "none" ? <>{ar.fusion_type}{ar.fusion_partner_domains ? `: ${ar.fusion_partner_domains}` : ""}</> : na(ar.fusion_type === "none" ? "None" : null)}</Row>
            <Row k="Architecture flags">{ar.flags.length ? ar.flags.map((f) => <FlagBadge key={f}>{f}</FlagBadge>) : <span className="text-ink-2">None</span>}</Row>
            <Row k="Covers TM7">{src.membership.covers_TM7 === null ? na(null) : src.membership.covers_TM7 ? "Yes" : "No"}</Row>
            <Row k="Transmembrane segments"><span className="text-ink-2">{NOT_AVAILABLE} (not provided)</span></Row>
          </dl>
        </div>
      </div>

      {src.engineering.is_engineered || variants.length ? (
        <div className="card mt-4 p-4" data-testid="engineering-links">
          <h3 className="text-base">Engineered constructs</h3>
          {src.engineering.is_engineered ? (
            <p className="mt-1 text-sm">
              This source record is an engineered construct. Wild type:{" "}
              {src.engineering.wild_type_acc ? <a className="font-mono" href={href.record(src.engineering.wild_type_acc)}>{src.engineering.wild_type_acc}</a> : "not recorded"}.
              Mutated positions are not exported in v1.6.0.
            </p>
          ) : null}
          {variants.length ? (
            <div className="mt-1 text-sm" data-testid="variant-links">
              <p>{variants.length} engineered construct{variants.length === 1 ? "" : "s"} in the database list this record as wild type:</p>
              <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                {variants.map((v) => <li key={v}><a className="font-mono" href={href.record(v)}>{v}</a></li>)}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Section>
  );
}
