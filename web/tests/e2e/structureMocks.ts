/**
 * Network mocks for the structure viewer: requests to RCSB PDB (models / files) and AlphaFold DB
 * are answered with real files committed under tests/fixtures/structures (see
 * scripts/fetch_structure_fixtures.py). Unknown entries get a 404 so a missing fixture is visible.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route } from "@playwright/test";
import type { Watch } from "./fixtures";

const FIX = resolve(dirname(fileURLToPath(import.meta.url)), "../fixtures/structures");
const CORS = { "access-control-allow-origin": "*" };

export const EXTERNAL = /^https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)\//;

export type Override = (route: Route, url: URL) => Promise<boolean> | boolean;

export interface MockLog {
  /** External structure URLs requested, in order. */
  hits: string[];
}

function serve(route: Route, file: string, contentType: string) {
  const p = resolve(FIX, file);
  if (!existsSync(p)) return route.fulfill({ status: 404, headers: CORS, body: `no fixture ${file}` });
  return route.fulfill({ status: 200, headers: { ...CORS, "content-type": contentType }, body: readFileSync(p) });
}

/** Install the mocks. `override` may answer a request itself (return true) e.g. to inject errors. */
export async function mockStructures(page: Page, override?: Override): Promise<MockLog> {
  const log: MockLog = { hits: [] };
  await page.route(EXTERNAL, async (route) => {
    const url = new URL(route.request().url());
    log.hits.push(url.toString());
    if (override && (await override(route, url))) return;
    let m: RegExpExecArray | null;
    if (url.hostname === "models.rcsb.org" && (m = /^\/v1\/([0-9a-z]{4})\/full$/.exec(url.pathname))) return serve(route, `${m[1]}.bcif`, "application/octet-stream");
    if (url.hostname === "files.rcsb.org" && (m = /^\/download\/([0-9A-Z]{4})\.cif$/.exec(url.pathname))) return serve(route, `${m[1]}.cif`, "chemical/x-mmcif");
    if (url.hostname === "alphafold.ebi.ac.uk" && (m = /^\/files\/(AF-[A-Z0-9]+-F1-model_v\d+\.pdb)$/.exec(url.pathname))) return serve(route, m[1], "chemical/x-pdb");
    return route.fulfill({ status: 404, headers: CORS, body: "not mocked" });
  });
  return log;
}

/** Remove expected (injected) failures from the watch log so the fixture's teardown check passes. */
export function dropExpected(watch: Watch, ...patterns: RegExp[]) {
  const keep = watch.errors.filter((e) => !patterns.some((p) => p.test(e)));
  watch.errors.splice(0, watch.errors.length, ...keep);
}

/** Lazy Mol* chunk requests (Vite names it molstarViewer-<hash>.js). */
export const molstarChunk = (watch: Watch) => watch.requests.filter((u) => /\/assets\/molstarViewer-[^/]+\.js$/.test(u));
