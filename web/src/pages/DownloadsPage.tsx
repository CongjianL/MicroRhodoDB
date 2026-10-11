/**
 * Downloads (#/downloads), spec section 10.4. Everything comes from downloads.json (written by
 * tools/export_web_data.py from the release SHA256SUMS, refpkg SHA256SUMS, CITATION.cff and the
 * repository). export_manifest.json (website-file checksums, ~0.8 MB) is linked, never loaded here.
 */
import { href } from "../app/routes";
import { Callout, PageTitle } from "../components/common";
import { TableRegion } from "../components/Paged";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadDownloads, releaseFileUrl, useResource } from "../data/loaders";
import type { Downloads } from "../data/types";
import { Ext, copyText } from "../features/entry/ui";
import { fmtBytes } from "../lib/citation";
import { fmtInt } from "../lib/format";
import { useState } from "react";

async function load() {
  const d = await loadDownloads();
  const paths = [...d.website_derived.map((w) => w.path), "export_manifest.json"];
  const urls = await Promise.all(paths.map((p) => releaseFileUrl(p)));
  return { d, urls: Object.fromEntries(paths.map((p, i) => [p, urls[i]])) as Record<string, string> };
}

export default function DownloadsPage() {
  const res = useResource(load, []);
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Downloads - MicroRhodoDB" lead="Release files with SHA-256 checksums, the reference package, and the derived files used by this website.">
        Downloads
      </PageTitle>
      {res.state === "loading" ? <LoadingSkeleton lines={8} /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the download list" /> : null}
      {res.state === "ready" ? <Body d={res.data.d} urls={res.data.urls} /> : null}
    </div>
  );
}

function Sha({ sha }: { sha: string }) {
  const [done, setDone] = useState(false);
  return (
    <span className="whitespace-nowrap">
      <code className="text-xs" title={sha}>{sha.slice(0, 12)}…</code>{" "}
      <button type="button" className="btn btn-secondary btn-sm !px-2 !py-0 text-xs" aria-label={`Copy SHA-256 ${sha}`}
        onClick={async () => setDone(await copyText(sha))}>{done ? "Copied" : "Copy"}</button>
    </span>
  );
}

function Body({ d, urls }: { d: Downloads; urls: Record<string, string> }) {
  const r = d.release;
  const notInGit = d.release_files.filter((f) => !f.in_git_at_tag);
  const totalBytes = d.release_files.reduce((s, f) => s + f.bytes, 0);
  return (
    <>
      <section aria-labelledby="dl-release" className="mb-8" data-testid="dl-release">
        <h2 id="dl-release" className="mb-2 text-xl">Data release {r.tag}</h2>
        <dl className="grid max-w-3xl grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-ink-2">Release</dt><dd><Ext href={r.url}>{r.tag} on GitHub</Ext></dd>
          <dt className="text-ink-2">Release date</dt><dd>{r.release_date ?? "not recorded"} <span className="text-ink-2">(release-database metadata; CITATION.cff gives date-released {d.citation["date-released"] ?? "not recorded"})</span></dd>
          <dt className="text-ink-2">Licence</dt>
          <dd data-testid="dl-license">
            {r.license ?? "not recorded"} <span className="text-ink-2">(as stored in the release metadata)</span>. The repository{" "}
            <Ext href={d.repository_documents.find((x) => x.path === "LICENSE")?.url ?? r.url}>LICENSE</Ext> file contains the CC BY 4.0 text; CITATION.cff declares {d.citation.license ?? "no licence"}.
          </dd>
          <dt className="text-ink-2">Checksums</dt><dd><Ext href={r.sha256sums_url}>SHA256SUMS</Ext> ({fmtInt(d.release_files.length)} files, {fmtBytes(totalBytes)} in total)</dd>
        </dl>
        <p className="mt-3 max-w-3xl text-sm text-ink-2" data-testid="dl-version-note">{d.version_note} This website is version {d.website_version}; cite the data release (see <a href={href.section("citation")}>Citation</a>).</p>
        {notInGit.length ? (
          <Callout tone="warn" title="Release database file" testId="dl-db-note">
            {notInGit.map((f) => <span key={f.path}><code>{f.path}</code> ({fmtBytes(f.bytes)}) </span>)}
            is listed in SHA256SUMS but is not stored in the git repository at the tag. It is distributed as a GitHub Release asset; the exact asset file name was not verified by the exporter, so check the
            {" "}<Ext href={r.url}>release page</Ext> and compare the downloaded file with the SHA-256 below.
          </Callout>
        ) : null}
      </section>

      <section aria-labelledby="dl-files" className="mb-8">
        <h2 id="dl-files" className="mb-1 text-xl">Release files</h2>
        <p className="mb-3 text-sm text-ink-2">Paths are relative to <code>releases/{r.tag}/</code>. Links open the file at the release tag; verify downloads with <code>sha256sum -c SHA256SUMS</code>.</p>
        <TableRegion label="Release files" testId="dl-release-files">
          <table className="data-table">
            <thead><tr><th scope="col">File</th><th scope="col" className="num">Size</th><th scope="col">SHA-256</th><th scope="col">Distribution</th></tr></thead>
            <tbody>
              {d.release_files.map((f) => (
                <tr key={f.path} data-testid={`dl-file-${f.path}`}>
                  <td>{f.in_git_at_tag ? <Ext href={f.url}>{f.path}</Ext> : <code>{f.path}</code>}</td>
                  <td className="num">{fmtBytes(f.bytes)}</td>
                  <td><Sha sha={f.sha256} /></td>
                  <td className="text-xs">{f.distribution}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <section aria-labelledby="dl-refpkg" className="mb-8">
        <h2 id="dl-refpkg" className="mb-1 text-xl">Reference package MR_RT_003</h2>
        <p className="mb-3 text-sm text-ink-2">Tree, alignment and model files used for phylogenetic placement ({fmtInt(d.refpkg_files.length)} files with SHA-256 in <code>refpkg/MR_RT_003/SHA256SUMS</code>).</p>
        <details>
          <summary className="cursor-pointer text-sm text-accent">Show {d.refpkg_files.length} reference-package files</summary>
          <TableRegion label="Reference package files" testId="dl-refpkg-files">
            <table className="data-table">
              <thead><tr><th scope="col">File</th><th scope="col">SHA-256</th></tr></thead>
              <tbody>{d.refpkg_files.map((f) => <tr key={f.path}><td><Ext href={f.url}>{f.path}</Ext></td><td><Sha sha={f.sha256} /></td></tr>)}</tbody>
            </table>
          </TableRegion>
        </details>
      </section>

      <section aria-labelledby="dl-docs" className="mb-8">
        <h2 id="dl-docs" className="mb-3 text-xl">Repository documents and tools</h2>
        <TableRegion label="Repository documents" testId="dl-docs-table">
          <table className="data-table">
            <thead><tr><th scope="col">File</th><th scope="col">Description</th><th scope="col" className="num">Size</th><th scope="col">SHA-256</th></tr></thead>
            <tbody>{d.repository_documents.map((f) => <tr key={f.path}><td><Ext href={f.url}>{f.path}</Ext></td><td>{f.description}</td><td className="num">{fmtBytes(f.bytes)}</td><td><Sha sha={f.sha256} /></td></tr>)}</tbody>
          </table>
        </TableRegion>
      </section>

      <section aria-labelledby="dl-web" className="mb-8">
        <h2 id="dl-web" className="mb-1 text-xl">Website data files</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2" data-testid="dl-web-note">
          {d.website_derived_note} <a href={urls["export_manifest.json"]} data-testid="dl-export-manifest">export_manifest.json</a> (SHA-256 of every website file).
        </p>
        <TableRegion label="Website data files" testId="dl-web-files">
          <table className="data-table">
            <thead><tr><th scope="col">File</th><th scope="col">Contents</th></tr></thead>
            <tbody>{d.website_derived.map((w) => <tr key={w.path}><td><a href={urls[w.path]} download>{w.path}</a></td><td>{w.description}</td></tr>)}</tbody>
          </table>
        </TableRegion>
        <p className="mt-2 text-sm">Filtered subsets (TSV, FASTA, unique-sequence FASTA) can be exported from <a href={href.browse()}>Browse</a>.</p>
      </section>

      <section aria-labelledby="dl-history" className="mb-8">
        <h2 id="dl-history" className="mb-3 text-xl">Release history</h2>
        <TableRegion label="Release history" testId="dl-history">
          <table className="data-table">
            <thead><tr><th scope="col">Release</th><th scope="col">Release notes</th><th scope="col">Checksums</th></tr></thead>
            <tbody>
              {d.release_history.map((h) => (
                <tr key={h.release}>
                  <td><Ext href={h.url}>{h.release}</Ext>{h.current ? <span className="ml-2 text-xs font-semibold">(current)</span> : null}</td>
                  <td>{h.release_notes ?? <span className="text-ink-2">none in the repository</span>}</td>
                  <td>{h.has_sha256sums ? "SHA256SUMS" : <span className="text-ink-2">none</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <section aria-labelledby="dl-maint" className="mb-8" data-testid="dl-maintenance">
        <h2 id="dl-maint" className="mb-1 text-xl">Long-term availability</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">The maintenance plan (MAINTENANCE.md) still contains placeholders. They are shown as recorded; nothing has been filled in by this website.</p>
        <ul className="max-w-3xl list-disc space-y-1 pl-5 text-sm">
          {d.maintenance_placeholders.map((m, i) => (
            <li key={i}><span className="font-mono text-xs">{m.context}</span> — expected: {m.hint}. <span className="font-medium">Status: {m.status}.</span></li>
          ))}
        </ul>
      </section>
    </>
  );
}
