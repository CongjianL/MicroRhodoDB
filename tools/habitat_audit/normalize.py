"""Field-role mapping and value normalization (fixed, reviewed vocabularies).

A source attribute is mapped to exactly one role. Only the five HABITAT_ROLES
can make a record DIRECT_SAMPLE. Geography/date/depth/material/context are
reported but never count as habitat. No value is inferred from taxonomy,
organism name, sequence similarity or geography.
"""
from __future__ import annotations

import re

HABITAT_ROLES = ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "host")
OTHER_ROLES = ("habitat_nonstandard", "sample_material", "country", "lat_lon", "lat", "lon", "collection_date", "depth",
               "host_detail", "strain", "isolate", "environmental_sample", "package", "checklist",
               "metagenome_source", "investigation_type", "sample_title", "sample_description", "organism")

# Keys are lower-cased tag names with '_', '-' and spaces collapsed to a single space.
ROLE_MAP = {
    # MIxS triad (current names, ENA display names) and legacy biome/feature/material (MIxS mapping)
    "env broad scale": "env_broad_scale", "broad scale environmental context": "env_broad_scale",
    "env biome": "env_broad_scale", "environment (biome)": "env_broad_scale", "biome": "env_broad_scale",
    "environment biome": "env_broad_scale",
    "env local scale": "env_local_scale", "local environmental context": "env_local_scale",
    "local scale environmental context": "env_local_scale",
    "env feature": "env_local_scale", "environment (feature)": "env_local_scale",
    "environment feature": "env_local_scale", "feature": "env_local_scale",
    "env medium": "env_medium", "environmental medium": "env_medium", "env material": "env_medium",
    "environment (material)": "env_medium", "environment material": "env_medium", "material": "env_medium",
    "isolation source": "isolation_source", "isolation source host associated": "isolation_source",
    "isolation source non host associated": "isolation_source",
    "host": "host", "specific host": "host", "host scientific name": "host", "nat host": "host",
    "natural host": "host",
    # non-standard habitat-like tags: reported verbatim, never graded (outside the agreed usable fields)
    "environment": "habitat_nonstandard", "habitat": "habitat_nonstandard", "isolation site": "habitat_nonstandard",
    "source of isolate": "habitat_nonstandard", "seabed habitat": "habitat_nonstandard",
    # material (never habitat)
    "tissue": "sample_material", "tissue type": "sample_material", "cell type": "sample_material",
    "cell line": "sample_material", "sample material": "sample_material", "dev stage": "sample_material",
    "tissue lib": "sample_material", "sample type": "sample_material",
    # host details (reported, not counted)
    "host body site": "host_detail", "host tissue sampled": "host_detail", "host taxid": "host_detail",
    "host tax id": "host_detail", "host common name": "host_detail", "host body habitat": "host_detail",
    "host description": "host_detail", "body site": "host_detail", "plant body site": "host_detail",
    "plant structure": "host_detail", "plant struc": "host_detail",
    # geography / date / depth (reported separately, never habitat)
    "geo loc name": "country", "country": "country", "geographic location (country and/or sea)": "country",
    "geographic location (region and locality)": "country",
    "lat lon": "lat_lon", "geographic location (latitude)": "lat", "geographic location (longitude)": "lon",
    "latitude": "lat", "longitude": "lon", "lat": "lat", "lon": "lon", "location": "lat_lon",
    "collection date": "collection_date", "depth": "depth", "geographic location (depth)": "depth",
    # identity / sample-type inputs
    "strain": "strain", "sub strain": "strain", "isolate": "isolate",
    "environmental sample": "environmental_sample", "metagenome source": "metagenome_source",
    "metagenomic source": "metagenome_source", "ncbi submission package": "package",
    "ena checklist": "checklist", "organism": "organism", "scientific name": "organism",
    "investigation type": "investigation_type",
}

MISSING_RE = re.compile(
    r"^(missing|not collected|not applicable|not provided|not available|not determined|restricted access|"
    r"unknown|unspecified|na|n/a|n\.a\.|none|null|nan|-|--|\.|\?)(\s*[:;,(].*)?$", re.I)

# isolation_source values that describe the material/tissue of the organism, not where it was sampled.
TISSUE_TERMS = {
    "leaf", "leaves", "root", "roots", "stem", "stems", "shoot", "shoots", "flower", "flowers", "seed", "seeds",
    "fruit", "fruiting body", "fruiting bodies", "mycelium", "mycelia", "hyphae", "spores", "conidia",
    "whole organism", "whole body", "whole plant", "whole cell", "whole cells", "cells", "cell", "tissue",
    "thallus", "sporophyte", "gametophyte", "protonema", "rhizoid", "blade", "frond",
}
# Whole-value culture/laboratory descriptions (a culture mentioned inside a longer habitat
# description, e.g. "enrichment culture from lake sediment", is NOT matched).
CULTURE_RE = re.compile(
    r"^(axenic |pure |unialgal |clonal |laboratory |lab |cell |stock |batch |continuous )?cultures?$|"
    r"^culture collection$|^(laboratory|lab) (strain|stock|isolate)s?$|^laboratory$|^cultured cells$|"
    r"^(cell|tissue) lines?$|^strain collection$|^(viral )?plaques?$|"
    r"^.*\b(agar|broth)\b.*$|^.*\b(culture|growth|isolation) media?$|^[a-z0-9][a-z0-9\-+]* medium$", re.I)

# Explicit but uninformative placeholder values (root ENVO classes or the bare field name).
PLACEHOLDER_ENVO = {"ENVO:00010483", "ENVO:00000428", "ENVO:01000254", "ENVO:00002297", "ENVO:01001110",
                    "ENVO:00002036", "ENVO:01000813"}
PLACEHOLDER_TEXT = {"environmental material", "environment material", "biome", "environmental feature",
                    "environment", "environmental system", "environmental sample", "other", "sample"}


def is_placeholder(v: str | None, envo_ids: list[str]) -> bool:
    s = re.sub(r"\s*[\[(]?\s*envo[:_ ]?\d{7,8}\s*[\])]?\s*", " ", norm_value(v)).strip(" .;,|")
    if envo_ids and set(envo_ids) <= PLACEHOLDER_ENVO:
        return True
    return s in PLACEHOLDER_TEXT


def tag_key(tag: str | None) -> str:
    """Lower case; '_', '-' and whitespace collapsed; non-printable / replacement characters dropped
    (e.g. a submitted tag 'isolation source non-host-associated\ufffd')."""
    t = re.sub(r"[^\x20-\x7e]", "", tag or "")
    return re.sub(r"[\s_\-]+", " ", t.strip().lower()).strip()


def role_for(tag: str | None) -> str | None:
    return ROLE_MAP.get(tag_key(tag))


def norm_value(v: str | None) -> str:
    """Comparison form: lower case, whitespace collapsed (the agreed rule)."""
    return re.sub(r"\s+", " ", (v or "").strip()).lower()


def is_missing(v: str | None) -> bool:
    s = norm_value(v)
    return s == "" or bool(MISSING_RE.match(s))


def is_tissue_term(v: str | None) -> bool:
    return norm_value(v).rstrip(".") in TISSUE_TERMS


def is_culture_term(v: str | None) -> bool:
    return bool(CULTURE_RE.match(norm_value(v).rstrip(".")))


def binomial(name: str | None) -> str:
    """First two words of an organism name, lower case (used ONLY for the host==self check)."""
    w = re.sub(r"[\[\]]", "", norm_value(name)).split(" ")
    return " ".join(w[:2]) if len(w) >= 2 else (w[0] if w else "")


VIRAL_RE = re.compile(r"\b(virus|viruses|phage|bacteriophage|virophage)\b", re.I)


def host_is_self(host: str | None, organism_names: list[str], organism_taxids: list[str],
                 host_taxid: str | None = None, viral: bool = False) -> bool:
    """True when the reported host is the record's own organism (a submission artefact).
    Exact full-name or taxid match always counts; the binomial match is NOT applied to viruses,
    whose names start with their host's binomial (e.g. 'Emiliania huxleyi virus 86')."""
    h = norm_value(host)
    if not h:
        return False
    if host_taxid and str(host_taxid) in {str(t) for t in organism_taxids if t}:
        return True
    names = [o for o in organism_names if o]
    if any(h == norm_value(o) for o in names):
        return True
    if viral or any(VIRAL_RE.search(o) for o in names):
        return False
    hb = binomial(h)
    for o in names:
        ob = binomial(o)
        if len(ob.split()) == 2 and not ob.endswith((" sp.", " sp")) and hb == ob:
            return True
    return False


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"), 1)}


def date_key(v: str | None) -> str:
    """Comparison form for collection dates (flagging only): ISO-like YYYY[-MM[-DD]]."""
    s = norm_value(v)
    m = re.match(r"^(\d{1,2})-([a-z]{3})-(\d{4})$", s)
    if m and m.group(2) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"^([a-z]{3})-(\d{4})$", s)
    if m and m.group(1) in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    return s


def geo_key(v: str | None) -> str:
    """Comparison form for geography (flagging only): whitespace around ':' and ',' removed."""
    return re.sub(r"\s*([:,;])\s*", r"\1", norm_value(v))
