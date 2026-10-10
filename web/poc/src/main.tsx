// PR-0 proof of concept only. Not production code.
// Verifies that phylotree.js and Mol* load REAL MicroRhodoDB assets inside a Vite + React + TS build
// served under the production base path /MicroRhodoDB/site/.
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

declare global { interface Window { __poc: Record<string, unknown> } }
window.__poc = {};

function TreePoc() {
  const ref = useRef<HTMLDivElement>(null);
  const [msg, setMsg] = useState("loading tree");
  useEffect(() => {
    (async () => {
      const t0 = performance.now();
      const { phylotree } = await import("phylotree");
      await import("phylotree/dist/phylotree.css");
      const nwk = (await (await fetch(`${import.meta.env.BASE_URL}data/MR_RT_003.rooted.treefile`)).text()).trim();
      const tree = new phylotree(nwk);
      const tips: string[] = []; const support: string[] = [];
      tree.traverse_and_compute((n: any) => {
        if (!n.children || n.children.length === 0) tips.push(n.data.name);
        else if (n.data.name) support.push(n.data.name);
      });
      const radial = location.hash.includes("radial");
      const r = tree.render({ container: ref.current!, width: 900, height: radial ? 900 : 4000,
        "left-right-spacing": "fit", "top-bottom-spacing": "fit", "is-radial": radial,
        "show-scale": true, "align-tips": false, zoom: true, "font-size": 7 } as any);
      ref.current!.appendChild(r.show());
      const ms = Math.round(performance.now() - t0);
      const svgTips = ref.current!.querySelectorAll(".node text, text.phylotree-node-text").length;
      window.__poc.tree = { tips: tips.length, uniqueTips: new Set(tips).size, supportLabels: support.length,
        supportExample: support.slice(0, 3), svgTipTexts: svgTips, renderMs: ms, radial,
        firstTips: tips.slice(0, 3) };
      setMsg(`tree: ${tips.length} tips, ${support.length} support labels, ${ms} ms`);
    })().catch((e) => { window.__poc.treeError = String(e); setMsg("tree error: " + e); });
  }, []);
  return <div><p id="tree-status">{msg}</p><div id="tree" ref={ref} /></div>;
}

const ASSETS = {
  pdb: { url: "https://models.rcsb.org/v1/1c3w/full?encoding=bcif", format: "mmcif", binary: true,
         label: "PDB 1C3W (linked to P02945 in protein_pdb)" },
  afdb: { url: "https://alphafold.ebi.ac.uk/files/AF-P02945-F1-model_v6.pdb", format: "pdb", binary: false,
          label: "AF-P02945-F1 v6 (afdb_model.model_url)" },
} as const;

function StructurePoc() {
  const ref = useRef<HTMLDivElement>(null);
  const [msg, setMsg] = useState("Mol* not loaded (lazy)");
  const which = (location.hash.split("/")[2] || "pdb") as keyof typeof ASSETS;
  useEffect(() => {
    (async () => {
      const t0 = performance.now();
      const [{ createPluginUI }, { renderReact18 }, { DefaultPluginUISpec }] = await Promise.all([
        import("molstar/lib/mol-plugin-ui"), import("molstar/lib/mol-plugin-ui/react18"),
        import("molstar/lib/mol-plugin-ui/spec")]);
      await import("molstar/lib/mol-plugin-ui/skin/light.scss");
      const plugin = await createPluginUI({ target: ref.current!, render: renderReact18,
        spec: { ...DefaultPluginUISpec(), layout: { initial: { isExpanded: false, showControls: false } } } });
      const a = ASSETS[which];
      const data = await plugin.builders.data.download({ url: a.url, isBinary: a.binary }, { state: { isGhost: true } });
      const traj = await plugin.builders.structure.parseTrajectory(data, a.format as any);
      await plugin.builders.structure.hierarchy.applyPreset(traj, "default");
      const s = plugin.managers.structure.hierarchy.current.structures;
      const st = s[0]?.cell.obj?.data;
      const ms = Math.round(performance.now() - t0);
      window.__poc.structure = { asset: which, url: a.url, nStructures: s.length,
        atoms: st ? st.elementCount : 0, units: st ? st.units.length : 0, loadMs: ms };
      setMsg(`${a.label}: ${st?.elementCount} atoms, ${ms} ms`);
    })().catch((e) => { window.__poc.structureError = String(e); setMsg("structure error: " + e); });
  }, [which]);
  return <div><p id="structure-status">{msg}</p>
    <div ref={ref} style={{ position: "relative", width: 900, height: 600 }} /></div>;
}

function App() {
  const route = location.hash || "#/tree";
  return <main style={{ fontFamily: "Liberation Sans, Arial, sans-serif" }}>
    <h1 style={{ fontSize: 16 }}>MicroRhodoDB website PR-0 PoC (not production)</h1>
    {route.startsWith("#/structure") ? <StructurePoc /> : <TreePoc />}
  </main>;
}
window.addEventListener("hashchange", () => location.reload());
createRoot(document.getElementById("root")!).render(<App />);
