/**
 * Structure viewer panel of the Protein Entry page. Lives in the record chunk; Mol* itself is a
 * separate chunk imported only after the user clicks "Load 3D viewer" (or a "View in 3D" button).
 *
 * Controls are our own (style, ligand/retinal, colouring, reset, PNG snapshot, coordinate download);
 * the full Mol* plugin UI is not used. Residue highlighting is deliberately unavailable because
 * v1.6.0 provides no validated PDB chain/residue to UniProt mapping.
 */
import { useEffect, useId, useRef, useState } from "react";
import { releaseFileUrl } from "../../data/loaders";
import type { StructureOption } from "../../lib/entry";
import type { Coloring, LoadResult, MolViewer, Style } from "./molstarViewer";

type Phase =
  | { s: "idle" }
  | { s: "starting" }
  | { s: "loading"; key: string }
  | { s: "ready"; key: string; result: LoadResult }
  | { s: "error"; key: string | null; message: string; kind: string };

const PLDDT_LEGEND = [
  { label: "Very high (pLDDT > 90)", color: "#0053d6" },
  { label: "Confident (90 > pLDDT > 70)", color: "#65cbf3" },
  { label: "Low (70 > pLDDT > 50)", color: "#ffdb13" },
  { label: "Very low (pLDDT < 50)", color: "#ff7d45" },
];

async function absolute(urls: StructureOption["urls"]) {
  return Promise.all(urls.map(async (u) => ({ ...u, url: /^https?:/.test(u.url) ? u.url : new URL(await releaseFileUrl(u.url), window.location.href).toString() })));
}

export function StructureViewer({ options, selected, onSelect, activate, onActivated }: {
  options: StructureOption[];
  selected: StructureOption | null;
  onSelect: (o: StructureOption) => void;
  /** Incremented by "View in 3D" buttons elsewhere on the page: loads the viewer if not yet loaded. */
  activate: number;
  onActivated?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewer = useRef<MolViewer | null>(null);
  const abort = useRef<AbortController | null>(null);
  const [phase, setPhase] = useState<Phase>({ s: "idle" });
  const [style, setStyle] = useState<Style>("cartoon");
  const [coloring, setColoring] = useState<Coloring>(selected?.predicted ? "plddt-confidence" : "chain-id");
  const [showLigand, setShowLigand] = useState(true);
  const [busy, setBusy] = useState(false);
  const [downloadHref, setDownloadHref] = useState<string | null>(null);
  const pickId = useId();
  const statusId = useId();
  const started = phase.s !== "idle";

  // Absolute download URL (release models live under the versioned data directory).
  useEffect(() => {
    let alive = true;
    setDownloadHref(null);
    if (!selected) return;
    const u = selected.download.url;
    if (/^https?:/.test(u)) setDownloadHref(u);
    else releaseFileUrl(u).then((x) => alive && setDownloadHref(x), () => undefined);
    return () => {
      alive = false;
    };
  }, [selected]);

  useEffect(() => () => {
    abort.current?.abort();
    viewer.current?.dispose();
    viewer.current = null;
  }, []);

  async function ensureViewer(): Promise<MolViewer> {
    if (viewer.current) return viewer.current;
    setPhase({ s: "starting" });
    const mod = await import("./molstarViewer");
    const v = await mod.MolViewer.create(canvas.current!, host.current!);
    viewer.current = v;
    return v;
  }

  async function load(opt: StructureOption | null) {
    if (!opt) return;
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    const col: Coloring = opt.predicted ? "plddt-confidence" : "chain-id";
    try {
      const v = await ensureViewer();
      if (ctl.signal.aborted) return;
      setPhase({ s: "loading", key: opt.key });
      const urls = await absolute(opt.urls);
      const result = await v.load({ urls, rescalePlddt: opt.rescalePlddt, label: opt.label }, { style, coloring: col, showLigand }, ctl.signal);
      if (ctl.signal.aborted) return;
      setColoring(col === "plddt-confidence" && !result.plddtAvailable ? "chain-id" : col);
      setPhase({ s: "ready", key: opt.key, result });
      onActivated?.();
    } catch (e) {
      if (ctl.signal.aborted) return;
      const err = e as Error & { kind?: string };
      if (err.kind === "aborted") return;
      setPhase({ s: "error", key: opt.key, message: err.message, kind: err.kind ?? "error" });
    }
  }

  // Selection changes reload only once the viewer is running.
  useEffect(() => {
    if (started && selected) void load(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.key]);

  // External "View in 3D" requests.
  useEffect(() => {
    if (activate > 0 && !started) void load(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activate]);

  async function run(fn: (v: MolViewer) => Promise<unknown> | unknown) {
    if (!viewer.current) return;
    setBusy(true);
    try {
      await fn(viewer.current);
    } finally {
      setBusy(false);
    }
  }

  async function snapshot() {
    await run(async (v) => {
      const uri = await v.snapshot();
      const a = document.createElement("a");
      a.href = uri;
      a.download = `${selected?.key.replace(":", "_") ?? "structure"}.png`;
      a.click();
    });
  }

  if (!options.length) {
    return (
      <div className="card p-4 text-sm text-ink-2" data-testid="viewer-none">
        No experimental structure or predicted model is linked to this source record, so there is nothing to display in 3D.
      </div>
    );
  }

  const ready = phase.s === "ready";
  const statusText =
    phase.s === "idle" ? "3D viewer not loaded." :
    phase.s === "starting" ? "Starting the 3D viewer." :
    phase.s === "loading" ? `Loading ${selected?.label ?? "structure"}.` :
    phase.s === "ready" ? `Showing ${options.find((o) => o.key === phase.key)?.label ?? phase.key} (${(phase.result.bytes / 1024).toFixed(0)} KB, ${phase.result.ms} ms).` :
    `Could not display the structure. ${phase.message}`;
  const exp = options.filter((o) => o.group === "experimental");
  const pred = options.filter((o) => o.group !== "experimental");
  const isPred = !!selected?.predicted;

  return (
    <div className="card overflow-hidden" data-testid="structure-viewer" data-phase={phase.s} data-selected={selected?.key ?? ""}>
      <div className="flex flex-wrap items-end gap-3 border-b border-line p-3">
        <div className="min-w-0 flex-1 basis-64">
          <label htmlFor={pickId} className="field-label">Structure or model</label>
          <select
            id={pickId}
            className="field"
            value={selected?.key ?? ""}
            onChange={(e) => {
              const o = options.find((x) => x.key === e.target.value);
              if (o) onSelect(o);
            }}
            data-testid="structure-picker"
          >
            {exp.length ? (
              <optgroup label={`Experimental (PDB, ${exp.length})`}>
                {exp.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </optgroup>
            ) : null}
            {pred.length ? (
              <optgroup label="Predicted models">
                {pred.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </optgroup>
            ) : null}
          </select>
        </div>
        {!started ? (
          <button type="button" className="btn btn-primary" onClick={() => void load(selected)} data-testid="viewer-load">
            Load 3D viewer
          </button>
        ) : null}
      </div>

      {selected ? (
        <p className="border-b border-line px-3 py-2 text-sm text-ink-2" data-testid="viewer-detail">
          {isPred ? <strong className="text-ink">Predicted model, not an experimental structure. </strong> : null}
          {selected.detail}
        </p>
      ) : null}

      <div className="relative bg-white" style={{ height: "min(62vh, 30rem)", minHeight: "18rem" }}>
        <div ref={host} className="absolute inset-0" aria-hidden={!ready}>
          <canvas
            ref={canvas}
            className="block h-full w-full"
            role="img"
            aria-label={ready ? `3D view of ${selected?.label}. Drag to rotate, scroll or pinch to zoom.` : "3D viewer"}
            data-testid="viewer-canvas"
          />
        </div>
        {!ready ? (
          <div className="absolute inset-0 flex items-center justify-center bg-subtle/90 p-4 text-center">
            {phase.s === "error" ? (
              <div role="alert" className="max-w-md" data-testid="viewer-error">
                <p className="font-semibold text-danger">Could not display this structure.</p>
                <p className="mt-1 break-words text-sm">{phase.message}</p>
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  {phase.kind !== "webgl" ? (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load(selected)} data-testid="viewer-retry">Retry</button>
                  ) : null}
                  {selected?.external.map((x) => (
                    <a key={x.url} className="btn btn-secondary btn-sm" href={x.url} target="_blank" rel="noopener noreferrer">{x.label}</a>
                  ))}
                  {downloadHref ? <a className="btn btn-secondary btn-sm" href={downloadHref} download={selected?.download.filename}>Download coordinates</a> : null}
                </div>
              </div>
            ) : phase.s === "idle" ? (
              <div className="max-w-md text-sm text-ink-2">
                <p>The interactive viewer (Mol*) is loaded only on request to keep this page fast.</p>
                <button type="button" className="btn btn-primary mt-3" onClick={() => void load(selected)}>Load 3D viewer</button>
              </div>
            ) : (
              <p className="text-sm text-ink-2" aria-hidden="true">{statusText}</p>
            )}
          </div>
        ) : null}
      </div>

      <p id={statusId} role="status" aria-live="polite" className="sr-only" data-testid="viewer-status">{statusText}</p>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line p-3 text-sm">
        <fieldset className="flex flex-wrap items-center gap-1" disabled={!ready || busy}>
          <legend className="sr-only">Representation</legend>
          {(["cartoon", "surface", "ball-and-stick"] as Style[]).map((s) => (
            <button
              key={s}
              type="button"
              className={`btn btn-sm ${style === s ? "btn-primary" : "btn-secondary"}`}
              aria-pressed={style === s}
              onClick={() => {
                setStyle(s);
                void run((v) => v.setStyle(s));
              }}
            >
              {s === "cartoon" ? "Cartoon" : s === "surface" ? "Surface" : "Ball and stick"}
            </button>
          ))}
        </fieldset>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={showLigand}
            disabled={!ready || busy || (ready && !phase.result.hasLigand)}
            onChange={(e) => {
              setShowLigand(e.target.checked);
              void run((v) => v.setLigandVisible(e.target.checked));
            }}
          />
          Ligands and retinal{ready && !phase.result.hasLigand ? " (none in model)" : ""}
        </label>
        <label className="inline-flex items-center gap-2">
          Colour
          <select
            className="field w-auto"
            style={{ minHeight: "2.25rem" }}
            value={coloring}
            disabled={!ready || busy}
            onChange={(e) => {
              const c = e.target.value as Coloring;
              void run(async (v) => setColoring(await v.setColoring(c)));
            }}
            data-testid="viewer-coloring"
          >
            <option value="chain-id">By chain</option>
            {isPred && (!ready || phase.result.plddtAvailable) ? <option value="plddt-confidence">pLDDT confidence</option> : null}
          </select>
        </label>
        <div className="flex flex-wrap gap-1">
          <button type="button" className="btn btn-secondary btn-sm" disabled={!ready} onClick={() => viewer.current?.resetCamera()}>Reset view</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={!ready || busy} onClick={() => void snapshot()}>PNG snapshot</button>
          {downloadHref ? (
            <a className="btn btn-secondary btn-sm" href={downloadHref} download={selected?.download.filename} data-testid="viewer-download">Download coordinates</a>
          ) : null}
        </div>
      </div>

      {isPred && coloring === "plddt-confidence" ? (
        <div className="border-t border-line px-3 py-2 text-xs text-ink-2" data-testid="plddt-legend">
          <p className="mb-1 font-medium text-ink">pLDDT (model confidence per residue; not resolution)</p>
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
            {PLDDT_LEGEND.map((l) => (
              <li key={l.label} className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className="inline-block h-3 w-3 rounded-sm border border-line-strong" style={{ background: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>
          {selected?.rescalePlddt ? (
            <p className="mt-1">This release model stores pLDDT as a fraction (0-1) in the B-factor column; values are multiplied by 100 in the browser for display. The distributed file is unchanged.</p>
          ) : null}
        </div>
      ) : null}

      <p className="border-t border-line px-3 py-2 text-xs text-ink-2">
        Residue highlighting is not offered: v1.6.0 provides no validated PDB chain/residue to UniProt mapping.
        Viewer: <a href="https://molstar.org" target="_blank" rel="noopener noreferrer">Mol*</a> (MIT licence; Sehnal et al., Nucleic Acids Res 2021).
        Experimental coordinates are fetched from RCSB PDB; AlphaFold DB models from EMBL-EBI.
      </p>
    </div>
  );
}
