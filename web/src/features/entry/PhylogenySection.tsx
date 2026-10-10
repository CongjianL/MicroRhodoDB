import { useMemo, useState } from "react";
import { href } from "../../app/routes";
import { CladeBadge, FlagBadge } from "../../components/Badges";
import { CladeSupportNotice } from "../../components/CladeSupportNotice";
import { ErrorState, LoadingSkeleton } from "../../components/States";
import { loadNewick, loadTips, useResource } from "../../data/loaders";
import type { Clades, MrdbEntry, SourceRecord, Tips, Vocabulary } from "../../data/types";
import { CLADE_STATE_LABEL } from "../../lib/format";
import { thresholdText } from "../../lib/summary";
import { OUTGROUP_KEY, TREE_RADIUS, TreePreview, buildTreeModel, type TreeHighlight } from "../tree/TreePreview";
import { Row, Section, fmtNum, na } from "./ui";

interface Placement {
  best_edge?: string | null;
  best_lwr?: number | null;
  best_pendant?: number | null;
  lwr_weighted_pendant?: number | null;
  n_credible95?: number | null;
  placement_qc?: string | null;
  clade_call?: string | null;
  clade_call_qc?: string | null;
  subclade_call?: string | null;
  subclade_id?: string | null;
  subclade_lwr?: number | null;
  model_tag?: string | null;
  track?: string | null;
  tree_id: string;
}

/** Which tip / clade arc to highlight on the reference-tree preview. */
export function treeHighlight(entry: MrdbEntry, src: SourceRecord, tips: Tips): TreeHighlight | null {
  const ph = src.phylogeny;
  if (ph.is_reference_tip) {
    const t = tips.tips.find((x) => x.tip === src.source_acc) ?? tips.tips.find((x) => x.mrdb_acc === entry.mrdb_acc);
    if (t) return { tip: t.tip, group: null, label: `reference tip ${t.tip}` };
  }
  if (ph.clade_state === "outgroup_placed") return { tip: null, group: OUTGROUP_KEY, label: "placed in the heliorhodopsin outgroup (arc only; not a tree leaf)" };
  const g = ph.clade_state === "tentative" ? ph.tentative_clade_id : ph.clade_id;
  if (g) return { tip: null, group: g, label: `${ph.clade_state === "tentative" ? "tentative placement near" : "placed in"} ${g} (clade arc only; not a tree leaf)` };
  return null;
}

export function PhylogenySection({ entry, src, clades, vocab, caveats }: { entry: MrdbEntry; src: SourceRecord; clades: Clades; vocab: Vocabulary; caveats: Map<string, string> }) {
  const ph = src.phylogeny;
  const pl = ph.placement as Placement | null;
  const stateDef = new Map(vocab.clade_state.map((c) => [c.state, c.definition])).get(ph.clade_state);
  const cladeKey = ph.clade_state === "tentative" ? ph.tentative_clade_id : ph.clade_id;
  const clade = cladeKey ? clades.level1.find((c) => c.clade_id === cladeKey) : undefined;
  const [showTree, setShowTree] = useState(false);

  return (
    <Section id="phylogeny" title="Phylogenetic placement" lead={<>Reference tree MR_RT_003 (472 tips). Clade scheme MR_CLD3. The interactive phylogeny explorer is planned (<a href={href.planned("phylogeny")}>PR-4</a>).</>}>
      {cladeKey && caveats.has(cladeKey) ? <div className="mb-4"><CladeSupportNotice clades={clades} only={[cladeKey]} /></div> : null}
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="card p-4">
          <h3 className="text-base">Assignment</h3>
          <dl className="mt-2">
            <Row k="Placement state" testId="ph-state">
              {CLADE_STATE_LABEL[ph.clade_state]} <code className="text-xs text-ink-2">{ph.clade_state}</code>
              {stateDef ? <span className="mt-1 block text-sm text-ink-2">{stateDef}</span> : null}
            </Row>
            <Row k={ph.clade_state === "tentative" ? "Tentative clade" : "Clade"}>
              <CladeBadge state={ph.clade_state} cladeId={ph.clade_id} tentativeId={ph.tentative_clade_id} failing={caveats} />
              {ph.clade_state === "tentative" ? <span className="mt-1 block text-sm text-ink-2">Tentative: the placement is near this clade but does not meet the confident-assignment criteria. It is not a confident assignment.</span> : null}
            </Row>
            <Row k="Clade name">
              {na(ph.clade_state === "tentative" ? ph.tentative_clade_name : ph.clade_name)}
              {cladeKey ? <> <a href={href.clade(cladeKey)} className="whitespace-nowrap text-sm" data-testid="record-clade-link">Clade summary</a></> : null}
            </Row>
            <Row k="Subclade">{na(ph.subclade_id, "None")}</Row>
            <Row k="Clade source">{na(ph.clade_source)}{ph.clade_lwr !== null ? <span className="text-sm text-ink-2"> · clade LWR {fmtNum(ph.clade_lwr, 3)}</span> : null}</Row>
            <Row k="Reference-tree tip" testId="ph-tip">
              {ph.is_reference_tip ? <>Yes{ph.tip_role ? <> <FlagBadge>{ph.tip_role}</FlagBadge></> : null}</> : "No: placed onto the fixed reference tree"}
            </Row>
            {clade ? (
              <Row k="Clade support (corrected run1)" testId="ph-support">
                SH-aLRT {clade.support_audit.iqtree_run1_sh_alrt} / UFBoot {clade.support_audit.iqtree_run1_ufboot}{" "}
                {clade.support_audit.iqtree_run1_meets_support_thresholds ? <FlagBadge tone="info">meets thresholds</FlagBadge> : <FlagBadge tone="warn">fails thresholds</FlagBadge>}
                <span className="mt-1 block text-xs text-ink-2">Thresholds: {thresholdText(clades)}. Values from the original IQ-TREE run mapped to the rooted tree by bipartition.</span>
              </Row>
            ) : null}
          </dl>
        </div>

        <div className="card p-4" data-testid="placement-table">
          <h3 className="text-base">Placement details</h3>
          {pl ? (
            <>
              <dl className="mt-2 text-sm">
                <Row k="Tree / model">{pl.tree_id}{pl.model_tag ? ` · ${pl.model_tag}` : ""}</Row>
                <Row k="Best edge">{na(pl.best_edge)}</Row>
                <Row k="Best LWR">{na(fmtNum(pl.best_lwr, 3))}</Row>
                <Row k="Edges in 95% credible set">{na(pl.n_credible95)} <span className="text-ink-2">(the set members are not exported)</span></Row>
                <Row k="Pendant length (best / LWR-weighted)">{na(fmtNum(pl.best_pendant, 4))} / {na(fmtNum(pl.lwr_weighted_pendant, 4))}</Row>
                <Row k="Placement QC">{na(pl.placement_qc)}</Row>
                <Row k="Clade call (QC)">{na(pl.clade_call)}{pl.clade_call_qc ? ` (${pl.clade_call_qc})` : ""}</Row>
                <Row k="Subclade call">{na(pl.subclade_call)}{pl.subclade_id ? ` · ${pl.subclade_id}` : ""}{pl.subclade_lwr !== null && pl.subclade_lwr !== undefined ? ` · LWR ${fmtNum(pl.subclade_lwr, 3)}` : ""}</Row>
                {pl.track ? <Row k="Track">{pl.track}</Row> : null}
              </dl>
              <p className="mt-2 text-xs text-ink-2">A placement is not a reconstructed tree leaf: the sequence was placed onto the fixed reference tree, which was not re-inferred. Values are shown as recorded in v1.6.0.</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-ink-2">{ph.is_reference_tip ? "This record is a tip of the reference tree; no placement was needed." : "No placement recorded for this source record."}</p>
          )}
        </div>
      </div>

      <div className="card mt-4 p-4" data-testid="mini-tree">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base">Position on the reference tree</h3>
          {!showTree ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowTree(true)} data-testid="mini-tree-show">Show on reference tree</button> : null}
        </div>
        {showTree ? <MiniTree entry={entry} src={src} clades={clades} /> : <p className="mt-1 text-sm text-ink-2">Loads the 472-tip tree preview (about 15 KB compressed) on request.</p>}
      </div>
    </Section>
  );
}

function MiniTree({ entry, src, clades }: { entry: MrdbEntry; src: SourceRecord; clades: Clades }) {
  const res = useResource(() => Promise.all([loadNewick(), loadTips()]), []);
  const built = useMemo(() => {
    if (res.state !== "ready") return null;
    const [nwk, tips] = res.data;
    return { model: buildTreeModel(nwk, tips, TREE_RADIUS), hl: treeHighlight(entry, src, tips) };
  }, [res, entry, src]);
  if (res.state === "loading") return <LoadingSkeleton label="Loading reference tree" lines={3} />;
  if (res.state === "error") return <ErrorState error={res.error} retry={res.retry} what="the reference tree" />;
  if (!built) return null;
  return (
    <div className="mt-2 grid items-start gap-4 md:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <div className="mx-auto w-full max-w-[26rem]">
        <TreePreview model={built.model} clades={clades} highlight={built.hl ?? undefined} idPrefix="record-tree" />
      </div>
      <div className="text-sm">
        {built.hl ? (
          <p data-testid="mini-tree-caption">
            {built.hl.tip ? <>The marked circle is reference tip <span className="font-mono">{built.hl.tip}</span>.</> : <>The outlined ring segment is {built.hl.label}. The record itself is not drawn as a leaf.</>}
          </p>
        ) : (
          <p data-testid="mini-tree-caption">This record has no clade or reference-tip position to mark ({CLADE_STATE_LABEL[src.phylogeny.clade_state].toLowerCase()}).</p>
        )}
        <p className="mt-2 text-ink-2">Branch lengths to scale; ring segments are level-1 clades and backbone groups; hatched segments fail the corrected clade-support thresholds.</p>
      </div>
    </div>
  );
}
