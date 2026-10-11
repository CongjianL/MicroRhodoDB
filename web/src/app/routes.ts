/**
 * Typed hash-route contract (WEBSITE_REDESIGN_SPEC.md section 2).
 *
 * Hash routing keeps every URL refresh-safe on GitHub Pages under /MicroRhodoDB/site/.
 * Legacy routes preserved: #/record/<MRDB or source accession>, #/about, #/search;
 * #/novel redirects to #/watchlist. The legacy root #/ (old browse table) now opens Home,
 * which links to Browse.
 */

export type PlannedPage =
  | "structures"
  | "search"
  | "downloads"
  | "statistics"
  | "evidence"
  | "watchlist"
  | "methods"
  | "citation"
  | "help";

export type Route =
  | { name: "home" }
  | { name: "browse"; params: URLSearchParams }
  | { name: "record"; accession: string; params: URLSearchParams }
  | { name: "about" }
  | { name: "phylogeny"; params: URLSearchParams }
  | { name: "clade"; cladeId: string }
  | { name: "planned"; page: PlannedPage }
  | { name: "not-found"; path: string };

export const PLANNED_PAGES: Record<PlannedPage, { title: string; pr: string; summary: string }> = {
  structures: { title: "Structures", pr: "PR-5", summary: "Structure browser for experimental PDB entries and predicted models." },
  search: { title: "Sequence search", pr: "PR-5", summary: "Sequence-similarity search running in a Web Worker, with explicit method limits." },
  downloads: { title: "Downloads", pr: "PR-5", summary: "Release files (TSV, FASTA, SQLite, reference tree) with checksums." },
  statistics: { title: "Statistics", pr: "PR-5", summary: "Database composition and annotation coverage with explicit denominators." },
  evidence: { title: "Evidence explorer", pr: "PR-5", summary: "E1-E5 evidence, function basis, call conflicts and curated membership overrides." },
  watchlist: { title: "Novel-family watchlist", pr: "PR-5", summary: "Research-candidate layer kept separate from the corpus (not database records)." },
  methods: { title: "Methods", pr: "PR-5", summary: "Membership scoring, evidence ladder, phylogeny and placement methods." },
  citation: { title: "Citation", pr: "PR-5", summary: "How to cite MicroRhodoDB and its release files." },
  help: { title: "Help", pr: "PR-5", summary: "Usage notes and frequently asked questions." },
};

const PLANNED = new Set(Object.keys(PLANNED_PAGES));

/** Parse a location.hash value (e.g. "#/browse?evidence=E1") into a Route. */
export function parseHash(hash: string): Route {
  let h = hash.startsWith("#") ? hash.slice(1) : hash;
  if (h === "" || h === "/") return { name: "home" };
  if (!h.startsWith("/")) h = "/" + h;
  const qi = h.indexOf("?");
  const path = qi >= 0 ? h.slice(0, qi) : h;
  const query = qi >= 0 ? h.slice(qi + 1) : "";
  const parts = path.split("/").filter(Boolean).map(safeDecode);
  const [head, arg, ...rest] = parts;
  if (head === undefined) return { name: "home" };
  if (rest.length) return { name: "not-found", path };
  switch (head) {
    case "browse":
      return arg === undefined ? { name: "browse", params: new URLSearchParams(query) } : { name: "not-found", path };
    case "record":
      return arg ? { name: "record", accession: arg.trim().toUpperCase(), params: new URLSearchParams(query) } : { name: "not-found", path };
    case "about":
      return arg === undefined ? { name: "about" } : { name: "not-found", path };
    case "phylogeny":
      return arg === undefined ? { name: "phylogeny", params: new URLSearchParams(query) } : { name: "not-found", path };
    case "clade":
      return arg ? { name: "clade", cladeId: arg } : { name: "phylogeny", params: new URLSearchParams(query) };
    case "novel":
      return { name: "planned", page: "watchlist" };
    default:
      if (PLANNED.has(head) && arg === undefined) return { name: "planned", page: head as PlannedPage };
      return { name: "not-found", path };
  }
}

/** Legacy hashes that must be rewritten in the address bar (replaceState, no extra history entry). */
export function canonicalRedirect(hash: string): string | null {
  const h = hash.replace(/^#/, "");
  if (h === "/novel" || h.startsWith("/novel?") || h === "/novel/") return "#/watchlist";
  // Record accessions are case-insensitive; the address bar shows the canonical upper-case form.
  const m = /^\/record\/([^/?]+)(\?.*)?$/.exec(h);
  if (m) {
    const acc = safeDecode(m[1]).trim();
    const up = acc.toUpperCase();
    if (acc !== up && (MRDB_RE.test(up) || UNIPROT_RE.test(up))) return `#/record/${encodeURIComponent(up)}${m[2] ?? ""}`;
  }
  return null;
}

function safeDecode(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export const href = {
  home: () => "#/",
  browse: (query = "") => (query ? `#/browse?${query.replace(/^\?/, "")}` : "#/browse"),
  record: (acc: string, query = "") => `#/record/${encodeURIComponent(acc)}${query ? `?${query.replace(/^\?/, "")}` : ""}`,
  about: () => "#/about",
  phylogeny: (query = "") => (query ? `#/phylogeny?${query.replace(/^\?/, "")}` : "#/phylogeny"),
  clade: (id: string) => `#/clade/${encodeURIComponent(id)}`,
  planned: (p: PlannedPage) => `#/${p}`,
};

export function routeTitle(r: Route): string {
  switch (r.name) {
    case "home": return "MicroRhodoDB - microbial rhodopsin knowledgebase";
    case "browse": return "Browse records - MicroRhodoDB";
    case "record": return `${r.accession} - MicroRhodoDB`;
    case "about": return "About - MicroRhodoDB";
    case "phylogeny": return "Phylogeny - MicroRhodoDB";
    case "clade": return `${r.cladeId} - MicroRhodoDB`;
    case "planned": return `${PLANNED_PAGES[r.page].title} (planned) - MicroRhodoDB`;
    case "not-found": return "Page not found - MicroRhodoDB";
  }
}

/** Accession patterns used by the universal search box. */
export const MRDB_RE = /^MRDB\d{6}$/;
export const UNIPROT_RE = /^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$/;
export const PDB_RE = /^[1-9][A-Z0-9]{3}$/;
export const CLADE_RE = /^MR_CLD3_(?:\d{3}|B\d{2})$/;
export const SUBCLADE_RE = /^MR_CLD3_(?:\d{3}|B\d{2})\.\d{2}$/;

/**
 * Universal search routing (Home and header search). Pure function; unit tested.
 * Accessions open the record route (which resolves source accessions and reports unknown ones);
 * everything else opens Browse over all records (engineered constructs included) so nothing is hidden.
 */
export function routeForQuery(raw: string): string {
  const q = raw.trim();
  if (!q) return href.browse();
  const up = q.toUpperCase();
  if (MRDB_RE.test(up) || UNIPROT_RE.test(up)) return href.record(up);
  const base = new URLSearchParams({ group: "all", eng: "1" });
  if (PDB_RE.test(up) && /[A-Z]/.test(up)) base.set("pdbid", up);
  else if (CLADE_RE.test(up)) base.set("clade", up);
  else if (SUBCLADE_RE.test(up)) base.set("sub", up);
  else base.set("q", q);
  return href.browse(base.toString());
}
