/** The dataset release named in the code, the exported data and the schema must agree. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DATASET_RELEASE, RELEASE_LABEL } from "../../src/data/release";
import { WEB } from "./helpers";

describe("dataset release", () => {
  it("matches data/current.json and the web-data schema", () => {
    const cur = JSON.parse(readFileSync(resolve(WEB, "public/data/current.json"), "utf8"));
    expect(cur.dataset_release).toBe(DATASET_RELEASE);
    expect(cur.path).toBe(`data/${RELEASE_LABEL}/`);
    const schema = readFileSync(resolve(WEB, "src/data/schemas/web-data.schema.json"), "utf8");
    expect(schema).toContain(`"const": "${DATASET_RELEASE}"`);
  });
});
