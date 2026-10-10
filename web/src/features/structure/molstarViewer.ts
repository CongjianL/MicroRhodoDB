/**
 * Compact canvas-only Mol* (molstar 5.13.1, MIT) wrapper for the Protein Entry viewer.
 * Loaded as a separate chunk on demand (dynamic import after the user clicks "Load 3D viewer");
 * never imported by Home, Browse or About. No Mol* UI components or styles are used.
 *
 * Coordinates are fetched here (not by Mol*) so timeouts, HTTP/CORS errors and the in-memory
 * pLDDT rescale of release models are under our control; parsed data are passed to Mol* as raw data.
 */
import { MAQualityAssessment } from "molstar/lib/extensions/model-archive/quality-assessment/behavior";
import { setSubtreeVisibility } from "molstar/lib/mol-plugin/behavior/static/state";
import { PluginContext } from "molstar/lib/mol-plugin/context";
import { DefaultPluginSpec, PluginSpec } from "molstar/lib/mol-plugin/spec";
import { Color } from "molstar/lib/mol-util/color";
import { rescalePlddt } from "../../lib/entry";

export type Style = "cartoon" | "surface" | "ball-and-stick";
export type Coloring = "chain-id" | "plddt-confidence";

export interface LoadSpec {
  urls: { url: string; format: "mmcif" | "pdb"; binary: boolean }[];
  rescalePlddt: boolean;
  label: string;
}

export interface LoadResult {
  /** URL that was actually used (first candidate that succeeded). */
  url: string;
  bytes: number;
  hasLigand: boolean;
  plddtAvailable: boolean;
  ms: number;
}

export class ViewerError extends Error {
  constructor(message: string, readonly kind: "network" | "http" | "timeout" | "parse" | "webgl" | "aborted") {
    super(message);
  }
}

/** Per-URL timeout. E2E tests may shorten it via window.__MRDB_VIEWER_TIMEOUT_MS (no effect otherwise). */
const timeoutMs = () => {
  const t = (globalThis as { __MRDB_VIEWER_TIMEOUT_MS?: unknown }).__MRDB_VIEWER_TIMEOUT_MS;
  return typeof t === "number" && t > 0 ? t : 30_000;
};

async function fetchCoords(u: LoadSpec["urls"][number], signal: AbortSignal): Promise<string | Uint8Array<ArrayBuffer>> {
  const ctl = new AbortController();
  const onAbort = () => ctl.abort();
  signal.addEventListener("abort", onAbort);
  const TIMEOUT_MS = timeoutMs();
  const timer = setTimeout(() => ctl.abort("timeout"), TIMEOUT_MS);
  try {
    let res: Response;
    try {
      res = await fetch(u.url, { signal: ctl.signal, mode: "cors", credentials: "omit" });
    } catch (e) {
      if (signal.aborted) throw new ViewerError("Loading cancelled", "aborted");
      if (ctl.signal.aborted) throw new ViewerError(`Timed out after ${TIMEOUT_MS / 1000} s while loading ${u.url}`, "timeout");
      throw new ViewerError(`Network or CORS error while loading ${u.url}`, "network");
    }
    if (!res.ok) throw new ViewerError(`HTTP ${res.status} while loading ${u.url}`, "http");
    if (u.binary) return new Uint8Array(await res.arrayBuffer());
    return await res.text();
  } catch (e) {
    if (e instanceof ViewerError) throw e;
    if (signal.aborted) throw new ViewerError("Loading cancelled", "aborted");
    if (ctl.signal.aborted) throw new ViewerError(`Timed out after ${TIMEOUT_MS / 1000} s while loading ${u.url}`, "timeout");
    throw new ViewerError(`Network or CORS error while loading ${u.url}`, "network");
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}

export class MolViewer {
  private plugin: PluginContext;
  private polymer: string | null = null;
  private ligand: string | null = null;
  private style: Style = "cartoon";
  private coloring: Coloring = "chain-id";
  private showLigand = true;

  private constructor(plugin: PluginContext) {
    this.plugin = plugin;
  }

  static async create(canvas: HTMLCanvasElement, container: HTMLDivElement): Promise<MolViewer> {
    const spec = DefaultPluginSpec();
    // pLDDT colour theme (registered by the ModelArchive quality-assessment behaviour).
    spec.behaviors.push(PluginSpec.Behavior(MAQualityAssessment));
    const plugin = new PluginContext(spec);
    await plugin.init();
    let ok = false;
    try {
      ok = await plugin.initViewerAsync(canvas, container);
    } catch {
      ok = false;
    }
    if (!ok || !plugin.canvas3d) {
      plugin.dispose();
      throw new ViewerError("WebGL is not available in this browser, so the 3D viewer cannot start.", "webgl");
    }
    plugin.canvas3d.setProps({
      renderer: { backgroundColor: Color(0xffffff) },
      camera: { helper: { axes: { name: "off", params: {} } } },
    });
    return new MolViewer(plugin);
  }

  async load(spec: LoadSpec, opts: { style: Style; coloring: Coloring; showLigand: boolean }, signal: AbortSignal): Promise<LoadResult> {
    const t0 = performance.now();
    let lastErr: ViewerError | null = null;
    let data: string | Uint8Array<ArrayBuffer> | null = null;
    let used: LoadSpec["urls"][number] | null = null;
    for (const u of spec.urls) {
      try {
        data = await fetchCoords(u, signal);
        used = u;
        break;
      } catch (e) {
        lastErr = e as ViewerError;
        if (lastErr.kind === "aborted") throw lastErr;
      }
    }
    if (!data || !used) throw lastErr ?? new ViewerError("No coordinate source", "network");
    if (spec.rescalePlddt && typeof data === "string") data = rescalePlddt(data);
    if (signal.aborted) throw new ViewerError("Loading cancelled", "aborted");

    const p = this.plugin;
    await p.clear();
    this.polymer = this.ligand = null;
    try {
      const raw = await p.builders.data.rawData({ data, label: spec.label });
      const traj = await p.builders.structure.parseTrajectory(raw, used.format);
      const model = await p.builders.structure.createModel(traj);
      const structure = await p.builders.structure.createStructure(model);
      const polymer = await p.builders.structure.tryCreateComponentStatic(structure, "polymer");
      const ligand = await p.builders.structure.tryCreateComponentStatic(structure, "ligand");
      this.polymer = polymer?.ref ?? null;
      this.ligand = ligand?.ref ?? null;
    } catch (e) {
      throw new ViewerError(`Could not parse coordinates from ${used.url}: ${(e as Error).message}`, "parse");
    }
    this.style = opts.style;
    this.showLigand = opts.showLigand;
    const plddtAvailable = this.plddtApplicable();
    this.coloring = opts.coloring === "plddt-confidence" && !plddtAvailable ? "chain-id" : opts.coloring;
    await this.rebuild();
    p.managers.camera.reset();
    return {
      url: used.url,
      bytes: typeof data === "string" ? data.length : data.byteLength,
      hasLigand: !!this.ligand,
      plddtAvailable,
      ms: Math.round(performance.now() - t0),
    };
  }

  private plddtApplicable(): boolean {
    const s = this.plugin.managers.structure.hierarchy.current.structures[0]?.cell.obj?.data;
    if (!s) return false;
    const theme = this.plugin.representation.structure.themes.colorThemeRegistry.get("plddt-confidence");
    return !!theme && theme.isApplicable({ structure: s });
  }

  private async rebuild() {
    const p = this.plugin;
    const b = p.state.data.build();
    for (const ref of [this.polymer, this.ligand]) {
      if (!ref) continue;
      for (const child of p.state.data.tree.children.get(ref).toArray()) b.delete(child);
    }
    await b.commit();
    const repr = p.builders.structure.representation;
    if (this.polymer) {
      const type = this.style === "surface" ? "molecular-surface" : this.style === "ball-and-stick" ? "ball-and-stick" : "cartoon";
      await repr.addRepresentation(this.polymer, { type, color: this.coloring } as never);
    }
    if (this.ligand) {
      await repr.addRepresentation(this.ligand, { type: "ball-and-stick", color: "element-symbol" } as never);
      setSubtreeVisibility(p.state.data, this.ligand, !this.showLigand);
    }
  }

  async setStyle(style: Style) {
    this.style = style;
    await this.rebuild();
  }

  async setColoring(c: Coloring) {
    this.coloring = c === "plddt-confidence" && !this.plddtApplicable() ? "chain-id" : c;
    await this.rebuild();
    return this.coloring;
  }

  setLigandVisible(v: boolean) {
    this.showLigand = v;
    if (this.ligand) setSubtreeVisibility(this.plugin.state.data, this.ligand, !v);
  }

  resetCamera() {
    this.plugin.managers.camera.reset();
  }

  async snapshot(): Promise<string> {
    const h = this.plugin.helpers.viewportScreenshot;
    if (!h) throw new Error("Snapshot is not available");
    return h.getImageDataUri();
  }

  dispose() {
    this.plugin.dispose();
  }
}
