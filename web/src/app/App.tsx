import { Component, Suspense, lazy, useEffect, useLayoutEffect, useRef, type ReactNode } from "react";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { requestTitleFocus } from "../components/common";
import { useHash } from "./navigation";
import { canonicalRedirect, parseHash, routeTitle, type Route } from "./routes";

/* Route-level code splitting: each page is its own chunk. */
const HomePage = lazy(() => import("../pages/HomePage"));
const BrowsePage = lazy(() => import("../pages/BrowsePage"));
const RecordPage = lazy(() => import("../pages/RecordPage"));
const AboutPage = lazy(() => import("../pages/AboutPage"));
const PlaceholderPage = lazy(() => import("../pages/PlaceholderPage").then((m) => ({ default: m.PlaceholderPage })));
const CladePage = lazy(() => import("../pages/PlaceholderPage").then((m) => ({ default: m.CladePage })));
const NotFoundPage = lazy(() => import("../pages/PlaceholderPage").then((m) => ({ default: m.NotFoundPage })));

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

/** Identity of a "page" for focus/scroll handling: Browse query changes are in-page state, not navigation. */
function pageKey(r: Route): string {
  switch (r.name) {
    case "browse": return "browse";
    case "record": return `record/${r.accession}`;
    case "clade": return `clade/${r.cladeId}`;
    case "planned": return `planned/${r.page}`;
    case "not-found": return `nf/${r.path}`;
    default: return r.name;
  }
}

function page(r: Route) {
  switch (r.name) {
    case "home": return <HomePage />;
    case "browse": return <BrowsePage params={r.params} />;
    case "record": return <RecordPage key={r.accession} accession={r.accession} />;
    case "about": return <AboutPage />;
    case "clade": return <CladePage key={r.cladeId} cladeId={r.cladeId} />;
    case "planned": return <PlaceholderPage key={r.page} page={r.page} />;
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
