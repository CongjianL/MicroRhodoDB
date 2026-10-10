/** Typed accessors for exporter-owned summary values (UI never hard-codes metric values). */
import type { Clades, Summary } from "../data/types";

export type Metric = Summary["metrics"][number];
export type Distribution = Summary["distributions"][number];

export function metric(s: Summary, id: string): Metric {
  const m = s.metrics.find((x) => x.id === id);
  if (!m) throw new Error(`summary.json: metric ${id} missing`);
  return m;
}

export const mv = (s: Summary, id: string) => metric(s, id).value;

export function distribution(s: Summary, id: string): Distribution {
  const d = s.distributions.find((x) => x.id === id);
  if (!d) throw new Error(`summary.json: distribution ${id} missing`);
  return d;
}

export function distCount(d: Distribution, key: string | null): number {
  return d.items.find((i) => i.key === key)?.value ?? 0;
}

/** Level-1 clades whose IQ-TREE run1 support (bipartition-mapped) fails the predefined thresholds. */
export function failingClades(c: Clades) {
  return c.level1.filter((x) => !x.support_audit.iqtree_run1_meets_support_thresholds);
}

export function thresholdText(c: Clades): string {
  const r = c.clade_rule.level1;
  return `SH-aLRT \u2265 ${r.min_sh_alrt} and UFBoot \u2265 ${r.min_ufboot}`;
}

/** Short caveat text keyed by clade id, used by badges and banners. */
export function caveatMap(c: Clades): Map<string, string> {
  return new Map(
    failingClades(c).map((x) => [
      x.clade_id,
      `legacy v1.6.0 assignment; corrected IQ-TREE run1 support SH-aLRT ${x.support_audit.iqtree_run1_sh_alrt} / UFBoot ${x.support_audit.iqtree_run1_ufboot} fails the thresholds (${thresholdText(c)})`,
    ]),
  );
}
