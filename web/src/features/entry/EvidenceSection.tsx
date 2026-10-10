import { href } from "../../app/routes";
import { EvidenceBadge, FlagBadge, FunctionLabel } from "../../components/Badges";
import { loadEvidenceIndex, useResource } from "../../data/loaders";
import type { MrdbEntry, SourceRecord, Vocabulary } from "../../data/types";
import { EVIDENCE_LEVELS } from "../../lib/format";
import { Row, Section, fmtNum, na } from "./ui";

export function EvidenceSection({ entry, src, vocab }: { entry: MrdbEntry; src: SourceRecord; vocab: Vocabulary }) {
  const fn = src.function;
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const ev = useResource(loadEvidenceIndex, []);
  const idx = ev.state === "ready" ? ev.data : null;
  const overrideMembers = fn.override_rule && idx ? idx.override_rules[fn.override_rule]?.length : undefined;

  return (
    <Section id="evidence" title="Functional evidence" lead="The functional class and the evidence level are separate fields: the level says how the class is supported, not how likely it is.">
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="card p-4">
          <h3 className="text-base">Call for {src.source_acc}</h3>
          <dl className="mt-2">
            <Row k="Functional class"><FunctionLabel func={fn.func_class} /> <code className="text-xs text-ink-2">{fn.func_class}</code></Row>
            <Row k="Evidence level" testId="ev-level">
              <EvidenceBadge level={fn.evidence_level} definition={evDef.get(fn.evidence_level)} long />
              {fn.evidence_level === "E5" ? (
                <span className="mt-1 block text-sm" data-testid="ev-e5-note">E5 means the function is unassigned or uncertain. It is not evidence that the protein lacks a function.</span>
              ) : null}
            </Row>
            <Row k="Function basis">{na(fn.function_basis)}</Row>
            {fn.exp_class ? (
              <Row k="Experimental class (E1)">
                <code>{fn.exp_class}</code>
                <span className="mt-1 block text-xs text-ink-2">Class recorded from experimental characterization, as stored in v1.6.0.</span>
              </Row>
            ) : null}
            <Row k="E1 representative">
              {fn.e1_representative ? <a className="font-mono" href={href.record(fn.e1_representative)}>{fn.e1_representative}</a> : na(null, "Not applicable")}
              <span className="mt-1 block text-xs text-ink-2">Experimentally characterized record used as the functional reference; distinct from the MRDB representative ({entry.representative_source_acc}).</span>
            </Row>
            <Row k="E2 transfer reference">
              {fn.e2_ref ? <><a className="font-mono" href={href.record(fn.e2_ref)}>{fn.e2_ref}</a>{fn.e2_identity !== null ? ` · identity ${fmtNum(fn.e2_identity, 3)}` : ""}</> : na(null, "Not applicable")}
            </Row>
            <Row k="Clade function (E3/E4 reasoning)">
              {na(fn.clade_function)}
              {src.phylogeny.clade_function_source ? <span className="text-sm text-ink-2"> · from {src.phylogeny.clade_function_source}</span> : null}
            </Row>
            <Row k="Override rule">{fn.override_rule ? <><code>{fn.override_rule}</code>{overrideMembers !== undefined ? <span className="text-sm text-ink-2"> · applied to {overrideMembers} records</span> : null}</> : na(null, "None")}</Row>
            <Row k="v1.4 functional class">{na(fn.func_class_v14)}</Row>
          </dl>
        </div>

        <div className="space-y-4">
          <div className={`card p-4 ${fn.call_conflict ? "border-warn-line" : ""}`} data-testid="ev-conflict">
            <h3 className="text-base">Call conflict</h3>
            {fn.call_conflict ? (
              <p className="mt-1 text-sm"><FlagBadge tone="warn">conflict</FlagBadge> {na(fn.call_conflict_detail, "Detail not recorded")}</p>
            ) : (
              <p className="mt-1 text-sm">No call conflict recorded for this source record.</p>
            )}
            {idx?.function_conflict_rule ? <p className="mt-2 text-xs text-ink-2">Rule: {idx.function_conflict_rule}</p> : null}
          </div>
          {src.membership.curated_override ? (
            <div className="card p-4" data-testid="ev-curated">
              <h3 className="text-base">Curated membership override</h3>
              <p className="mt-1 text-sm">{src.membership.curated_override.rationale}</p>
            </div>
          ) : null}
          {src.engineering.is_engineered ? (
            <div className="card p-4" data-testid="ev-engineered">
              <h3 className="text-base">Engineered construct policy</h3>
              <p className="mt-1 text-sm">{idx?.engineered_policy ?? "Engineered constructs are excluded from counts."}</p>
            </div>
          ) : null}
          <div className="card p-4">
            <h3 className="text-base">Evidence levels</h3>
            <dl className="mt-1 text-sm">
              {EVIDENCE_LEVELS.map((l) => (
                <div key={l} className={`flex gap-2 py-1 ${l === fn.evidence_level ? "font-semibold" : ""}`}>
                  <dt><EvidenceBadge level={l} /></dt>
                  <dd>{evDef.get(l)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-ink-2">{vocab.evidence_note}</p>
          </div>
        </div>
      </div>
    </Section>
  );
}
