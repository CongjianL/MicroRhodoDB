/**
 * PR-7: build provenance injected at build time by vite.config.ts (define __MRDB_BUILD__) from the environment
 * variables MRDB_BUILD_COMMIT / MRDB_BUILD_DATE that web/scripts/build_site_artifact.py sets. A plain
 * `npm run build` or `npm run dev` has no commit and is labelled a development build.
 */
declare const __MRDB_BUILD__: { commit: string; date: string } | undefined;

export interface BuildStamp {
  /** Full 40-hex source commit, or null for development builds. */
  commit: string | null;
  /** UTC build date (YYYY-MM-DD, the commit date), or null. */
  date: string | null;
}

const raw = typeof __MRDB_BUILD__ === "undefined" ? undefined : __MRDB_BUILD__;

export const BUILD: BuildStamp = {
  commit: raw && /^[0-9a-f]{40}$/.test(raw.commit) ? raw.commit : null,
  date: raw && /^\d{4}-\d{2}-\d{2}$/.test(raw.date) ? raw.date : null,
};

export const isReleaseBuild = (b: BuildStamp = BUILD): boolean => b.commit !== null;

/** Footer label: "Build 1a2b3c4 (2026-10-12)" for artifact builds, otherwise a development-build notice. */
export function buildLabel(b: BuildStamp = BUILD): string {
  if (!b.commit) return "Development build; not the deployed site";
  return `Build ${b.commit.slice(0, 7)}${b.date ? ` (${b.date})` : ""}`;
}
