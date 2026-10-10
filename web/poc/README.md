# PR-0 proof of concept (temporary)

Checks that phylotree.js 2.6.0 and Mol* 5.13.1 load real MicroRhodoDB assets in a Vite 8 + React 18 + TypeScript build with base `/MicroRhodoDB/site/`. This is not production code. Delete it when PR-2 creates the real `web/` app.

```bash
cd web/poc
mkdir -p public/data && cp ../../refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile public/data/
npm ci && npm run build
python verify_poc.py dist ../../docs/website/baseline   # needs Playwright Chromium; RCSB/AFDB network access
```
