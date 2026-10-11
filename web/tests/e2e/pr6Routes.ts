/** Mandatory PR-6 routes with a readiness probe each (shared by the PR-6 accessibility and reliability specs). */
import { expect, type Page } from "@playwright/test";

export const ROUTES: { name: string; hash: string; ready: (p: Page) => Promise<void> }[] = [
  { name: "home", hash: "#/", ready: async (p) => { await expect(p.getByTestId("stat-cards")).toBeVisible(); await expect(p.getByTestId("tree-preview")).toBeVisible(); } },
  { name: "browse", hash: "#/browse", ready: async (p) => { await expect(p.getByTestId("results-table")).toBeVisible(); } },
  { name: "browse_clade017_tent", hash: "#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1", ready: async (p) => { await expect(p.getByTestId("caveat-count")).toBeVisible(); } },
  { name: "record_P02945", hash: "#/record/P02945", ready: async (p) => { await expect(p.getByTestId("sequence")).toBeVisible(); } },
  { name: "record_engineered", hash: "#/record/A0ABF7PQA2", ready: async (p) => { await expect(p.getByTestId("sequence")).toBeVisible(); } },
  { name: "record_not_found", hash: "#/record/ZZZ999", ready: async (p) => { await expect(p.getByTestId("record-not-found")).toBeVisible(); } },
  { name: "about", hash: "#/about", ready: async (p) => { await expect(p.getByTestId("clade-support-notice")).toBeVisible(); } },
  { name: "phylogeny", hash: "#/phylogeny", ready: async (p) => { await expect(p.getByTestId("tree-canvas")).toBeVisible(); } },
  { name: "clade_017", hash: "#/clade/MR_CLD3_017", ready: async (p) => { await expect(p.getByTestId("clade-tree-canvas")).toBeVisible(); } },
  { name: "statistics", hash: "#/statistics", ready: async (p) => { await expect(p.getByTestId("chart-evidence-level")).toBeVisible(); } },
  { name: "evidence", hash: "#/evidence", ready: async (p) => { await expect(p.getByTestId("e1-table")).toBeVisible(); } },
  { name: "structures", hash: "#/structures", ready: async (p) => { await expect(p.getByTestId("pdb-table")).toBeVisible(); } },
  { name: "watchlist", hash: "#/watchlist", ready: async (p) => { await expect(p.getByTestId("wl-table")).toBeVisible(); } },
  { name: "search_text", hash: "#/search?q=MR_CLD3_017", ready: async (p) => { await expect(p.getByTestId("text-results")).toBeVisible(); } },
  { name: "search_seq", hash: "#/search?mode=sequence", ready: async (p) => { await expect(p.getByTestId("seq-not-classifier")).toBeVisible(); } },
  { name: "downloads", hash: "#/downloads", ready: async (p) => { await expect(p.getByTestId("dl-release-files")).toBeVisible(); } },
  { name: "methods", hash: "#/methods", ready: async (p) => { await expect(p.getByTestId("methods-denominators")).toBeVisible(); } },
  { name: "citation", hash: "#/citation", ready: async (p) => { await expect(p.getByTestId("cite-bibtex")).toBeVisible(); } },
  { name: "help", hash: "#/help", ready: async (p) => { await expect(p.getByTestId("help-faq")).toBeVisible(); } },
  { name: "not_found", hash: "#/does-not-exist", ready: async (p) => { await expect(p.getByTestId("not-found")).toBeVisible(); } },
];
