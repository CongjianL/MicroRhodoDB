import { Component, Suspense, lazy, useEffect, useLayoutEffect, useRef, type ReactNode } from "react";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { requestTitleFocus } from "../components/common";
import { useHash } from "./navigation";
import { canonicalRedirect, parseHash, routeTitle, type Route, type SectionPage } from "./routes";

/* Route-level code splitting: each page is its own chunk. */
const HomePage = lazy(() => import("../pages/HomePage"));
const BrowsePage = lazy(() => import("../pages/BrowsePage"));
const RecordPage = lazy(() => import("../pages/RecordPage"));
const AboutPage = lazy(() => import("../pages/AboutPage"));
const PhylogenyPage = lazy(() => import("../pages/PhylogenyPage"));
const CladePage = lazy(() => import("../pages/CladePage"));
const NotFoundPage = lazy(() => import("../pages/PlaceholderPage").then((m) => ({ default: m.NotFoundPage })));
/* PR-5 section pages. */
const StatisticsPage = lazy(() => import("../pages/StatisticsPage"));
const EvidencePage = lazy(() => import("../pages/EvidencePage"));
const StructuresPage = lazy(() => import("../pages/StructuresPage"));
const WatchlistPage = lazy(() => import("../pages/WatchlistPage"));
const SearchPage = lazy(() => import("../pages/SearchPage"));
const DownloadsPage = lazy(() => import("../pages/DownloadsPage"));
const MethodsPage = lazy(() => import("../pages/MethodsPage"));
const CitationPage = lazy(() => import("../pages/CitationPage"));
const HelpPage = lazy(() => import("../pages/HelpPage"));

function sectionPage(page: SectionPage, params: URLSearchParams) {
  switch (page) {
    case "statistics": return <StatisticsPage />;
    case "evidence": return <EvidencePage params={params} />;
    case "structures": return <StructuresPage params={params} />;
    case "watchlist": return <WatchlistPage />;
    case "search": return <SearchPage params={params} />;
    case "downloads": return <DownloadsPage />;
    case "methods": return <MethodsPage params={params} />;
    case "citation": return <CitationPage />;
    case "help": return <HelpPage />;
  }
}

class Boundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }
  render() {
    if (this.state.error) {
      return (
        <div className="container-page pt-6">
          <ErrorState error={this.state.error} retry={() => window.location.reload()} what="this page" />
        </div>
      );
    }
    return this.props.children;
  }
}

/** Identity of a "page" for focus/scroll handling: Browse query changes and record ?section=/?structure= are in-page state, not navigation. */
function pageKey(r: Route): string {
  switch (r.name) {
    case "browse": return "browse";
    case "record": return `record/${r.accession}`;
    case "phylogeny": return "phylogeny";
    case "clade": return `clade/${r.cladeId}`;
    case "section": return `section/${r.page}`;
    case "not-found": return `nf/${r.path}`;
    default: return r.name;
  }
}

function page(r: Route) {
  switch (r.name) {
    case "home": return <HomePage />;
    case "browse": return <BrowsePage params={r.params} />;
    case "record": return <RecordPage key={r.accession} accession={r.accession} params={r.params} />;
    case "about": return <AboutPage />;
    case "phylogeny": return <PhylogenyPage params={r.params} />;
    case "clade": return <CladePage key={r.cladeId} cladeId={r.cladeId} />;
    case "section": return sectionPage(r.page, r.params);
    case "not-found": return <NotFoundPage path={r.path} />;
  }
}

export function App() {
  const hash = useHash();
  const redirect = canonicalRedirect(hash);
  useLayoutEffect(() => {
    if (redirect) {
      const url = new URL(window.location.href);
      url.hash = redirect;
      window.history.replaceState(window.history.state, "", url.toString());
      window.dispatchEvent(new Event("mrdb:navigate"));
    }
  }, [redirect]);
  const route = parseHash(redirect ?? hash);
  const key = pageKey(route);
  const first = useRef(true);
  useEffect(() => {
    document.title = routeTitle(route);
    if (first.current) {
      first.current = false;
      return;
    }
    window.scrollTo(0, 0);
    requestTitleFocus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader route={route} />
      <main id="main" tabIndex={-1} className="flex-1 pb-4 outline-none">
        <Boundary resetKey={key}>
          <Suspense fallback={<div className="container-page pt-6"><LoadingSkeleton label="Loading page" /></div>}>{page(route)}</Suspense>
        </Boundary>
      </main>
      <SiteFooter />
    </div>
  );
}
