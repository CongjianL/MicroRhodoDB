/**
 * Pure page model for the Protein Entry page (#/record/<acc>). No React, no fetches: unit tested.
 *
 * - Deep-link parameters (?section=, ?structure=) and their canonical serialisation.
 * - Structure options for the viewer (experimental PDB, AlphaFold DB, release models) and the
 *   default selection rule: representative -> highest resolution -> first PDB; then AFDB; then release model.
 * - Experimental-structure table rows, filtering and sorting (focused source or union of all sources).
 * - Publication grouping (support first, separate from other link roles).
 * - pLDDT rescaling for release models stored as fractions (0-1) in the B-factor column.
 */
import type { MrdbEntry, PdbLink, PdbMethod, PredictedModel, PubLink, SourceRecord } from "../data/types";

export const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "sequence", label: "Sequence and motifs" },
  { id: "experimental", label: "Experimental structures" },
  { id: "predicted", label: "Predicted structures" },
  { id: "phylogeny", label: "Phylogenetic placement" },
  { id: "evidence", label: "Functional evidence" },
  { id: "publications", label: "Publications" },
] as const;
export type SectionId = (typeof SECTIONS)[number]["id"];
const SECTION_IDS = new Set<string>(SECTIONS.map((s) => s.id));

export type StructureSel = { kind: "pdb"; id: string } | { kind: "afdb" } | { kind: "pred" };

export interface RecordQuery {
  section: SectionId | null;
  structure: StructureSel | null;
}

const PDB_ID_RE = /^[0-9][A-Z0-9]{3}$/;

export function parseStructureParam(v: string | null): StructureSel | null {
  if (!v) return null;
  const s = v.trim();
  if (s.toLowerCase() === "afdb") return { kind: "afdb" };
  if (s.toLowerCase() === "pred") return { kind: "pred" };
  const m = /^pdb:([0-9A-Za-z]{4})$/.exec(s);
  if (m && PDB_ID_RE.test(m[1].toUpperCase())) return { kind: "pdb", id: m[1].toUpperCase() };
  return null;
}

export function structureParam(sel: StructureSel): string {
  return sel.kind === "pdb" ? `pdb:${sel.id}` : sel.kind;
}

export function parseRecordQuery(params: URLSearchParams): RecordQuery {
  const sec = params.get("section");
  return {
    section: sec && SECTION_IDS.has(sec) ? (sec as SectionId) : null,
    structure: parseStructureParam(params.get("structure")),
  };
}

/** Canonical query string (section first, then structure); empty when nothing is set. */
export function recordQueryString(q: Partial<RecordQuery>): string {
  const p = new URLSearchParams();
  if (q.section) p.set("section", q.section);
  if (q.structure) p.set("structure", structureParam(q.structure));
  return p.toString().replace(/%3A/gi, ":");
}

export const sameSel = (a: StructureSel | null, b: StructureSel | null) =>
  a === b || (!!a && !!b && a.kind === b.kind && (a.kind !== "pdb" || a.id === (b as { id: string }).id));

/* ---------------------------------------------------------------- structures */

export const PDB_METHOD_SHORT: Record<PdbMethod, string> = {
  "X-RAY DIFFRACTION": "X-ray",
  "ELECTRON MICROSCOPY": "Cryo-EM",
  "SOLUTION NMR": "Solution NMR",
  "ELECTRON CRYSTALLOGRAPHY": "Electron crystallography",
};

export function resolutionText(r: PdbLink["resolution_A"]): string {
  if (typeof r === "number") return `${r.toFixed(2)} Å`;
  if (r === "not_applicable") return "Not applicable (NMR)";
  return "Not reported";
}

export const pdbUrls = (id: string) => ({
  rcsb: `https://www.rcsb.org/structure/${id}`,
  pdbe: `https://www.ebi.ac.uk/pdbe/entry/pdb/${id.toLowerCase()}`,
  mmcif: `https://files.rcsb.org/download/${id}.cif`,
  bcif: `https://models.rcsb.org/v1/${id.toLowerCase()}/full?encoding=bcif`,
});

export const afdbEntryUrl = (acc: string) => `https://alphafold.ebi.ac.uk/entry/${encodeURIComponent(acc)}`;

/** Experimental entry from the focused source, or the union over all sources of an MRDB entry. */
export interface PdbRow extends PdbLink {
  /** Source accessions of this MRDB entry linked to the PDB entry (focused view: just the focused source). */
  sources: string[];
}

export function focusedRows(src: SourceRecord): PdbRow[] {
  return src.structures.experimental.map((p) => ({ ...p, sources: [src.source_acc] }));
}

/** Union of experimental links over all sources, one row per PDB ID (flags merged with OR). */
export function unionRows(entry: MrdbEntry): PdbRow[] {
  const by = new Map<string, PdbRow>();
  for (const s of entry.sources) {
    for (const p of s.structures.experimental) {
      const cur = by.get(p.pdb_id);
      if (cur) {
        cur.sources.push(s.source_acc);
        by.set(p.pdb_id, { ...cur, is_rep: cur.is_rep || p.is_rep, is_highest_res: cur.is_highest_res || p.is_highest_res });
      } else by.set(p.pdb_id, { ...p, sources: [s.source_acc] });
    }
  }
  return [...by.values()];
}

export type PdbSortKey = "pdb_id" | "method" | "resolution" | "year";
export interface PdbFilter {
  q: string;
  method: PdbMethod | "";
  retinal: "" | "yes" | "no";
  sort: PdbSortKey;
  dir: "asc" | "desc";
}
export const DEFAULT_PDB_FILTER: PdbFilter = { q: "", method: "", retinal: "", sort: "resolution", dir: "asc" };

const resNum = (r: PdbLink["resolution_A"]) => (typeof r === "number" ? r : Number.POSITIVE_INFINITY);

/** Filter then sort; ties always broken by PDB ID so the order is stable and deterministic. */
export function filterSortPdb(rows: PdbRow[], f: PdbFilter): PdbRow[] {
  const q = f.q.trim().toUpperCase();
  const out = rows.filter((r) => {
    if (f.method && r.method !== f.method) return false;
    if (f.retinal === "yes" && !r.has_retinal) return false;
    if (f.retinal === "no" && r.has_retinal) return false;
    if (q && !(r.pdb_id.includes(q) || r.title.toUpperCase().includes(q) || r.ligands.some((l) => l === q) || r.sources.some((s) => s === q))) return false;
    return true;
  });
  const sgn = f.dir === "asc" ? 1 : -1;
  const cmp = (a: PdbRow, b: PdbRow): number => {
    let d = 0;
    if (f.sort === "resolution") {
      // Entries without a numeric resolution (NMR, not reported) always sort last.
      const ra = resNum(a.resolution_A);
      const rb = resNum(b.resolution_A);
      if (ra === rb) d = 0;
      else if (!Number.isFinite(ra)) return 1;
      else if (!Number.isFinite(rb)) return -1;
      else d = (ra - rb) * sgn;
    } else if (f.sort === "year") d = (a.year - b.year) * sgn;
    else if (f.sort === "method") d = a.method.localeCompare(b.method) * sgn;
    else d = a.pdb_id.localeCompare(b.pdb_id) * sgn;
    return d || a.pdb_id.localeCompare(b.pdb_id);
  };
  return out.sort(cmp);
}

/* ---------------------------------------------------------------- viewer options */

export interface StructureOption {
  sel: StructureSel;
  key: string;
  label: string;
  group: "experimental" | "afdb" | "release";
  predicted: boolean;
  /** Candidate coordinate URLs tried in order (first success wins). Relative URLs are release files. */
  urls: { url: string; format: "mmcif" | "pdb"; binary: boolean }[];
  /** Release models store pLDDT as a fraction 0-1 in the B-factor column. */
  rescalePlddt: boolean;
  download: { url: string; filename: string };
  external: { label: string; url: string }[];
  detail: string;
}

export function pdbOption(p: PdbLink, sourceAcc: string): StructureOption {
  const u = pdbUrls(p.pdb_id);
  return {
    sel: { kind: "pdb", id: p.pdb_id },
    key: `pdb:${p.pdb_id}`,
    label: `${p.pdb_id} · ${PDB_METHOD_SHORT[p.method]}${typeof p.resolution_A === "number" ? ` ${p.resolution_A.toFixed(2)} Å` : ""}`,
    group: "experimental",
    predicted: false,
    urls: [
      { url: u.bcif, format: "mmcif", binary: true },
      { url: u.mmcif, format: "mmcif", binary: false },
    ],
    rescalePlddt: false,
    download: { url: u.mmcif, filename: `${p.pdb_id}.cif` },
    external: [{ label: "RCSB PDB", url: u.rcsb }, { label: "PDBe", url: u.pdbe }],
    detail: `Experimental structure (${p.method}), linked to ${sourceAcc}. ${p.title}`,
  };
}

export function afdbOption(src: SourceRecord): StructureOption | null {
  const a = src.structures.afdb;
  if (a.status !== "ok" || !a.model_url || !a.model_id) return null;
  return {
    sel: { kind: "afdb" },
    key: "afdb",
    label: `AlphaFold DB ${a.model_id}${a.version !== null ? ` (v${a.version})` : ""}`,
    group: "afdb",
    predicted: true,
    urls: [{ url: a.model_url, format: "pdb", binary: false }],
    rescalePlddt: false,
    download: { url: a.model_url, filename: a.model_url.split("/").pop() ?? `${a.model_id}.pdb` },
    external: [{ label: "AlphaFold DB entry", url: afdbEntryUrl(src.source_acc) }],
    detail: `Predicted model from AlphaFold DB for ${src.source_acc}; colour shows pLDDT confidence, not resolution.`,
  };
}

export function releaseOption(src: SourceRecord, m: PredictedModel): StructureOption {
  const filename = m.file.split("/").pop() ?? m.file;
  return {
    sel: { kind: "pred" },
    key: "pred",
    label: `Release model · ${m.method}`,
    group: "release",
    predicted: true,
    urls: [{ url: m.file, format: "pdb", binary: false }],
    rescalePlddt: m.bfactor_scale === "fraction_0_1",
    download: { url: m.file, filename },
    external: [],
    detail: `Predicted model distributed with the release for ${src.source_acc} (${m.method}); not an experimental structure.`,
  };
}

/** Viewer options for the focused source; `extraPdb` adds a union PDB entry selected from another source. */
export function structureOptions(entry: MrdbEntry, src: SourceRecord): StructureOption[] {
  const opts: StructureOption[] = [];
  const seen = new Set<string>();
  for (const p of src.structures.experimental) {
    opts.push(pdbOption(p, src.source_acc));
    seen.add(p.pdb_id);
  }
  for (const s of entry.sources) {
    if (s === src) continue;
    for (const p of s.structures.experimental) {
      if (seen.has(p.pdb_id)) continue;
      seen.add(p.pdb_id);
      opts.push(pdbOption(p, s.source_acc));
    }
  }
  const af = afdbOption(src);
  if (af) opts.push(af);
  const pm = src.structures.predicted[0];
  if (pm) opts.push(releaseOption(src, pm));
  return opts;
}

/** Default viewer selection: representative -> highest resolution -> first PDB; then AFDB; then release model. */
export function defaultStructure(src: SourceRecord): StructureSel | null {
  const exp = src.structures.experimental;
  const pick = exp.find((p) => p.is_rep) ?? exp.find((p) => p.is_highest_res) ?? exp[0];
  if (pick) return { kind: "pdb", id: pick.pdb_id };
  if (afdbOption(src)) return { kind: "afdb" };
  if (src.structures.predicted.length) return { kind: "pred" };
  return null;
}

/** Resolve a requested selection against the available options (unknown requests fall back to the default). */
export function resolveSelection(options: StructureOption[], requested: StructureSel | null, fallback: StructureSel | null): StructureOption | null {
  const find = (s: StructureSel | null) => (s ? options.find((o) => sameSel(o.sel, s)) ?? null : null);
  return find(requested) ?? find(fallback) ?? options[0] ?? null;
}

/**
 * Multiply B-factors (PDB columns 61-66) by 100 on ATOM/HETATM records, so that release models
 * storing pLDDT as a fraction 0-1 use the 0-100 scale expected by the pLDDT colour theme.
 * Applied in memory only; the distributed files are unchanged.
 */
export function rescalePlddt(pdb: string): string {
  return pdb
    .split("\n")
    .map((line) => {
      if (!(line.startsWith("ATOM  ") || line.startsWith("HETATM")) || line.length < 66) return line;
      const b = Number.parseFloat(line.slice(60, 66));
      if (!Number.isFinite(b)) return line;
      return line.slice(0, 60) + (b * 100).toFixed(2).padStart(6) + line.slice(66);
    })
    .join("\n");
}

/** Mean CA B-factor of a PDB text (used to check pLDDT scales). */
export function meanCaBfactor(pdb: string): number {
  let n = 0;
  let sum = 0;
  for (const line of pdb.split("\n")) {
    if (line.startsWith("ATOM  ") && line.slice(12, 16).trim() === "CA") {
      sum += Number.parseFloat(line.slice(60, 66));
      n++;
    }
  }
  return n ? sum / n : Number.NaN;
}

/* ---------------------------------------------------------------- publications */

export interface PubGroup {
  publication_id: number;
  title: string | null;
  journal: string | null;
  year: number | null;
  doi: string | null;
  pmid: string | null;
  links: PubLink[];
}

const groupBy = (links: PubLink[]): PubGroup[] => {
  const by = new Map<number, PubGroup>();
  for (const l of links) {
    let g = by.get(l.publication_id);
    if (!g) {
      g = { publication_id: l.publication_id, title: l.title, journal: l.journal, year: l.year, doi: l.doi, pmid: l.pmid, links: [] };
      by.set(l.publication_id, g);
    }
    g.links.push(l);
  }
  const out = [...by.values()];
  for (const g of out) g.links.sort((a, b) => a.assertion_id - b.assertion_id);
  // Newest first; publications without a year last; ties by publication_id (stable, deterministic).
  return out.sort((a, b) => (b.year ?? -1) - (a.year ?? -1) || a.publication_id - b.publication_id);
};

/** Support links (counts_as_support) first and kept apart from compilation/context/conflicting links. */
export function groupPublications(pubs: PubLink[]): { support: PubGroup[]; other: PubGroup[] } {
  return {
    support: groupBy(pubs.filter((p) => p.counts_as_support)),
    other: groupBy(pubs.filter((p) => !p.counts_as_support)),
  };
}

export const LINK_ROLE_LABEL: Record<string, string> = {
  support: "Support",
  compilation: "Compilation (not counted as support)",
  context: "Context (not counted as support)",
  conflicting_evidence: "Conflicting evidence",
  unresolvable_not_counted: "Unresolvable (not counted)",
  dropped: "Dropped",
  replaced: "Replaced",
};

/* ---------------------------------------------------------------- sequence */

/** Sequence split into blocks of 10 residues, 6 blocks per line, with the 1-based start of each line. */
export function sequenceLines(seq: string, block = 10, perLine = 6): { start: number; blocks: string[] }[] {
  const out: { start: number; blocks: string[] }[] = [];
  const width = block * perLine;
  for (let i = 0; i < seq.length; i += width) {
    const chunk = seq.slice(i, i + width);
    const blocks: string[] = [];
    for (let j = 0; j < chunk.length; j += block) blocks.push(chunk.slice(j, j + block));
    out.push({ start: i + 1, blocks });
  }
  return out;
}

export function fastaRecord(entry: MrdbEntry, s: SourceRecord): string {
  const header = `>${s.source_acc} ${entry.mrdb_acc}${s.protein_name ? ` ${s.protein_name}` : ""}${s.organism ? ` OS=${s.organism}` : ""} release=v1.6.0`;
  const lines = s.sequence.match(/.{1,60}/g) ?? [];
  return `${header}\n${lines.join("\n")}\n`;
}

export function fasta(entry: MrdbEntry, sources: SourceRecord[]): string {
  return sources.map((s) => fastaRecord(entry, s)).join("");
}

/** Wild-type -> engineered variants (source accessions), from evidence-index.json `engineered`. */
export function variantsOf(engineered: { source_acc: string; wild_type_acc: string }[], wt: string): string[] {
  return engineered.filter((e) => e.wild_type_acc === wt).map((e) => e.source_acc).sort();
}
