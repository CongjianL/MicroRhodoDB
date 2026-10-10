"""Stage 1 (novel-family candidate layer), final consolidation step.

Combines the EBI-hosted-index search results (fetch_and_filter_candidates.py) and the
local current-Swiss-Prot supplementary search (local_swissprot_search.py) into a single
final candidate table + a combined per-family funnel summary, for the v1.6.0
`novel_family_candidate` DB table (built in Stage 2) and for the response-to-referee /
report documentation.
"""
import pandas as pd

CAND = "/workspace/v160/novel/candidates"

FAMS = ["viral_rhodopsin", "schizorhodopsin", "xenorhodopsin", "bestrhodopsin", "MerMAID"]

HARMONIZED_COLS = ["family", "source_db", "query_accession", "resolved_accession",
                   "identifier", "description", "species", "taxonomy_id", "architecture",
                   "score", "evalue", "seq_length", "has_retinalK", "mapali_window"]

# ---- 1. Final candidate table: union of EBI-pass + Swiss-Prot-pass records ----
ebi_pass = pd.read_csv(f"{CAND}/novel_family_candidates_retinalK_pass.tsv", sep="\t")
ebi_pass = ebi_pass[ebi_pass["has_retinalK"] == True].copy()
ebi_pass["source_db"] = "ebi_hmmer_uniprot_snapshot"
ebi_pass["query_accession"] = ebi_pass["accession"]
ebi_final = ebi_pass[["family", "source_db", "query_accession", "resolved_accession",
                      "identifier", "description", "species", "taxonomy_id", "architecture",
                      "score", "evalue", "seq_length", "has_retinalK", "mapali_window"]]

sprot_pass = pd.read_csv(f"{CAND}/swissprot_candidates_retinalK_pass.tsv", sep="\t")
if len(sprot_pass):
    sprot_pass = sprot_pass[sprot_pass["has_retinalK"] == True].copy()
sprot_pass["source_db"] = "swissprot_current"
sprot_pass["query_accession"] = sprot_pass.get("accession")
sprot_pass["resolved_accession"] = sprot_pass.get("accession")  # Swiss-Prot hits are already live/current
sprot_pass["identifier"] = sprot_pass.get("swissprot_entry")
sprot_pass["species"] = None
sprot_pass["taxonomy_id"] = None
sprot_pass["architecture"] = None
for c in HARMONIZED_COLS:
    if c not in sprot_pass.columns:
        sprot_pass[c] = None
sprot_final = sprot_pass[HARMONIZED_COLS] if len(sprot_pass) else pd.DataFrame(columns=HARMONIZED_COLS)

final_candidates = pd.concat([ebi_final, sprot_final], ignore_index=True)
# De-duplicate on resolved_accession in case the same live protein surfaced from both sources
final_candidates = final_candidates.drop_duplicates(subset=["family", "resolved_accession"])
final_candidates.to_csv(f"{CAND}/novel_family_candidates_FINAL_v160.tsv", sep="\t", index=False)

# ---- 2. Combined per-family funnel summary ----
ebi_funnel = pd.read_csv(f"{CAND}/filter_funnel.tsv", sep="\t")
ebi_counts = pd.read_csv(f"{CAND}/novel_family_candidate_counts.tsv", sep="\t").rename(
    columns={"n_prefilter_novel": "ebi_n_resolved_live",
             "n_length_pass": "ebi_n_length_pass",
             "n_retinalK_pass": "ebi_n_retinalK_pass"})
sprot_funnel = pd.read_csv(f"{CAND}/swissprot_funnel.tsv", sep="\t").rename(
    columns={"n_sprot_hits": "sprot_n_raw_hits_Ele10",
             "n_novel_excl_known": "sprot_n_excl_known",
             "n_length_pass": "sprot_n_length_pass",
             "n_retinalK_pass": "sprot_n_retinalK_pass"})

combined = ebi_funnel.rename(columns={
    "n_total_hits": "ebi_n_total_hits", "n_included": "ebi_n_included",
    "n_has_opsin_domain": "ebi_n_has_PF01036", "n_evalue_pass": "ebi_n_evalue_pass",
    "n_novel_candidates": "ebi_n_excl_known"})
combined = combined.merge(ebi_counts[["family", "ebi_n_resolved_live", "ebi_n_length_pass", "ebi_n_retinalK_pass"]],
                           on="family")
combined = combined.merge(sprot_funnel, on="family")

final_counts_by_fam = final_candidates.groupby("family").size().reindex(FAMS, fill_value=0)
combined = combined.set_index("family").reindex(FAMS)
combined["final_combined_candidates"] = final_counts_by_fam
combined = combined.reset_index()
combined.to_csv(f"{CAND}/combined_funnel_summary_v160.tsv", sep="\t", index=False)

print("=== Final novel-family candidates (union of EBI + Swiss-Prot, all filters passed) ===")
print(final_candidates.to_string(index=False) if len(final_candidates) else "  (none)")
print()
print("=== Combined per-family funnel summary ===")
print(combined.to_string(index=False))
print()
print(f"TOTAL final candidates across all 5 families: {len(final_candidates)}")
