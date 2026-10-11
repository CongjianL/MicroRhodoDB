import { describe, expect, it } from "vitest";
import { BUILD, buildLabel, isReleaseBuild } from "../../src/lib/buildInfo";

// PR-7: the footer build label distinguishes a provenance-stamped artifact build from a development build.
describe("PR-7 build stamp", () => {
  it("is a development build when no commit is injected (vitest runs without MRDB_BUILD_COMMIT)", () => {
    expect(BUILD.commit).toBeNull();
    expect(isReleaseBuild()).toBe(false);
    expect(buildLabel()).toBe("Development build; not the deployed site");
  });
  it("labels an artifact build with the short commit and the commit date", () => {
    const b = { commit: "f0b9f261cbdc55e8eef67bcf321d1035a2a21814", date: "2026-10-12" };
    expect(isReleaseBuild(b)).toBe(true);
    expect(buildLabel(b)).toBe("Build f0b9f26 (2026-10-12)");
    expect(buildLabel({ ...b, date: null })).toBe("Build f0b9f26");
  });
});
