/**
 * Citation strings built only from the CITATION.cff fields exported in downloads.json (citation block).
 * Nothing is invented: a missing DOI is reported as missing, the website version is never used as the
 * data version, and fields that are null are omitted rather than guessed.
 */
import type { Downloads } from "../data/types";

export type Cff = Downloads["citation"];

export interface CffAuthor { family: string; given: string }

export function authors(c: Cff): CffAuthor[] {
  return (c.authors ?? []).map((a) => ({ family: a["family-names"] ?? a.name ?? "", given: a["given-names"] ?? "" })).filter((a) => a.family);
}

const initials = (given: string) =>
  given.split(/[\s-]+/).filter(Boolean).map((g) => `${g[0].toUpperCase()}.`).join(" ");

export const year = (c: Cff) => (c["date-released"] ? c["date-released"].slice(0, 4) : "n.d.");

/** APA 7-style data-set reference. */
export function apa(c: Cff): string {
  const as = authors(c).map((a) => `${a.family}, ${initials(a.given)}`.trim());
  const who = as.length <= 1 ? as.join("") : `${as.slice(0, -1).join(", ")}, & ${as[as.length - 1]}`;
  const parts = [`${who} (${year(c)}).`, `${c.title ?? "MicroRhodoDB"}${c.version ? ` (Version ${c.version})` : ""} [Data set].`];
  if (c.doi) parts.push(`https://doi.org/${c.doi}`);
  else if (c["repository-code"]) parts.push(c["repository-code"]);
  return parts.join(" ");
}

const BIB_SPECIAL = /([&%$#_{}])/g;
export const bibEscape = (s: string) => s.replace(/\\/g, "\\textbackslash{}").replace(BIB_SPECIAL, "\\$1").replace(/~/g, "\\textasciitilde{}").replace(/\^/g, "\\textasciicircum{}");

export function bibKey(c: Cff): string {
  const fam = (authors(c)[0]?.family ?? "microrhododb").toLowerCase().replace(/[^a-z0-9]/g, "");
  return `${fam}_microrhododb_${(c.version ?? "").replace(/[^0-9]/g, "")}_${year(c)}`;
}

export function bibtex(c: Cff): string {
  const fields: [string, string][] = [
    ["author", authors(c).map((a) => `${bibEscape(a.family)}, ${bibEscape(a.given)}`).join(" and ")],
    ["title", `{${bibEscape(c.title ?? "MicroRhodoDB")}}`],
    ["year", year(c)],
  ];
  if (c.version) fields.push(["version", bibEscape(c.version)]);
  if (c.doi) fields.push(["doi", bibEscape(c.doi)]);
  if (c["repository-code"]) fields.push(["url", c["repository-code"]]);
  const note = [c["date-released"] ? `Released ${c["date-released"]}` : null, c.license ? `licence ${c.license}` : null].filter(Boolean).join("; ");
  if (note) fields.push(["note", bibEscape(note)]);
  return `@misc{${bibKey(c)},\n${fields.map(([k, v]) => `  ${k} = {${v}}`).join(",\n")}\n}\n`;
}

/** "12.1 kB" style sizes (decimal units, as GitHub shows them). */
export function fmtBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  const u = ["kB", "MB", "GB"];
  let v = n / 1000;
  let i = 0;
  while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${u[i]}`;
}
