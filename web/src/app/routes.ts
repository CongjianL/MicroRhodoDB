/**
 * Typed hash-route contract (WEBSITE_REDESIGN_SPEC.md section 2).
 *
 * Hash routing keeps every URL refresh-safe on GitHub Pages under /MicroRhodoDB/site/.
 * Legacy routes preserved: #/record/<MRDB or source accession>, #/about, #/search (now the PR-5 Search page);
 * #/novel redirects to #/watchlist. The legacy root #/ (old browse table) now opens Home,
 * which links to Browse.
 */

export type SectionPage =
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
  | { name: "section"; page: SectionPage; params: URLSearchParams }
  | { name: "not-found"; path: string };

/** Section pages implemented in PR-5 (titles are used for navigation, <title> and headings). */
export const SECTION_PAGES: Record<SectionPage, { title: string; nav: string; summary: string }> = {
  structures: { title: "Structure explorer", nav: "Structures", summary: "Experimental PDB entries, AlphaFold DB models and release models, with provenance." },
  search: { title: "Search", nav: "Search", summary: "Text search across records and an in-browser sequence-similarity search with stated limits." },
  downloads: { title: "Downloads", nav: "Downloads", summary: "Release files, reference package and repository documents with SHA-256 checksums." },
  statistics: { title: "Statistics", nav: "Statistics", summary: "Database composition and annotation coverage with explicit denominators and SQL provenance." },
  evidence: { title: "Evidence explorer", nav: "Evidence", summary: "E1-E5 evidence, function-call basis, conflicts, curated membership overrides and validation." },
  watchlist: { title: "Novel-family watchlist", nav: "Watchlist", summary: "Research candidates not admitted to the corpus, with screening funnel and limitations." },
  methods: { title: "Methods", nav: "Methods", summary: "Membership scoring, evidence ladder, phylogeny, placement, validation and website derivation." },
  citation: { title: "Citation", nav: "Citation", summary: "How to cite a specific MicroRhodoDB data release." },
  help: { title: "Help", nav: "Help", summary: "How to use the website, and answers to common questions." },
};

const SECTIONS = new Set(Object.keys(SECTION_PAGES));

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
      return { name: "section", page: "watchlist", params: new URLSearchParams() };
    default:
      if (SECTIONS.has(head) && arg === undefined) return { name: "section", page: head as SectionPage, params: new URLSearchParams(query) };
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
  section: (p: SectionPage, query = "") => `#/${p}${query ? `?${query.replace(/^\?/, "")}` : ""}`,
};

export function routeTitle(r: Route): string {
  switch (r.name) {
    case "home": return "MicroRhodoDB - microbial rhodopsin knowledgebase";
    case "browse": return "Browse records - MicroRhodoDB";
    case "record": return `${r.accession} - MicroRhodoDB`;
    case "about": return "About - MicroRhodoDB";
    case "phylogeny": return "Phylogeny - MicroRhodoDB";
    case "clade": return `${r.cladeId} - MicroRhodoDB`;
    case "section": return `${SECTION_PAGES[r.page].title} - MicroRhodoDB`;
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
