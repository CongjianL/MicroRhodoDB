/**
 * PR-6: Content-Security-Policy for the static GitHub Pages build.
 *
 * GitHub Pages cannot set response headers, so the policy is delivered as a <meta http-equiv> tag that
 * Vite injects into the production index.html only (the dev server needs inline HMR scripts).
 * frame-ancestors, report-uri and sandbox are ignored in a meta policy and are therefore omitted.
 *
 * connect-src lists the only third-party hosts the site fetches from: RCSB PDB coordinates
 * (models.rcsb.org BinaryCIF, files.rcsb.org mmCIF) and AlphaFold DB model files. All other external
 * resources are plain links opened in a new tab, which CSP does not govern.
 * style-src needs 'unsafe-inline' because ECharts and Mol* set inline styles/style elements.
 */
export const CSP_DIRECTIVES: Record<string, string[]> = {
  "default-src": ["'self'"],
  "script-src": ["'self'"],
  "worker-src": ["'self'"],
  "connect-src": ["'self'", "https://models.rcsb.org", "https://files.rcsb.org", "https://alphafold.ebi.ac.uk"],
  "img-src": ["'self'", "data:", "blob:"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "font-src": ["'self'", "data:"],
  "object-src": ["'none'"],
  "base-uri": ["'self'"],
  "form-action": ["'self'"],
};

export const CSP = Object.entries(CSP_DIRECTIVES).map(([k, v]) => `${k} ${v.join(" ")}`).join("; ");
