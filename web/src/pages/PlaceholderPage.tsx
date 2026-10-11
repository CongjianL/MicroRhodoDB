/** Not Found page (the PR-2..PR-4 "planned" placeholders were replaced by real pages in PR-5). */
import { href } from "../app/routes";
import { PageTitle, SearchBox } from "../components/common";

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
