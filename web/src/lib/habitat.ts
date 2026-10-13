/**
 * PR-7c.2 Ecology and habitat: pure view model for the Protein Entry habitat section. No React, no fetches.
 *
 * Principle: display observed environmental metadata, not inferred habitats. Every value shown comes verbatim from
 * one item of the habitat sidecar (data/v1.6.0/habitat/records/<MRDB>.json), which copies the PR-7c.1a audit tables.
 * The view model never merges, normalises, ranks or resolves values; it only groups them for display and attaches
 * neutral wording keyed on the audit's own states (grade, scope, ambiguity class, flags).
 *
 * Defence in depth (the sidecar is schema-validated at export time; these checks guard the browser against a
 * malformed or tampered file): items in the wrong group, with an unknown role or a malformed evidence ID are dropped
 * and counted; a file whose MRDB accession or source records differ from the record file is rejected.
 */
import type {
  AmbiguityClass, HabitatGrade, HabitatItem, HabitatRecordFile, HabitatSourceEntry, HostStatus,
} from "../data/habitatTypes";

export const HABITAT_ROLES = {
  physical: ["env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "habitat_nonstandard", "literature_isolate", "literature_rejected"],
  host: ["host", "host_detail"],
  collection: ["country", "lat_lon", "lat", "lon", "collection_date", "depth", "sample_material", "environmental_sample", "metagenome_source"],
  organism_context: ["organism_context"],
} as const;
export type HabitatGroup = keyof typeof HABITAT_ROLES;
const GROUP_OF = new Map<string, HabitatGroup>(
  (Object.keys(HABITAT_ROLES) as HabitatGroup[]).flatMap((g) => HABITAT_ROLES[g].map((r) => [r, g] as [string, HabitatGroup])),
);
/** Roles used for the physical-habitat grade (MIxS env_* triad and isolation source). */
export const GRADING_ROLES = ["isolation_source", "env_broad_scale", "env_local_scale", "env_medium"] as const;

export const ROLE_LABEL: Record<string, string> = {
  isolation_source: "Isolation source",
  env_broad_scale: "Broad-scale environment (env_broad_scale)",
  env_local_scale: "Local environment (env_local_scale)",
  env_medium: "Environmental medium (env_medium)",
  habitat_nonstandard: "Non-standard habitat field",
  literature_isolate: "Literature isolation statement",
  literature_rejected: "Literature statement (rejected)",
  host: "Host",
  host_detail: "Host detail",
  country: "Country / geographic location",
  lat_lon: "Coordinates",
  lat: "Latitude",
  lon: "Longitude",
  collection_date: "Collection date",
  depth: "Depth",
  sample_material: "Sample material",
  environmental_sample: "Environmental sample flag",
  metagenome_source: "Metagenome source",
  organism_context: "Organism-level context",
};

export const SOURCE_LABEL: Record<string, string> = {
  ena_biosample: "ENA BioSample",
  ncbi_biosample: "NCBI BioSample",
  insdc_source_feature: "INSDC source feature",
  literature: "Literature",
};

export const GRADE_INFO: Record<HabitatGrade, { label: string; tone: "info" | "neutral" | "warn"; text: string }> = {
  DIRECT_SAMPLE: { label: "Direct sample", tone: "info", text: "A physical habitat value is reported in the sample record(s) linked to this sequence." },
  VERIFIED_ISOLATE: { label: "Verified isolate (literature)", tone: "info", text: "A publication states where the source isolate of this record was obtained; no usable physical habitat value is available from linked sample records." },
  ORGANISM_CONTEXT_ONLY: { label: "Organism context only", tone: "neutral", text: "Only organism-level ecological context is available. It is not the sampling habitat of this sequence." },
  AMBIGUOUS: { label: "Conflicting records", tone: "warn", text: "The linked records report differing physical habitat values. All values are listed; none is chosen." },
  NOT_REPORTED: { label: "Not reported", tone: "neutral", text: "No usable physical habitat value is reported." },
  LOOKUP_FAILED: { label: "Lookup failed", tone: "warn", text: "The linked records could not be retrieved." },
  NOT_SEARCHED: { label: "Not searched", tone: "neutral", text: "This record was not searched." },
};

export const HOST_INFO: Record<HostStatus, { label: string; tone: "info" | "neutral" | "warn" }> = {
  REPORTED: { label: "Host reported", tone: "info" },
  AMBIGUOUS: { label: "Conflicting host values", tone: "warn" },
  NOT_REPORTED: { label: "Host not reported", tone: "neutral" },
  LOOKUP_FAILED: { label: "Host lookup failed", tone: "warn" },
  NOT_SEARCHED: { label: "Host not searched", tone: "neutral" },
};

/** Neutral explanation of each ambiguity class (PR-7c.1a dictionary section 6). The class never resolves a value. */
export const AMBIGUITY_TEXT: Record<AmbiguityClass, { label: string; text: string }> = {
  FORMATTING_ONLY: { label: "Formatting differences", text: "The values differ only in punctuation or separators." },
  NESTED_WORDING: { label: "Nested wording", text: "One value's words contain the other's (for example, a more specific description of the same place)." },
  DISTINCT_SAME_SAMPLE: { label: "Different wording within one sample", text: "Different values within one sample unit (for example, the ENA and NCBI copies of a BioSample, or a source feature and its BioSample). This may be a synonym or a submitter inconsistency; it is not resolved." },
  DISTINCT_ACROSS_SAMPLES: { label: "Different values across samples", text: "Different values in different sample records, for example the same sequence obtained from different samples." },
  LITERATURE_VS_DATABASE: { label: "Literature differs from database", text: "A verified literature isolation statement differs from the database sample record." },
};

/** Why an item is not counted as a usable value (value_status). */
export const NOT_USABLE_TEXT: Record<string, string> = {
  reported_missing: "reported as missing (for example 'missing' or 'not collected')",
  invalid_placeholder: "invalid placeholder ('0'); not a habitat value",
  uninformative_placeholder: "uninformative placeholder (root ontology class or a generic word)",
  moved_to_material: "culture or tissue term; listed as sample material, not habitat",
};

export const QUARANTINE_TEXT: Record<string, string> = {
  envo_id_not_found_in_ols: "contains an ENVO identifier that was not found in the ontology (OLS); shown as text only, never as an ontology term",
  unprefixed_numeric_identifier: "a bare number without an ENVO prefix; shown as text only, never as an ontology term",
};

export const ORGANISM_CONTEXT_LABEL = "Organism-level context, not the sampling habitat of this sequence";
export const HOST_TISSUE_NOTE = "Names host tissue: sampling context; no broader habitat is inferred";
export const NO_LINK_TEXT = "No traceable INSDC or sample link; sample records could not be checked.";

const EVIDENCE_ID_RE = /^H[EL][0-9a-f]{12}$/;
const ENVO_RE = /^ENVO:(\d{8})$/;

/** Sentence describing missing physical habitat, following the audit's not-reported scope and link status. */
export function missingnessText(e: HabitatSourceEntry): string | null {
  if (e.grade !== "NOT_REPORTED" || !e.missingness) return null;
  const db = e.missingness.database === "no_traceable_sample_link"
    ? NO_LINK_TEXT.replace(/\.$/, "")
    : "Physical habitat not reported in the linked sample records";
  const lit = {
    not_reviewed: "literature not reviewed",
    inaccessible: "literature not accessible",
    reviewed_not_reported: "not reported in the reviewed literature either",
  }[e.missingness.literature];
  return `${db}; ${lit}.`;
}

/** Host-only wording: the record reports a host but no usable physical habitat. Host is never shown as habitat. */
export function hostOnlyText(e: HabitatSourceEntry): string | null {
  return e.flags.includes("host_association_only") ? "Physical habitat not reported; host reported." : null;
}

export function hostStatusText(e: HabitatSourceEntry): string {
  if (e.host_association_status === "NOT_REPORTED") {
    return e.sample_link === "none" ? NO_LINK_TEXT : "No host is reported in the linked sample records.";
  }
  if (e.host_association_status === "AMBIGUOUS") return "The linked records report differing host values. All are listed; none is chosen.";
  if (e.host_association_status === "REPORTED") return "A host is reported in the linked sample records. A host is a host association, not a physical habitat.";
  return HOST_INFO[e.host_association_status].label + ".";
}

export const envoUrl = (id: string): string | null => {
  const m = ENVO_RE.exec(id);
  return m ? `https://purl.obolibrary.org/obo/ENVO_${m[1]}` : null;
};

/** Safe external URLs built only from validated accession patterns. */
const ACC_URL: Record<string, [RegExp, (a: string) => string]> = {
  biosamples: [/^SAM[NED][A-Z]?\d+$/, (a) => `https://www.ebi.ac.uk/ena/browser/view/${a}`],
  bioprojects: [/^PRJ[NED][A-Z]\d+$/, (a) => `https://www.ebi.ac.uk/ena/browser/view/${a}`],
  insdc: [/^[A-Z]{1,6}\d{5,12}(\.\d+)?$/, (a) => `https://www.ebi.ac.uk/ena/browser/view/${a}`],
  embl_protein_ids: [/^[A-Z]{3}\d{5,7}(\.\d+)?$/, (a) => `https://www.ebi.ac.uk/ena/browser/view/${a}`],
  proteomes: [/^UP\d{9}$/, (a) => `https://www.uniprot.org/proteomes/${a}`],
  assemblies: [/^GC[AF]_\d{9}\.\d+$/, (a) => `https://www.ncbi.nlm.nih.gov/datasets/genome/${a}/`],
};
export function accessionUrl(kind: string, acc: string): string | null {
  const r = ACC_URL[kind];
  return r && r[0].test(acc) ? r[1](acc) : null;
}
/** Hosts that sidecar record/source URLs may point to (INSDC/BioSample browsers and PubMed/PMC/E-utilities). */
const ITEM_URL_HOSTS = new Set(["www.ebi.ac.uk", "www.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"]);
/** A record or retrieval URL from the sidecar, linked only if it is https on an allowlisted host; otherwise text. */
export function itemUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const x = new URL(u);
    return x.protocol === "https:" && ITEM_URL_HOSTS.has(x.host) && !x.username && !x.password ? u : null;
  } catch {
    return null;
  }
}

/** ENVO links for one item: only well-formed ENVO IDs (verified in OLS by the audit) and never for a quarantined item. */
export function envoLinks(i: HabitatItem): { id: string; url: string }[] {
  if (i.quarantine) return [];
  return (i.envo_ids ?? []).flatMap((id) => {
    const url = envoUrl(id);
    return url ? [{ id, url }] : [];
  });
}

export const pubmedUrl = (pmid: string) => (/^\d+$/.test(pmid) ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : null);
export const doiUrl = (doi: string | null | undefined) => (doi && /^10\.\d{4,9}\/\S+$/.test(doi) ? `https://doi.org/${doi}` : null);

export interface ValueGroup {
  /** evidence_source + entity accession: values are grouped by the record that reports them, never merged. */
  key: string;
  source: string;
  entity: string;
  items: HabitatItem[];
}

function byEntity(items: HabitatItem[]): ValueGroup[] {
  const m = new Map<string, ValueGroup>();
  for (const i of items) {
    const key = `${i.evidence_source}|${i.entity_accession}`;
    let g = m.get(key);
    if (!g) m.set(key, (g = { key, source: i.evidence_source, entity: i.entity_accession, items: [] }));
    g.items.push(i);
  }
  return [...m.values()];
}

export interface HabitatView {
  entry: HabitatSourceEntry;
  grade: (typeof GRADE_INFO)[HabitatGrade] & { id: HabitatGrade };
  missing: string | null;
  hostOnly: string | null;
  noLink: boolean;
  ambiguity: { label: string; text: string } | null;
  hostAmbiguity: { label: string; text: string } | null;
  /** Usable values of the four grading roles, grouped by reporting record. */
  physical: ValueGroup[];
  hostTissue: boolean;
  nonstandard: HabitatItem[];
  literatureIsolate: HabitatItem[];
  literatureRejected: HabitatItem[];
  notUsable: HabitatItem[];
  host: ValueGroup[];
  hostNotUsable: HabitatItem[];
  hostDetail: HabitatItem[];
  collection: HabitatItem[];
  collectionMissing: HabitatItem[];
  organismContext: HabitatItem[];
  notes: string[];
  dropped: number;
}

/** Items of one group that pass the structural checks (right group, known role, well-formed evidence ID). */
function clean(e: HabitatSourceEntry, group: HabitatGroup): { items: HabitatItem[]; dropped: number } {
  const raw = (e.items?.[group] ?? []) as HabitatItem[];
  const items = raw.filter((i) => GROUP_OF.get(i.role) === group && EVIDENCE_ID_RE.test(i.evidence_id) && typeof i.value_status === "string");
  return { items, dropped: raw.length - items.length };
}

export function habitatView(e: HabitatSourceEntry): HabitatView {
  let dropped = 0;
  const g = (k: HabitatGroup) => {
    const r = clean(e, k);
    dropped += r.dropped;
    return r.items;
  };
  const phys = g("physical");
  const host = g("host");
  const coll = g("collection");
  // organism context is shown only from its own group and only when it is a literature item
  const org = g("organism_context").filter((i) => i.evidence_source === "literature" && i.literature?.scope === "organism");
  const grading = new Set<string>(GRADING_ROLES);
  const usable = phys.filter((i) => grading.has(i.role) && i.value_status === "usable");
  const notes: string[] = [];
  if (e.flags.includes("geo_discordant")) notes.push("The linked records report more than one country or geographic location.");
  if (e.flags.includes("date_discordant")) notes.push("The linked records report more than one collection date.");
  if (e.flags.includes("tissue_or_culture_only")) notes.push("Only a culture or tissue sample material is reported; it is shown as sample material, not habitat.");
  return {
    entry: e,
    grade: { id: e.grade, ...GRADE_INFO[e.grade] },
    missing: missingnessText(e),
    hostOnly: hostOnlyText(e),
    noLink: e.sample_link === "none",
    ambiguity: e.ambiguity_class ? AMBIGUITY_TEXT[e.ambiguity_class] : null,
    hostAmbiguity: e.host_ambiguity_class ? AMBIGUITY_TEXT[e.host_ambiguity_class] : null,
    physical: byEntity(usable),
    hostTissue: e.flags.includes("host_tissue_isolation_source_only"),
    nonstandard: phys.filter((i) => i.role === "habitat_nonstandard" && i.value_status === "nonstandard_context"),
    literatureIsolate: phys.filter((i) => i.role === "literature_isolate" && i.evidence_source === "literature" && i.literature?.scope === "isolate"),
    literatureRejected: phys.filter((i) => i.role === "literature_rejected" && i.evidence_source === "literature"),
    notUsable: phys.filter((i) => (grading.has(i.role) || i.role === "habitat_nonstandard") && i.value_status !== "usable" && i.value_status !== "nonstandard_context"),
    host: byEntity(host.filter((i) => i.role === "host" && i.value_status === "usable")),
    hostNotUsable: host.filter((i) => i.role === "host" && i.value_status !== "usable"),
    hostDetail: host.filter((i) => i.role === "host_detail"),
    collection: coll.filter((i) => i.value_status !== "reported_missing"),
    collectionMissing: coll.filter((i) => i.value_status === "reported_missing"),
    organismContext: org,
    notes,
    dropped,
  };
}

export interface SourceRow {
  source_acc: string;
  current: boolean;
  representative: boolean;
  grade: HabitatGrade;
  host: HostStatus;
}

/** One row per source record of the MRDB accession; the current source is marked (aria-current). */
export function sourceRows(file: HabitatRecordFile, focus: string): SourceRow[] {
  return file.sources.map((s) => ({
    source_acc: s.source_acc,
    current: s.source_acc === focus,
    representative: s.is_mrdb_representative,
    grade: s.grade,
    host: s.host_association_status,
  }));
}

export type HabitatCheck = { ok: true; entry: HabitatSourceEntry } | { ok: false; reason: string };

/**
 * Accept a habitat file only if it belongs to this MRDB accession and lists exactly the record's source records,
 * each once. Any mismatch (wrong file, merged or missing source records) makes the section show "unavailable".
 */
export function checkHabitatFile(file: HabitatRecordFile | null, mrdbAcc: string, sourceAccs: string[], focus: string): HabitatCheck {
  if (!file) return { ok: false, reason: "missing" };
  if (file.mrdb_acc !== mrdbAcc) return { ok: false, reason: "mrdb_mismatch" };
  if (!Array.isArray(file.sources)) return { ok: false, reason: "malformed" };
  const got = file.sources.map((s) => s.source_acc);
  if (new Set(got).size !== got.length || got.length !== sourceAccs.length || !sourceAccs.every((a) => got.includes(a))) {
    return { ok: false, reason: "source_mismatch" };
  }
  if (file.sources.some((s) => s.mrdb_acc !== mrdbAcc)) return { ok: false, reason: "source_mismatch" };
  const entry = file.sources.find((s) => s.source_acc === focus);
  return entry ? { ok: true, entry } : { ok: false, reason: "source_mismatch" };
}

/** Text for an item value; null means the field is present but empty. */
export const valueText = (i: HabitatItem) => (i.value === null ? "(empty value)" : i.value);
