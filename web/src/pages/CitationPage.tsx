/**
 * How to cite (#/citation), spec section 10.5. Built only from CITATION.cff (downloads.json citation block).
 * The DOI is null in v1.6.0 (none minted; the maintainer chose to cite the GitHub Release) and is shown as
 * "none minted"; the website version is never cited as data.
 */
import { useState } from "react";
import { href } from "../app/routes";
import { Callout, PageTitle } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadDownloads, useResource } from "../data/loaders";
import type { Downloads } from "../data/types";
import { Ext, copyText } from "../features/entry/ui";
import { apa, authors, bibtex } from "../lib/citation";
import { safeExternalUrl } from "../lib/safe";

export default function CitationPage() {
  const res = useResource(loadDownloads, []);
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Citation - MicroRhodoDB" lead="Cite the data release you used. The citation is taken from CITATION.cff in the repository.">
        How to cite MicroRhodoDB
      </PageTitle>
      {res.state === "loading" ? <LoadingSkeleton /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the citation metadata" /> : null}
      {res.state === "ready" ? <Body d={res.data} /> : null}
    </div>
  );
}

function CopyBlock({ label, text, testId }: { label: string; text: string; testId: string }) {
  const [msg, setMsg] = useState("");
  return (
    <div className="card mb-4 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-base">{label}</h3>
        <button type="button" className="btn btn-secondary btn-sm print:hidden" data-testid={`${testId}-copy`}
          onClick={async () => setMsg((await copyText(text)) ? "Copied." : "Copy failed; select the text manually.")}>Copy</button>
      </div>
      <pre className="whitespace-pre-wrap break-words font-mono text-sm" data-testid={testId}>{text}</pre>
      <p className="sr-only" aria-live="polite">{msg}</p>
      {msg ? <p className="mt-1 text-xs text-ink-2" aria-hidden>{msg}</p> : null}
    </div>
  );
}

function Body({ d }: { d: Downloads }) {
  const c = d.citation;
  const cff = d.repository_documents.find((x) => x.path === d.citation_source);
  return (
    <div className="max-w-4xl">
      <dl className="mb-6 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm" data-testid="cite-fields">
        <dt className="text-ink-2">Title</dt><dd>{c.title}</dd>
        <dt className="text-ink-2">Authors</dt><dd>{authors(c).map((a) => `${a.given} ${a.family}`).join(", ")}</dd>
        <dt className="text-ink-2">Data release</dt><dd data-testid="cite-version">{c.version}</dd>
        <dt className="text-ink-2">Date released</dt><dd>{c["date-released"] ?? "not recorded"}</dd>
        <dt className="text-ink-2">Licence</dt><dd>{c.license ?? "not recorded"}</dd>
        <dt className="text-ink-2">DOI</dt><dd data-testid="cite-doi">{c.doi ?? "none minted for this release"}</dd>
        <dt className="text-ink-2">Repository</dt><dd>{c["repository-code"] ? <Ext href={c["repository-code"]}>{c["repository-code"]}</Ext> : "not recorded"}</dd>
        <dt className="text-ink-2">Source</dt><dd>{cff ? <Ext href={cff.url}>{d.citation_source}</Ext> : d.citation_source} (repository version used for this website build)</dd>
      </dl>

      {!c.doi ? (
        <Callout tone="warn" title="No DOI yet" testId="cite-no-doi">
          CITATION.cff for {d.release.tag} has no DOI. Until one is assigned, cite the release version and the repository URL, and state the release tag ({d.release.tag}) in your methods.
        </Callout>
      ) : null}

      <CopyBlock label="Reference (APA style)" text={apa(c)} testId="cite-apa" />
      <CopyBlock label="BibTeX" text={bibtex(c)} testId="cite-bibtex" />

      {c.message ? <p className="mb-4 text-sm [overflow-wrap:anywhere]"><span className="font-medium">From CITATION.cff:</span> {c.message}</p> : null}
      <p className="mb-4 text-sm text-ink-2" data-testid="cite-version-note">
        {d.version_note} The website version ({d.website_version}) is not a data version and should not be cited as one. Record-level pages state the release they were generated from.
      </p>
      <p className="mb-6 text-sm">
        When you use specific records, also cite the primary publications listed on their record pages and in the <a href={href.section("evidence", "s=pubs")}>Evidence Explorer</a>.
      </p>
      <div className="flex flex-wrap gap-2 print:hidden">
        <button type="button" className="btn btn-secondary" onClick={() => window.print()}>Print</button>
        {cff ? <a className="btn btn-secondary" href={safeExternalUrl(cff.url)} target="_blank" rel="noopener noreferrer">Open CITATION.cff</a> : null}
      </div>
    </div>
  );
}
