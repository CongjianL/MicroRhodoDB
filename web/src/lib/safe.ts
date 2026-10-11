/**
 * PR-6 output hardening (defence in depth; all inputs are frozen release data, but links and tooltip
 * HTML are built from data fields).
 */

/**
 * Only relative URLs (same site) and http(s)/mailto URLs are rendered as links; any other scheme
 * (javascript:, data:, vbscript:, ...) is dropped and the caller renders plain text instead.
 */
export function safeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  const t = url.trim();
  try {
    const u = new URL(t, "https://relative.invalid/");
    if (u.origin === "https://relative.invalid") return /^[a-z][a-z0-9+.-]*:/i.test(t) ? undefined : t;
    return u.protocol === "https:" || u.protocol === "http:" || u.protocol === "mailto:" ? t : undefined;
  } catch {
    return undefined;
  }
}

/** Escape text for HTML contexts (ECharts tooltip formatters return HTML). */
export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
