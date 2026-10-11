import { href } from "../app/routes";
import { loadManifest, useResource } from "../data/loaders";
import { BUILD, buildLabel } from "../lib/buildInfo";

export function SiteFooter() {
  const m = useResource(loadManifest);
  const d = m.state === "ready" ? m.data : null;
  return (
    <footer className="mt-16 border-t border-line bg-surface">
      <div className="container-page grid gap-6 py-8 text-sm text-ink-2 md:grid-cols-3">
        <div>
          <p className="font-semibold text-ink">MicroRhodoDB</p>
          <p className="mt-1">An evidence-aware knowledgebase of microbial rhodopsins.</p>
          <p className="mt-2">
            <a href={href.about()}>About</a> <span aria-hidden="true">·</span> <a href={href.section("citation")}>Citation</a>{" "}
            <span aria-hidden="true">·</span> <a href={href.section("help")}>Help</a>
          </p>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1" data-testid="footer-release">
          <dt>Data release</dt>
          <dd className="text-ink">{d ? `v${d.dataset_release} (${d.release_date})` : "v1.6.0"}</dd>
          <dt>License</dt>
          <dd className="text-ink">{d?.license ?? "..."}</dd>
          <dt>Source DB</dt>
          <dd className="min-w-0 truncate font-mono text-xs leading-5 text-ink" title={d ? `SHA-256 ${d.source_db.sha256}` : undefined}>
            {d ? `${d.source_db.file} sha256:${d.source_db.sha256.slice(0, 12)}…` : "..."}
          </dd>
        </dl>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt>Website</dt>
          <dd className="text-ink" data-testid="footer-website-version">{d ? d.website_version : "..."}</dd>
          <dt>Data schema</dt>
          <dd className="text-ink">{d ? d.schema_version : "..."}</dd>
          <dt>Build</dt>
          <dd className="text-ink" data-testid="footer-build" title={BUILD.commit ? `Source commit ${BUILD.commit}` : undefined}>{buildLabel()}</dd>
        </dl>
      </div>
    </footer>
  );
}
