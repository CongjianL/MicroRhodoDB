/**
 * Help (#/help), spec section 10.5: how to use each page, how to read the main fields, common pitfalls,
 * and where to get support. Static text plus the maintenance placeholders from downloads.json (never filled in).
 */
import { href } from "../app/routes";
import { PageTitle } from "../components/common";
import { loadDownloads, useResource } from "../data/loaders";
import { safeExternalUrl } from "../lib/safe";

const FAQ: { id: string; q: string; a: React.ReactNode }[] = [
  {
    id: "member-vs-evidence",
    q: "What is the difference between membership status and evidence level?",
    a: <>Membership status (member, candidate, boundary family, heliorhodopsin, decoy/rejected) says whether a protein is a Type-I microbial rhodopsin by the release rules. Evidence level (E1–E5) says what kind of support exists for its <em>function</em> call. They are independent: an E1 protein is not a member because it is E1, and a member can be E5. See <a href={href.section("methods", "s=evidence")}>Methods</a>.</>,
  },
  {
    id: "counted",
    q: "Why are there 5,466 records but statistics use 5,460?",
    a: <>The engineered constructs are kept as records but excluded from counts (counts_eligible = 0). Every chart on <a href={href.section("statistics")}>Statistics</a> states which denominator it uses; some charts let you switch between counted and all records.</>,
  },
  {
    id: "mrdb-vs-source",
    q: "What is the difference between an MRDB accession and a source accession?",
    a: <>Source records are UniProtKB entries. Records with identical sequences share one MRDB accession (MRDB000001 …), so there are fewer MRDB accessions than source records. Both work in search and in record links (<code>#/record/MRDB000001</code> or <code>#/record/P02945</code>).</>,
  },
  {
    id: "tentative",
    q: "What does a tentative clade mean?",
    a: <>The placement model put the record in a clade but the placement failed quality control (distant placement, low confidence). Tentative placements are shown separately and are not counted as clade assignments. See <a href={href.section("methods", "s=phylogeny")}>Methods: clades</a>.</>,
  },
  {
    id: "sequence-search",
    q: "Can I use the sequence search to classify my protein?",
    a: <>No. The browser sequence search finds similar corpus sequences (top 10 after a 3-mer prefilter); it is not exhaustive and does not compute the membership score. The annotations next to each hit describe the corpus record, not your query. To score a protein with the frozen membership scorer, run <code>tools/mrdb_search.py</code> from the repository. See <a href={href.section("search", "mode=sequence")}>Sequence search</a>.</>,
  },
  {
    id: "watchlist",
    q: "Are watchlist proteins part of MicroRhodoDB?",
    a: <>No. The <a href={href.section("watchlist")}>novel-family watchlist</a> lists structure-similarity candidates kept for follow-up. They were not admitted to the corpus, have no membership status, evidence level or function, and are excluded from all statistics, Browse and search.</>,
  },
  {
    id: "structures",
    q: "Which structure should I trust on a record page?",
    a: <>Experimental PDB entries are listed as stored in the release; no chain-to-residue mapping is claimed. AlphaFold DB models are fetched from AlphaFold DB on request. The two release-distributed predicted models carry a provenance warning because their stored method and note disagree. The 3D viewer is loaded only when you open a structure.</>,
  },
  {
    id: "cite",
    q: "How do I cite the data?",
    a: <>Cite the data release (v1.6.0), not the website version. Copy-ready text is on <a href={href.section("citation")}>Citation</a>; checksummed files are on <a href={href.section("downloads")}>Downloads</a>.</>,
  },
];

const PAGES: [string, string, string][] = [
  ["Browse", href.browse(), "Filter all records by membership, function, evidence, clade, taxonomy, motif, structure and flags; export TSV or FASTA. Filters are kept in the URL, so a filtered view can be bookmarked or shared."],
  ["Record pages", href.record("MRDB000001"), "Everything stored for one MRDB accession and its source records: classification, evidence and publications, phylogeny, sequence and structures."],
  ["Phylogeny and clades", href.phylogeny(), "The MR_RT_003 reference tree, clade support and clade summary pages."],
  ["Statistics", href.section("statistics"), "Charts with their denominators and SQL; the recount button re-derives the charts from the record index."],
  ["Evidence Explorer", href.section("evidence"), "E1–E5 records by basis, E1 publications, curated overrides, conflicts, rules and validation."],
  ["Structures", href.section("structures"), "PDB entries, AlphaFold DB models and release predicted models, with a 3D viewer."],
  ["Search", href.section("search"), "Text and identifier search, and a browser sequence-similarity search."],
  ["Downloads", href.section("downloads"), "Release files with SHA-256 checksums, the reference package and the website data files."],
];

export default function HelpPage() {
  const dl = useResource(loadDownloads, []);
  const contact = dl.state === "ready" ? dl.data.maintenance_placeholders.find((m) => /contact/i.test(m.context)) : undefined;
  const repo = dl.state === "ready" ? dl.data.citation["repository-code"] : null;
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Help - MicroRhodoDB" lead="How to use the website and read its fields.">Help</PageTitle>

      <section aria-labelledby="help-pages" className="mb-8 max-w-4xl">
        <h2 id="help-pages" className="mb-3 text-xl">Pages</h2>
        <dl className="space-y-2 text-sm">
          {PAGES.map(([t, h, d]) => <div key={t}><dt className="font-medium"><a href={h}>{t}</a></dt><dd className="text-ink-2">{d}</dd></div>)}
        </dl>
      </section>

      <section aria-labelledby="help-faq" className="mb-8 max-w-4xl" data-testid="help-faq">
        <h2 id="help-faq" className="mb-3 text-xl">Frequently asked questions</h2>
        {FAQ.map((f) => (
          <details key={f.id} id={`faq-${f.id}`} className="card mb-2 p-3 text-sm">
            <summary className="cursor-pointer font-medium">{f.q}</summary>
            <p className="mt-2 leading-relaxed">{f.a}</p>
          </details>
        ))}
      </section>

      <section aria-labelledby="help-access" className="mb-8 max-w-4xl text-sm">
        <h2 id="help-access" className="mb-2 text-xl">Accessibility and browsers</h2>
        <p>All pages work with the keyboard (a “Skip to main content” link is the first focusable element). Charts have table equivalents, and colour is never the only cue. The website is static and needs a current browser with JavaScript; sequence search uses a Web Worker.</p>
      </section>

      <section aria-labelledby="help-support" className="mb-8 max-w-4xl text-sm" data-testid="help-support">
        <h2 id="help-support" className="mb-2 text-xl">Support and corrections</h2>
        <p>
          Report errors or request corrections through the {repo ? <a href={safeExternalUrl(`${repo}/issues`)} target="_blank" rel="noopener noreferrer">repository issue tracker</a> : "repository issue tracker"}.
          {" "}Contact address: {contact ? <span>{contact.status}</span> : "not supplied"}.
        </p>
      </section>
    </div>
  );
}
