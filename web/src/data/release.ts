/**
 * Dataset release the website is built from. Must equal data/current.json `dataset_release` and the `const` in
 * web/src/data/schemas/web-data.schema.json (checked by tests/unit/release.test.ts). Change all three together
 * when the website moves to a new dataset release.
 */
export const DATASET_RELEASE = "1.6.1";
export const RELEASE_LABEL = `v${DATASET_RELEASE}`;
