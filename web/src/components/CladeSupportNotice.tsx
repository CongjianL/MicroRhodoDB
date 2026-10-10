/**
 * Disclosure for level-1 clades whose corrected (bipartition-mapped IQ-TREE run1) support fails the
 * predefined thresholds. All numbers come from clades.json; currently only MR_CLD3_017 qualifies.
 */
import type { Clades } from "../data/types";
import { failingClades, thresholdText } from "../lib/summary";
import { Callout } from "./common";

export function CladeSupportNotice({ clades, only, extra, compact = false }: {
  clades: Clades;
  only?: string[];
  extra?: React.ReactNode;
  compact?: boolean;
}) {
  const fails = failingClades(clades).filter((c) => !only || only.includes(c.clade_id));
  if (!fails.length) return null;
  return (
    <Callout tone="warn" title="Phylogenetic uncertainty" testId="clade-support-notice">
      {fails.map((c) => (
        <p key={c.clade_id} className={compact ? "" : "mb-1"}>
          <span className="font-mono">{c.clade_id}</span>
          {c.name ? <>{" "}&mdash; {c.name} &mdash;</> : ""} is retained as a <strong>legacy v1.6.0 assignment</strong>. Its corrected support, taken from
          the original IQ-TREE run and mapped to the rooted tree by bipartition, is{" "}
          <strong data-testid={`support-${c.clade_id}`}>
            SH-aLRT {c.support_audit.iqtree_run1_sh_alrt} / UFBoot {c.support_audit.iqtree_run1_ufboot}
          </strong>
          , which fails the predefined clade thresholds ({thresholdText(clades)}).
          {compact ? null : " Clade membership is not changed here; treat assignments and tentative placements to this clade as uncertain."}
        </p>
      ))}
      {extra}
    </Callout>
  );
}
