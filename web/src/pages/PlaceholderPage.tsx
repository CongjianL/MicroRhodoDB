/** Clearly labelled placeholders for destinations implemented in later PRs, plus Not Found. */
import { PLANNED_PAGES, href, type PlannedPage } from "../app/routes";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { PageTitle, SearchBox } from "../components/common";
import { ErrorState, LoadingSkeleton, PlannedNotice } from "../components/States";
import { loadClades, useResource } from "../data/loaders";
import { fmtInt } from "../lib/format";

export function PlaceholderPage({ page }: { page: PlannedPage }) {
  const p = PLANNED_PAGES[page];
  return (
    <div className="container-page pt-6" data-testid={`planned-${page}`}>
      <PageTitle docTitle={`${p.title} (planned) - MicroRhodoDB`}>{p.title}</PageTitle>
      <PlannedNotice page={page} />
    </div>
  );
}

/** #/clade/<id>: minimal factual summary from clades.json; the Clade Entry page itself is PR-4. */
export function CladePage({ cladeId }: { cladeId: string }) {
  const res = useResource(loadClades);
  return (
    <div className="container-page pt-6">
      {res.state === "loading" ? <LoadingSkeleton /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} /> : null}
      {res.state === "ready" ? (() => {
        const c = res.data.level1.find((x) => x.clade_id === cladeId) ?? res.data.subclades.find((x) => x.clade_id === cladeId);
        if (!c) return <NotFoundPage path={`/clade/${cladeId}`} />;
        const a = c.support_audit;
        const isSub = c.level === 2;
        return (
          <div data-testid="clade-page">
            <PageTitle docTitle={`${c.clade_id} - MicroRhodoDB`} eyebrow={<span className="font-mono">{c.clade_id}</span>}>{c.name ?? c.clade_id}</PageTitle>
            <dl className="card mb-4 grid max-w-3xl gap-x-4 gap-y-1 p-4 text-sm sm:grid-cols-[14rem_minmax(0,1fr)]">
              <dt className="text-ink-2">Level</dt><dd>{isSub ? `Subclade of ${c.parent_clade_id}` : "kind" in c && c.kind === "backbone_group" ? "Backbone group" : "Level-1 clade"}</dd>
              <dt className="text-ink-2">Tips in MR_RT_003</dt><dd>{fmtInt(c.n_tips)}</dd>
              <dt className="text-ink-2">Support (IQ-TREE run1, by bipartition)</dt><dd>SH-aLRT {a.iqtree_run1_sh_alrt} / UFBoot {a.iqtree_run1_ufboot}{a.iqtree_run1_meets_support_thresholds ? "" : " (fails thresholds)"}</dd>
            </dl>
            {!isSub ? <div className="mb-4 max-w-3xl"><CladeSupportNotice clades={res.data} only={[c.clade_id]} /></div> : null}
            <p className="mb-4">
              <a className="btn btn-secondary btn-sm" href={href.browse(`group=all&eng=1&${isSub ? "sub" : "clade"}=${c.clade_id}`)}>Browse records in {c.clade_id}</a>
            </p>
            <PlannedNotice page="phylogeny" />
          </div>
        );
      })() : null}
    </div>
  );
}

export function NotFoundPage({ path }: { path: string }) {
  return (
    <div className="container-page pt-6" data-testid="not-found">
      <PageTitle docTitle="Page not found - MicroRhodoDB">Page not found</PageTitle>
      <p className="max-w-3xl text-ink-2">
        There is no page at <code className="text-ink">#{path}</code>. Record links have the form <code>#/record/MRDB000001</code> or <code>#/record/P02945</code>.
      </p>
      <div className="mt-5 max-w-2xl"><SearchBox size="md" label="Search MicroRhodoDB" /></div>
      <p className="mt-4 text-sm"><a href={href.home()}>Home</a> · <a href={href.browse()}>Browse</a></p>
    </div>
  );
}
