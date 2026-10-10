# tests/

Run from the repository root (or the extracted archive) inside the pinned environment:

```bash
python -m pytest -q tests/            # 45 tests
```

| File | Tests | Scope |
|---|---|---|
| `test_v160_release.py` | 28 | v1.6.0 release. Covers DB integrity and identity, removal of `alias_v14` and the compatibility views, data-dictionary coverage, function-call conflict invariants (0 conflicting E3/E4, 439 downgrades), E1 support links, engineered-construct exclusion, counts, provenance, continuity with v1.5.0 (membership unchanged, prior `release_metadata` untouched, prior release SHA-256s), exports, the CLI on 12 queries, the Python API, the scorer-validation summary, re-drawing the audit sample, the v1.4.0 suite and a Snakemake dry run |
| `test_v150_release.py` | 17 | v1.5.0 release, run against the immutable v1.5.0 DB |
| `release_v140.py` | 18 checks | v1.4.0 suite; a plain script, run by `test_v160_release.py::test_v140_release_suite` |
| `browser_walkthrough_v160.py` | 38 checks | Playwright walkthrough of `site/` under `file://` and HTTP, or a live URL (`--url`). Not part of pytest; needs `playwright install chromium` |

**Skips.** A test is skipped only when its input is genuinely absent, and the skip message names the missing
input:

- `releases/v1.5.0`, `releases/v1.4.0`, or the two inputs of the v1.4.0 suite (`releases/v1.3.0` DB and `releases/v1.0/tables/membership_assignments.tsv`) not present. All are included in the v1.6.0 archive.
- The dry-run test is running inside Snakemake (`MRDB_IN_SNAKEMAKE=1`). It cannot call Snakemake recursively.

The CLI test does not skip. It fails if HMMER or DIAMOND is not on PATH.

**Environment variables.**

- `MRDB_REPO`: repository root (default `.`).
- `MRDB_DB`: database under test (default: the shipped v1.6.0 DB). The workflow sets it to the rebuilt DB.

The v1.2/v1.3 test suites were lost before v1.4.0 (see `docs/LEGACY_AND_MISSING_COMPONENTS.md`). Their
recorded results remain in `releases/v1.2.0/validation/` and `releases/v1.3.0/validation/`.
