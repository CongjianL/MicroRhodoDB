import { useMemo } from "react";
import { all, loadClades, loadExplorer, loadNewick, useResource, type Resource } from "../../data/loaders";
import type { Clades } from "../../data/types";
import { buildExplorerTree, type XTree } from "./explorerModel";

export interface ExplorerData { tree: XTree; clades: Clades }

/** Load explorer.json + the frozen rooted Newick + clades.json and align them (throws on mismatch). */
export function useExplorerData(): Resource<ExplorerData> {
  const ex = useResource(loadExplorer);
  const nwk = useResource(loadNewick);
  const cl = useResource(loadClades);
  const r = all(ex, nwk, cl);
  return useMemo<Resource<ExplorerData>>(() => {
    if (r.state !== "ready") return r as Resource<ExplorerData>;
    const [e, n, c] = r.data;
    try {
      return { state: "ready", data: { tree: buildExplorerTree(n, e), clades: c } };
    } catch (err) {
      return { state: "error", error: err as Error, retry: () => window.location.reload() };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [r.state, r.state === "ready" ? r.data[0] : null, r.state === "ready" ? r.data[1] : null]);
}
