import { useEffect, useId, useRef, useState } from "react";
import { PLANNED_PAGES, href, type PlannedPage, type Route } from "../app/routes";

interface NavItem {
  key: string;
  label: string;
  href: string;
  planned?: string; // PR that implements it
}

const PRIMARY: NavItem[] = [
  { key: "home", label: "Home", href: href.home() },
  { key: "browse", label: "Browse", href: href.browse() },
  { key: "phylogeny", label: "Phylogeny", href: href.phylogeny() },
  ...(["structures", "search", "downloads"] as PlannedPage[]).map((p) => ({
    key: p, label: p === "search" ? "Search" : PLANNED_PAGES[p].title, href: href.planned(p), planned: PLANNED_PAGES[p].pr,
  })),
  { key: "about", label: "About", href: href.about() },
];

const MORE: NavItem[] = (["statistics", "evidence", "watchlist", "methods", "citation", "help"] as PlannedPage[]).map((p) => ({
  key: p, label: PLANNED_PAGES[p].title, href: href.planned(p), planned: PLANNED_PAGES[p].pr,
}));

function activeKey(r: Route): string {
  if (r.name === "planned") return r.page;
  if (r.name === "record") return "browse";
  if (r.name === "clade") return "phylogeny";
  return r.name;
}

function PlannedPill({ pr }: { pr: string }) {
  return (
    <span className="ml-1 rounded border border-line-strong bg-subtle px-1 text-[0.6875rem] font-medium leading-4 text-ink-2" title={`Planned for ${pr}; not available in this build`}>
      planned
    </span>
  );
}

function NavLink({ item, active, onClick, block = false }: { item: NavItem; active: boolean; onClick?: () => void; block?: boolean }) {
  return (
    <a
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={[
        "inline-flex items-center rounded-md px-2.5 no-underline transition-colors",
        block ? "w-full py-2.5" : "py-2",
        active ? "bg-accent-soft font-semibold text-accent-strong" : "text-ink hover:bg-subtle hover:text-ink",
      ].join(" ")}
    >
      {item.label}
      {item.planned ? <PlannedPill pr={item.planned} /> : null}
      {item.planned ? <span className="sr-only"> (planned for {item.planned})</span> : null}
    </a>
  );
}

function useDismiss(open: boolean, close: () => void, refs: React.RefObject<HTMLElement | null>[]) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onDown = (e: MouseEvent) => {
      if (!refs.some((r) => r.current?.contains(e.target as Node))) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open, close, refs]);
}

export function SiteHeader({ route }: { route: Route }) {
  const active = activeKey(route);
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const moreBtn = useRef<HTMLButtonElement>(null);
  const morePanel = useRef<HTMLDivElement>(null);
  const mobileBtn = useRef<HTMLButtonElement>(null);
  const mobilePanel = useRef<HTMLDivElement>(null);
  const moreId = useId();
  const mobileId = useId();

  const closeMore = useRef(() => {
    setMoreOpen(false);
    moreBtn.current?.focus();
  }).current;
  const closeMobile = useRef(() => {
    setMobileOpen(false);
    mobileBtn.current?.focus();
  }).current;
  const moreRefs = useRef([moreBtn, morePanel]).current;
  const mobileRefs = useRef([mobileBtn, mobilePanel]).current;
  useDismiss(moreOpen, closeMore, moreRefs);
  useDismiss(mobileOpen, closeMobile, mobileRefs);

  // Close menus on navigation.
  const routeKey = JSON.stringify(route.name === "browse" ? "browse" : route);
  useEffect(() => {
    setMoreOpen(false);
    setMobileOpen(false);
  }, [routeKey]);

  const moreActive = MORE.some((m) => m.key === active);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/90">
      <a href="#main" className="sr-only-focusable absolute left-2 top-2 z-50 rounded bg-accent px-3 py-2 text-white" onClick={(e) => {
        e.preventDefault();
        document.getElementById("main")?.focus();
      }}>
        Skip to main content
      </a>
      <div className="container-page flex h-16 items-center gap-3">
        <a href={href.home()} className="flex shrink-0 items-center gap-2 text-ink no-underline hover:text-ink hover:no-underline" aria-label="MicroRhodoDB home">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width="28" height="28" />
          <span className="text-lg font-semibold tracking-tight">MicroRhodoDB</span>
          <span className="hidden rounded border border-line px-1.5 text-xs text-ink-2 sm:inline">v1.6.0</span>
        </a>

        <nav aria-label="Primary" className="ml-auto hidden lg:block">
          <ul className="flex items-center gap-0.5 text-[0.9375rem]">
            {PRIMARY.map((item) => (
              <li key={item.key}>
                <NavLink item={item} active={active === item.key} />
              </li>
            ))}
            <li className="relative">
              <button
                ref={moreBtn}
                type="button"
                aria-expanded={moreOpen}
                aria-controls={moreId}
                onClick={() => setMoreOpen((o) => !o)}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-2 ${moreActive ? "bg-accent-soft font-semibold text-accent-strong" : "text-ink hover:bg-subtle"}`}
              >
                More
                <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
              </button>
              <div ref={morePanel} id={moreId} hidden={!moreOpen} className="absolute right-0 top-full mt-1 w-64 rounded-lg border border-line bg-surface p-1.5 shadow-lg">
                <ul>
                  {MORE.map((item) => (
                    <li key={item.key}>
                      <NavLink item={item} active={active === item.key} onClick={() => setMoreOpen(false)} block />
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          </ul>
        </nav>

        <button
          ref={mobileBtn}
          type="button"
          className="btn btn-secondary btn-sm ml-auto lg:hidden"
          aria-expanded={mobileOpen}
          aria-controls={mobileId}
          onClick={() => setMobileOpen((o) => !o)}
        >
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18">
            {mobileOpen ? <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="1.8" /> : <path d="M2 4h14M2 9h14M2 14h14" stroke="currentColor" strokeWidth="1.8" />}
          </svg>
          Menu
        </button>
      </div>

      <div ref={mobilePanel} id={mobileId} hidden={!mobileOpen} className="border-t border-line bg-surface lg:hidden">
        <nav aria-label="Primary (mobile)" className="container-page max-h-[calc(100vh-4rem)] overflow-y-auto py-3">
          <ul className="grid gap-0.5 sm:grid-cols-2">
            {PRIMARY.map((item) => (
              <li key={item.key}>
                <NavLink item={item} active={active === item.key} onClick={() => setMobileOpen(false)} block />
              </li>
            ))}
          </ul>
          <p className="mb-1 mt-3 px-2.5 text-xs font-semibold uppercase tracking-wide text-ink-2">More</p>
          <ul className="grid gap-0.5 sm:grid-cols-2">
            {MORE.map((item) => (
              <li key={item.key}>
                <NavLink item={item} active={active === item.key} onClick={() => setMobileOpen(false)} block />
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
