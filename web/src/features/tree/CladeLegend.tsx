/** Clade table for the tree preview: every level-1 clade / backbone group with its corrected support. */
import { href } from "../../app/routes";
import type { Clades } from "../../data/types";
import { fmtInt } from "../../lib/format";
import { thresholdText } from "../../lib/summary";

export function CladeLegend({ clades, colorOf }: { clades: Clades; colorOf?: Map<string, string> }) {
  return (
    <div className="card overflow-hidden">
      <p id="clade-legend-cap" className="border-b border-line px-3 py-2 text-sm text-ink-2">
        {clades.display}. Support: IQ-TREE run1 SH-aLRT / UFBoot for the same bipartition; threshold {thresholdText(clades)}.
      </p>
      <div className="max-h-[34rem] overflow-auto" tabIndex={0} role="region" aria-labelledby="clade-legend-cap">
        <table className="data-table legend-table" data-testid="clade-legend" aria-describedby="clade-legend-cap">
          <thead>
            <tr>
              <th scope="col" className="lc-clade">Clade</th>
              <th scope="col" className="num hidden sm:table-cell">Tips</th>
              <th scope="col" className="num lc-rec" title="Source records assigned (confident) + tentative placements">Records</th>
              <th scope="col" className="lc-sup">Support</th>
            </tr>
          </thead>
          <tbody>
            {clades.level1.map((c) => {
              const a = c.support_audit;
              const ok = a.iqtree_run1_meets_support_thresholds;
              return (
                <tr key={c.clade_id} data-clade={c.clade_id} className={ok ? undefined : "bg-warn-soft"}>
                  <td className="sm:min-w-[11rem]">
                    <div className="flex items-start gap-2">
                      <span
                        aria-hidden="true"
                        className="mt-1 inline-block h-3 w-3 shrink-0 rounded-sm border border-white"
                        style={ok ? { background: colorOf?.get(c.clade_id) ?? "#c3ced9" } : { background: "repeating-linear-gradient(45deg,#b45309 0 2px,#fff7ed 2px 4px)", borderColor: "#b45309" }}
                      />
                      <span className="min-w-0">
                        <a href={href.browse(`group=all&eng=1&clade=${c.clade_id}`)} className="font-mono text-[0.8125rem]">{c.clade_id}</a>
                        {c.kind === "backbone_group" ? <span className="badge badge-neutral ml-1 align-middle">backbone group</span> : null}
                        <span className="block text-[0.8125rem] leading-snug text-ink-2">{c.name ?? "Unnamed"}</span>
                        <span className="block text-xs text-ink-2 sm:hidden">{fmtInt(c.n_tips_in_tree)} tips</span>
                      </span>
                    </div>
                  </td>
                  <td className="num hidden sm:table-cell">{fmtInt(c.n_tips_in_tree)}</td>
                  <td className="num">
                    {fmtInt(c.n_records_confident)}
                    {c.n_records_tentative ? (
                      <a className="block text-xs italic" href={href.browse(`group=all&eng=1&clade=${c.clade_id}&tent=1`)} title="Including tentative placements">
                        +{fmtInt(c.n_records_tentative)} tentative
                      </a>
                    ) : null}
                  </td>
                  <td>
                    <span className="tabular whitespace-nowrap" data-testid={`legend-support-${c.clade_id}`}>{a.iqtree_run1_sh_alrt} / {a.iqtree_run1_ufboot}</span>
                    {ok ? null : <span className="badge badge-warn mt-1 block w-fit whitespace-normal sm:ml-1 sm:inline-flex">fails thresholds</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
