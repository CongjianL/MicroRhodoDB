import { useEffect } from "react";

/**
 * Deep links to a section of a long page: `?s=<id>` scrolls to the element `${prefix}<id>` once it exists
 * (after data load). Only ids matching [a-z0-9-] are accepted.
 */
export function useSectionScroll(params: URLSearchParams, prefix: string, ready = true) {
  const s = params.get("s") ?? "";
  useEffect(() => {
    if (!ready || !/^[a-z0-9-]{1,40}$/.test(s)) return;
    const t = window.setTimeout(() => document.getElementById(`${prefix}${s}`)?.scrollIntoView({ block: "start" }), 0);
    return () => window.clearTimeout(t);
  }, [s, prefix, ready]);
}
