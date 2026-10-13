/**
 * PR-7c.2 Ecology and habitat section (Protein Entry page only).
 *
 * Representative records for every audit state, per-source display and page-wide source switching, lazy loading
 * (no habitat request outside the record page; exactly one habitat file per record view; summary.json only when
 * "About these data" is opened), graceful degradation when the habitat file is missing, malformed or does not match
 * the record, keyboard use, axe (WCAG A/AA, serious/critical) and responsive layout at 375/768/1440 px.
 * With SCREENSHOT_DIR set, PNG screenshots of the section are saved per record and width.
 */
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { dataJson, expect, expectNoHorizontalOverflow, test, type Watch } from "./fixtures";

const SHOTS = process.env.SCREENSHOT_DIR ? resolve(process.env.SCREENSHOT_DIR) : null;
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const body = (p: Page) => p.getByTestId("habitat-body");
const habitatFiles = (w: Watch) => w.dataFiles().filter((f) => f.startsWith("habitat/"));

/** Full-page capture clipped to the habitat section (element screenshots clip at the viewport under the sticky header). */
async function shot(p: Page, path: string) {
  await p.waitForLoadState("networkidle");
  const box = await p.locator("#section-habitat").boundingBox();
  const y = await p.evaluate(() => window.scrollY);
  await p.screenshot({ path, fullPage: true, clip: { x: box!.x, y: box!.y + y, width: box!.width, height: box!.height } });
}

async function openHabitat(p: Page, src: string) {
  await p.goto(`#/record/${src}?section=habitat`);
  await expect(p.getByTestId("record-page")).toHaveAttribute("data-focus", src);
  await expect(body(p)).toBeVisible();
  await expect(body(p)).toHaveAttribute("data-source", src);
}

interface Case {
  name: string;
  src: string;
  grade: string;
  host: string;
  check?: (p: Page) => Promise<void>;
}

const CASES: Case[] = [
  {
    name: "direct_sample", src: "A0ABS3TAH3", grade: "DIRECT_SAMPLE", host: "NOT_REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-grade")).toHaveText("Direct sample");
      await expect(p.getByTestId("habitat-physical-values").getByTestId("habitat-entity")).toHaveCount(3);
      // invalid placeholders are listed only under "Reported but not usable"
      const nu = p.getByTestId("habitat-not-usable");
      await expect(nu.locator('[data-status="invalid_placeholder"]')).toHaveCount(6);
      await expect(p.getByTestId("habitat-physical-values").locator('[data-status="invalid_placeholder"]')).toHaveCount(0);
    },
  },
  {
    name: "host_only", src: "A0A010RVL4", grade: "NOT_REPORTED", host: "REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-host-only")).toHaveText("Physical habitat not reported; host reported.");
      await expect(p.getByTestId("habitat-physical-values")).toHaveCount(0);
      await expect(p.getByTestId("habitat-host-values").getByTestId("habitat-value").first()).toHaveText("Fragaria x ananassa");
      // the host value never appears inside the physical-habitat card
      await expect(p.getByTestId("habitat-physical")).not.toContainText("Fragaria");
      await expect(p.getByTestId("habitat-missingness")).toHaveText("Physical habitat not reported in the linked sample records; literature not reviewed.");
    },
  },
  {
    name: "physical_ambiguous", src: "A0A9W6BMQ0", grade: "AMBIGUOUS", host: "NOT_REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-ambiguity")).toHaveAttribute("data-class", "DISTINCT_SAME_SAMPLE");
      await expect(p.getByTestId("habitat-grade")).toHaveText("Conflicting records");
    },
  },
  {
    name: "host_ambiguous_quarantine", src: "A0A4Q4MIR8", grade: "DIRECT_SAMPLE", host: "AMBIGUOUS",
    check: async (p) => {
      await expect(p.getByTestId("habitat-host-ambiguity")).toHaveAttribute("data-class", "DISTINCT_SAME_SAMPLE");
      const hv = p.getByTestId("habitat-host-values").getByTestId("habitat-value");
      await expect(hv).toHaveText(["apple", "Malus domestica", "apple"]);
      // ENVO:0010003 is not in OLS: shown verbatim, flagged, never linked
      const q = p.locator('[data-testid="habitat-item"][data-quarantine="envo_id_not_found_in_ols"]');
      await expect(q).toHaveCount(2);
      for (const el of await q.all()) {
        await expect(el.getByTestId("habitat-value")).toHaveText("ENVO:0010003");
        await expect(el.getByTestId("habitat-envo-link")).toHaveCount(0);
        await expect(el.getByTestId("habitat-quarantine")).toContainText("not an ontology term");
      }
      await expect(p.locator('a[href*="ENVO_0010003"]')).toHaveCount(0);
      await expect(p.locator('[data-testid="habitat-envo-link"] a[href="https://purl.obolibrary.org/obo/ENVO_00000115"]').first()).toBeAttached();
    },
  },
  {
    name: "literature_vs_database", src: "A0A411LJN5", grade: "AMBIGUOUS", host: "NOT_REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-ambiguity")).toHaveAttribute("data-class", "LITERATURE_VS_DATABASE");
      await expect(p.getByTestId("habitat-literature-isolate").getByTestId("habitat-literature")).toHaveCount(2);
      await expect(p.getByTestId("habitat-grades-differ")).toBeVisible();
    },
  },
  {
    name: "no_link", src: "Q53461", grade: "NOT_REPORTED", host: "NOT_REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-missingness")).toHaveText("No traceable INSDC or sample link; sample records could not be checked; literature not reviewed.");
      await expect(p.getByTestId("habitat-collection-no-link")).toBeVisible();
      await expect(p.getByTestId("habitat-badges")).toContainText("no traceable sample link");
    },
  },
  {
    name: "organism_context_only", src: "B0R2U4", grade: "ORGANISM_CONTEXT_ONLY", host: "NOT_REPORTED",
    check: async (p) => {
      const oc = p.getByTestId("habitat-organism-context");
      await expect(oc).toContainText("Organism-level context, not the sampling habitat of this sequence");
      await expect(oc.getByTestId("habitat-literature").first()).toHaveAttribute("data-scope", "organism");
      await expect(p.getByTestId("habitat-physical").getByTestId("habitat-literature")).toHaveCount(0);
      await expect(p.getByTestId("habitat-literature-checked")).toHaveAttribute("data-status", "ORGANISM_CONTEXT");
    },
  },
  {
    name: "verified_isolate_no_link", src: "A0AAJ6N6B2", grade: "VERIFIED_ISOLATE", host: "NOT_REPORTED",
    check: async (p) => {
      await expect(p.getByTestId("habitat-grade")).toHaveText("Verified isolate (literature)");
      await expect(p.getByTestId("habitat-literature-isolate").getByTestId("habitat-literature").first()).toHaveAttribute("data-scope", "isolate");
      await expect(p.getByTestId("habitat-no-link")).toBeVisible();
    },
  },
  {
    name: "unprefixed_identifier", src: "A0A6N7QP32", grade: "DIRECT_SAMPLE", host: "NOT_REPORTED",
    check: async (p) => {
      const q = p.locator('[data-testid="habitat-item"][data-quarantine="unprefixed_numeric_identifier"]');
      await expect(q).toHaveCount(2);
      await expect(q.first().getByTestId("habitat-value")).toHaveText("00000316");
      await expect(q.first().getByTestId("habitat-envo-link")).toHaveCount(0);
      await expect(p.locator('a[href*="ENVO_00000316"]')).toHaveCount(0);
    },
  },
];

test.describe("PR-7c.2 representative records", () => {
  for (const c of CASES) {
    test(`${c.name} (${c.src})`, async ({ page, watch }) => {
      await openHabitat(page, c.src);
      await expect(body(page)).toHaveAttribute("data-grade", c.grade);
      await expect(body(page)).toHaveAttribute("data-host", c.host);
      await c.check?.(page);
      // every rendered item carries a well-formed evidence ID that exists in the served sidecar entry
      const rec = await dataJson<{ mrdb_acc: string }>(page, `records/${(await page.getByTestId("record-page").getAttribute("data-mrdb"))!}.json`);
      const hab = await dataJson<{ sources: { source_acc: string; items: Record<string, { evidence_id: string }[]> }[] }>(page, `habitat/records/${rec.mrdb_acc}.json`);
      const want = Object.values(hab.sources.find((s) => s.source_acc === c.src)!.items).flat().map((i) => i.evidence_id).sort();
      const got = (await page.locator("#section-habitat [data-evidence-id]").evaluateAll((els) => els.map((e) => e.getAttribute("data-evidence-id")!))).sort();
      expect(got).toEqual(want);
      expect(habitatFiles(watch)).toEqual([`habitat/records/${rec.mrdb_acc}.json`]);
      if (SHOTS) {
        mkdirSync(SHOTS, { recursive: true });
        await shot(page, resolve(SHOTS, `case_${c.name}_${c.src}_1440.png`));
      }
    });
  }
});

test.describe("PR-7c.2 multi-source records", () => {
  test("lists every source with its grade; choosing one switches the whole page and keeps the sequence", async ({ page, watch }) => {
    await openHabitat(page, "B0R2U4");
    const table = page.getByTestId("habitat-sources");
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await expect(table.locator('tr[data-source="B0R2U4"]')).toHaveAttribute("aria-current", "true");
    await expect(table.locator('tr[data-source="B0R2U4"]')).toHaveAttribute("data-grade", "ORGANISM_CONTEXT_ONLY");
    await expect(table.locator('tr[data-source="P0DMH7"]')).toHaveAttribute("data-grade", "NOT_REPORTED");
    await expect(page.getByTestId("habitat-grades-differ")).toBeVisible();
    const seq = await page.getByTestId("sequence").innerText();

    await table.getByTestId("habitat-source-switch").click();
    await expect(page).toHaveURL(/#\/record\/P0DMH7\?section=habitat$/);
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "P0DMH7");
    await expect(page.getByTestId("record-eyebrow")).toContainText("source record P0DMH7");
    await expect(body(page)).toHaveAttribute("data-source", "P0DMH7");
    await expect(body(page)).toHaveAttribute("data-grade", "NOT_REPORTED");
    await expect(page.getByTestId("habitat-sources").locator('tr[data-source="P0DMH7"]')).toHaveAttribute("aria-current", "true");
    // identical MRDB sequence; organism, function and placement come from the selected source record
    expect(await page.getByTestId("sequence").innerText()).toBe(seq);
    const rec = await dataJson<{ sources: { source_acc: string; organism: string; function: { func_class: string } }[] }>(page, "records/MRDB000004.json");
    const s = rec.sources.find((x) => x.source_acc === "P0DMH7")!;
    await expect(page.locator("h1").locator("..")).toContainText(s.organism);
    // P0DMH7 is a reference-tree tip while B0R2U4 is placed: the placement block follows the selected source
    await expect(page.getByTestId("placement-table")).toContainText("This record is a tip of the reference tree");
    // the same habitat file serves both source records (fetched once)
    expect(habitatFiles(watch)).toEqual(["habitat/records/MRDB000004.json"]);
  });

  test("the overview source switcher and the habitat source table select the same source record", async ({ page, watch }) => {
    await openHabitat(page, "A0A411LJN5");
    await page.getByTestId("habitat-sources").getByTestId("habitat-source-switch").click();
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "A0A0C9NB29");
    await expect(body(page)).toHaveAttribute("data-grade", "DIRECT_SAMPLE");
    await expect(page.getByTestId("habitat-grades-differ")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });
});

test.describe("PR-7c.2 lazy loading", () => {
  const PAGES: [string, string][] = [
    ["#/", "stat-cards"], ["#/browse", "results-table"], ["#/search?q=MR_CLD3_017", "text-results"],
    ["#/phylogeny", "tree-canvas"], ["#/downloads", "dl-release-files"],
  ];
  for (const [hash, ready] of PAGES) {
    test(`no habitat request on ${hash}`, async ({ page, watch }) => {
      await page.goto(hash);
      await expect(page.getByTestId(ready)).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(habitatFiles(watch)).toEqual([]);
    });
  }

  test("a record view loads exactly one habitat file; summary.json only when About is opened", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000002");
    await expect(body(page)).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(habitatFiles(watch)).toEqual(["habitat/records/MRDB000002.json"]);
    await page.getByTestId("habitat-about").locator("summary").click();
    await expect(page.getByTestId("habitat-about-body")).toBeVisible();
    await expect(page.getByTestId("habitat-about-body")).toContainText("PR-7c.1a");
    expect(habitatFiles(watch)).toEqual(["habitat/records/MRDB000002.json", "habitat/summary.json"]);
    expect(watch.dataFiles().filter((f) => f === "habitat/manifest.json")).toEqual([]);
  });
});

test.describe("PR-7c.2 degradation", () => {
  const variants: [string, (route: import("@playwright/test").Route) => Promise<void>][] = [
    ["404", (r) => r.fulfill({ status: 404, body: "not found" })],
    ["malformed JSON", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "{not json" })],
    ["wrong MRDB accession", async (r) => {
      const res = await r.fetch();
      const j = await res.json();
      j.mrdb_acc = "MRDB000003";
      await r.fulfill({ response: res, json: j });
    }],
    ["merged source records", async (r) => {
      const res = await r.fetch();
      const j = await res.json();
      j.sources = j.sources.slice(0, 1);
      await r.fulfill({ response: res, json: j });
    }],
  ];
  for (const [name, handler] of variants) {
    test(`habitat file ${name}: neutral message, rest of the record unaffected`, async ({ page, watch }) => {
      await page.route("**/data/v1.6.0/habitat/records/MRDB000004.json", handler);
      await page.goto("#/record/B0R2U4?section=habitat");
      await expect(page.getByTestId("habitat-unavailable")).toBeVisible();
      await expect(page.getByTestId("habitat-unavailable")).toHaveText("Habitat metadata unavailable in this build. The rest of this record is not affected.");
      await expect(body(page)).toHaveCount(0);
      await expect(page.getByTestId("sequence")).toBeVisible();
      await expect(page.getByTestId("placement-table")).toBeVisible();
      // the deliberate failure is the only error (404 response / its console message)
      const unexpected = watch.errors.filter((e) => !/habitat\/records\/MRDB000004\.json/.test(e) && !/Failed to load resource: the server responded with a status of 404/.test(e));
      expect(unexpected).toEqual([]);
      watch.errors.length = 0;
    });
  }
});

test.describe("PR-7c.2 keyboard", () => {
  test("disclosures open with the keyboard and the source switcher is reachable and activates with Enter", async ({ page, watch }) => {
    await openHabitat(page, "B0R2U4");
    const prov = page.getByTestId("habitat-provenance").first();
    await prov.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(prov).toHaveAttribute("open", "");
    await expect(prov.getByTestId("habitat-evidence-id")).toHaveText(/^H[EL][0-9a-f]{12}$/);
    const about = page.getByTestId("habitat-about");
    await about.locator("summary").focus();
    await page.keyboard.press("Space");
    await expect(page.getByTestId("habitat-about-body")).toBeVisible();
    const link = page.getByTestId("habitat-source-switch");
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "P0DMH7");
    expect(watch.errors).toEqual([]);
  });
});

const VIEWPORTS = [{ w: 375, h: 812 }, { w: 768, h: 1024 }, { w: 1440, h: 900 }] as const;
const A11Y = ["A0A4Q4MIR8", "B0R2U4", "Q53461", "A0A010RVL4", "A0A411LJN5"];

for (const vp of VIEWPORTS) {
  test.describe(`PR-7c.2 ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });
    for (const src of A11Y) {
      test(`${src}: no overflow; no serious/critical axe violations in the habitat section`, async ({ page, watch }) => {
        await openHabitat(page, src);
        // open every disclosure in the section so axe and the screenshot cover the expanded content
        await page.locator("#section-habitat details").evaluateAll((els) => els.forEach((e) => ((e as HTMLDetailsElement).open = true)));
        await expect(page.getByTestId("habitat-about-body")).toBeVisible();
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalOverflow(page);
        const res = await new AxeBuilder({ page }).include("#section-habitat").withTags(TAGS).analyze();
        const bad = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
        expect(bad).toEqual([]);
        if (SHOTS) {
          mkdirSync(SHOTS, { recursive: true });
          await shot(page, resolve(SHOTS, `habitat_${src}_${vp.w}.png`));
        }
        expect(watch.errors).toEqual([]);
      });
    }
  });
}
