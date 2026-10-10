import { useSyncExternalStore } from "react";

/**
 * Minimal hash-history store.
 * - Links are real <a href="#/..."> elements (new history entries via the browser).
 * - Browse filter, sort and page changes use pushHash() (one history entry per discrete change,
 *   so Back/Forward restore earlier filter states); consecutive commits from one text field and
 *   automatic corrections (out-of-range page, legacy redirects) use replaceHash().
 */
const EVT = "mrdb:navigate";

function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  window.addEventListener("popstate", cb);
  window.addEventListener(EVT, cb);
  return () => {
    window.removeEventListener("hashchange", cb);
    window.removeEventListener("popstate", cb);
    window.removeEventListener(EVT, cb);
  };
}

export function useHash(): string {
  return useSyncExternalStore(subscribe, () => window.location.hash, () => "");
}

/** Replace the current hash without adding a history entry. */
export function replaceHash(hash: string) {
  if (window.location.hash === hash) return;
  const url = new URL(window.location.href);
  url.hash = hash;
  window.history.replaceState(window.history.state, "", url.toString());
  window.dispatchEvent(new Event(EVT));
}

/** Navigate to a new hash (adds a history entry). */
export function pushHash(hash: string) {
  if (window.location.hash === hash) return;
  window.location.hash = hash;
}
