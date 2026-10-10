"""Addendum step 1: primary-citation pass for the 26 compilation-only E1 records (25 task-D + CryoR2),
plus systematic corrections uncovered during the pass. Produces a sign-off TSV with the same 13 columns as
curation_v160_records.tsv. Reads v1.5.0 read-only; changes nothing in the DB."""
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_W160 = _os.environ.get("MRDB_V160_WORK", _os.path.join(_REPO, "work", "v160_stage1"))  # Stage-1 scratch dir
import sqlite3, re
import pandas as pd

DB = _os.path.join(_REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
W = _os.path.join(_W160, "addendum")
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
t = pd.read_csv(f"{W}/targets.tsv", sep="\t").set_index("source_acc")
lk = pd.read_csv(f"{W}/pmid_lookup.tsv", sep="\t", dtype=str).set_index("pmid")
cp = pd.read_sql("select * from characterized_protein", c).set_index("source_acc")
prot = pd.read_sql("select source_acc, mrdb_acc, protein_name, organism from protein", c).set_index("source_acc")
WRONG = {"30349080": "30349075", "33741996": "33742139"}
COMPILATION = set(WRONG) | set(WRONG.values())


def ref(pmids):
    out = []
    for p in pmids:
        r = lk.loc[p]
        out.append(f"PMID:{p} ({r.first_author} {r.year}, {r.journal}; doi:{r.doi})")
    return "; ".join(out)


def clean(pm):
    """Current pmid string with wrong compilation PMIDs corrected and the ECO pseudo-PMID removed."""
    toks = [x for x in str(pm).split(";") if x and x != "nan" and x != "0000269"]
    toks = [WRONG.get(x, x) for x in toks]
    return ";".join(dict.fromkeys(toks))


COLS = ["group_id", "source_acc", "mrdb_acc", "protein_name", "organism", "field_changed", "old_value", "new_value",
        "rationale", "evidence_ref", "recommended_decision", "user_decision", "user_notes"]
rows = []


def add(group, acc, field, old, new, why, pmids_or_ref, rec):
    p = prot.loc[acc] if acc in prot.index else None
    label = t.loc[acc, "protein_label"] if acc in t.index else (cp.loc[acc, "protein_label"] if acc in cp.index else "")
    evid = ref(pmids_or_ref) if isinstance(pmids_or_ref, list) else pmids_or_ref
    rows.append(dict(group_id=group, source_acc=acc, mrdb_acc=p.mrdb_acc if p is not None else "",
                     protein_name=f"{label} ({p.protein_name})" if p is not None else label,
                     organism=p.organism if p is not None else "", field_changed=field, old_value=old, new_value=new,
                     rationale=why, evidence_ref=evid, recommended_decision=rec, user_decision="", user_notes=""))


F_LINK = "characterized_protein.pmid (+ new assertion_publication support link)"

# ---------- ADD-A: primary functional paper found for this protein ----------
A = [  # acc, primary pmids, rationale, recommendation
    ("L1IFZ3", ["26113638"], "GtACR2 anion conductance shown by patch clamp in the original ACR paper.", "APPROVE"),
    ("A0A1U7EZ03", ["11452084", "7708770", "9450549"],
     "NpSRII phototaxis receptor; structure, cloning with transducer, and functional expression. Mapped record is 97.9% identical over 100% length to UniProt P42196 (NpSRII, strain variant).",
     "APPROVE_WITH_CAVEAT"),
    ("A0ABQ7GHC2", ["22196724"],
     "DChR1 photocurrents first reported in Zhang et al. 2011 Cell (attribution confirmed by Govorunova et al. 2021, PMID 34281394). Full text not machine-readable here; no reference accession available to confirm sequence identity.",
     "APPROVE_WITH_CAVEAT"),
    ("A0ABX5Q1D8", ["28527429"], "NdR2: light-driven Na+ and H+ transport measured in cells and liposomes.", "APPROVE"),
    ("A0ABY3LD08", ["26970049"], "PvR: light-induced pH decrease, CCCP-sensitive outward H+ pump.", "APPROVE"),
    ("A0A4P9TF16", ["16413498"],
     "HtdR (H. turkmenica) light-driven H+ pump. Mapped record is a Natrinema pallidum homolog (99.6% id / 96% cov), not the assayed protein itself.",
     "APPROVE_WITH_CAVEAT"),
    ("A7WQE8", ["23586665"], "OR1 vectorial proton transfer measured (mapped 100% id / 90% cov).", "APPROVE"),
    ("H2BW50", ["25375769"], "GLR transports only Na+ (pump assay).", "APPROVE"),
    ("Q0FYH0", ["25166488"], "Fulvimarina rhodopsin Cl- pump.", "APPROVE"),
    ("Q2RZM2", ["18566451", "19778064"], "SrSRI sensory rhodopsin; signalling complex with SrHtrI.", "APPROVE"),
    ("Q6R5N7", ["16075162"], "HxAR cloned and expressed; photoelectric responses (proton pump).", "APPROVE"),
]
for acc, pm, why, rec in A:
    old = cp.loc[acc, "pmid"]
    new = ";".join(dict.fromkeys(pm + [x for x in clean(old).split(";") if x]))
    add("ADD-A_primary_found", acc, F_LINK, old, new,
        why + " Compilation PMID kept only as the lambda-max source (corrected PMID).", pm, rec)

# ---------- ADD-B: exact-sequence duplicate of a primary-cited sibling ----------
B = [("G0LFX8", "Q18DH8", ["21135094", "22248212", "23720753", "26483542"]),
     ("A0A0C3TEH9", "L1J207", ["26113638", "30158697"]),
     ("B0R5N9", "P02945", ["8676377"]),
     ("A0A495RAM9", "Q5UXY6", ["20802037", "23565724", "24941450"]),
     ("M0JSR0", "Q5V0R5", ["20802037", "23565724", "24941450"]),
     ("A0ABR7ZCQ4", "A0ACD6B968", ["12622809", "15459346", "22872645", "28501588"])]
for acc, sib, pm in B:
    old = cp.loc[acc, "pmid"]
    new = ";".join(dict.fromkeys(pm + [x for x in clean(old).split(";") if x]))
    sib_doi = cp.loc[sib, "doi"]
    add("ADD-B_duplicate_inherit", acc, F_LINK + "; protein.exact_duplicate_of", old, f"{new} | exact_duplicate_of={sib}",
        f"100% identical sequence to {sib} (same exact_nr_cluster). Inherit the sibling's primary functional links "
        f"(sibling DOIs: {sib_doi}). Record kept, but flagged so duplicates are counted once in E1 totals and validation.",
        pm, "APPROVE")
# sibling-side gaps found during the pass
add("ADD-B_duplicate_inherit", "L1J207", F_LINK, cp.loc["L1J207", "pmid"], "26113638;" + clean(cp.loc["L1J207", "pmid"]),
    "GtACR1 reference record lacks its discovery paper; add it.", ["26113638"], "APPROVE")
add("ADD-B_duplicate_inherit", "A0ACD6B968", F_LINK, cp.loc["A0ACD6B968", "pmid"],
    "12622809;15459346;22872645;" + clean(cp.loc["A0ACD6B968", "pmid"]),
    "ASR reference record cites only an NMR oligomer paper and the compilation; add the functional/structural primaries.",
    ["12622809", "15459346", "22872645"], "APPROVE")

# ---------- ADD-C: no primary functional paper found ----------
C = [("A6W8Z2", "KrActR: only HS-AFM oligomer study (PMID 29844455) labels it a proton pump without a transport assay; no pumping measurement found."),
     ("A0A0G9MK34", "EgClR: lambda-max only in the Inoue 2021 compilation; no Cl- transport paper found."),
     ("A0A1C7DB83", "AnClR: lambda-max only in the compilation; no transport paper found."),
     ("A0A0M7BDG0", "JsNaR: lambda-max only in the compilation; no Na+ transport paper found."),
     ("A0A840I7T6", "PoClR2: lambda-max only in the compilation; Parvularcula hits are the xenorhodopsin PoXeR, not this ClR."),
     ("A0ABX5PZH6", "NdR1: genome paper (PMID 23292138) assigns it as a proteorhodopsin by sequence only; NdR2 paper does not assay NdR1.")]
for acc, why in C:
    add("ADD-C_no_primary_retier", acc,
        "function_evidence.evidence_level; characterized_protein.e1_eligible; e1_exclusion_reason",
        "E1 (experimental:this_protein); e1_eligible=1",
        "not E1: tier recomputed by pipeline rules (E2 homology / E3 clade / E4 motif); e1_eligible=0; e1_exclusion_reason=lambda_max_only_compilation",
        why + " Lambda-max value is kept (spectral data are genuine); only the functional E1 claim is withdrawn. Alternative: keep E1 with a 'function_from_compilation' flag.",
        "Searched Europe PMC by organism/protein name; compilation supplementary tables have no per-protein reference column.",
        "RETIER")

# ---------- ADD-D: candidate paper exists but identity to the assayed protein unverified ----------
D = [("A0A0P6XBM7", ["36724978"], "BcNaR: BeNaR Na+ pump was characterised from 'Bellilinea sp.'; paper not open access and gives no accession, so identity to B. caldifistulae A0A0P6XBM7 (the only Bellilinea rhodopsin in UniProt besides heliorhodopsin) cannot be confirmed."),
     ("A0ACE3JIR6", ["26970049", "26260121"], "PaR: PvR paper reports three DTG proteins as outward H+ pumps but only PvR is named in the abstract; whether P. ananatis rhodopsin is one of the three needs the full text.")]
for acc, pm, why in D:
    add("ADD-D_unverified_manual", acc, "characterized_protein.curation flag", "E1, compilation-only link",
        "E1 retained, flagged needs_manual; candidate primary recorded in curator_note", why, pm, "DEFER_FLAG")

# ---------- ADD-E: CryoR2 ----------
acc = "A0ABF7PQ05"
add("ADD-E_cryor2", acc, "characterized_protein.pmid; publication(id 69).pmid; exp_class (needs_manual resolved)",
    "pmid=NULL; exp_class=photoreceptor_no_transport (needs_manual: possibly proton_pump_inward)",
    "pmid=40614199;41580893; exp_class=photoreceptor_no_transport KEPT; needs_manual closed",
    "Full text checked: E. coli pH assays of the selected CryoRs showed no H+/Cl-/Na+ transport (with and without CCCP); "
    "liposome and NG108-15 patch-clamp experiments were done on CryoR1 only. No CryoR2-specific transport evidence exists, "
    "so inward-pump is not transferable. Warrelmann 2026 adds pH-dependent spectroscopy only. The existing approved link "
    "(publication 69, doi 10.1126/sciadv.adv1015) lacks its PMID; fill it. Note CryoR2 = A0ABF7PQ03 = A0AC62AE26 (identical, see ADD-I).",
    ["40614199", "41580893"], "APPROVE")

# ---------- ADD-F: systematic wrong PMIDs (DOIs correct) ----------
for tb in ["characterized_protein", "spectral_audit"]:
    for w, r in WRONG.items():
        n = c.execute(f"select count(*) from {tb} where ';'||pmid||';' like ?", (f"%;{w};%",)).fetchone()[0]
        add("ADD-F_pmid_correction", f"[{n} rows]", f"{tb}.pmid", w, r,
            f"PMID {w} is a different paper; DOI {lk.loc[r, 'doi']} in the same rows resolves to PMID {r} ({lk.loc[r, 'first_author']} {lk.loc[r, 'year']}). Fix keyed on DOI.",
            ref([r]), "APPROVE")

# ---------- ADD-G: ECO pseudo-PMID ----------
for tb in ["characterized_protein", "spectral_audit"]:
    n = c.execute(f"select count(*) from {tb} where ';'||pmid||';' like '%;0000269;%'").fetchone()[0]
    add("ADD-G_pseudo_pmid", f"[{n} rows]", f"{tb}.pmid", "0000269 (token)", "(token removed)",
        "'0000269' is the ECO:0000269 evidence code parsed as a PMID during UniProt ingestion; not a publication.",
        "UniProt evidence code ECO:0000269 (experimental evidence used in manual assertion)", "APPROVE")

# ---------- ADD-H: novel-family layer retraction ----------
add("ADD-H_novel_layer_correction", "A0ACD6B968", "novel_family_candidates (release package)", "1 candidate", "0 candidates",
    "The single 'novel' candidate is canonical Anabaena sensory rhodopsin (Q8YSC4, alr3165), already an E1 record in the corpus and 100% identical to A0ABR7ZCQ4. The layer excluded known proteins by the pre-resolution accession and never re-checked the resolved accession. Fix: exclude by resolved accession and by sequence hash.",
    ["15459346"], "APPROVE")

# ---------- ADD-I: exact-duplicate E1 records ----------
e1 = pd.read_sql("""select f.source_acc, r.exact_nr_cluster from function_evidence f join redundancy r using(source_acc)
                    where f.evidence_level='E1'""", c)
dup = e1.groupby("exact_nr_cluster").source_acc.apply(lambda s: sorted(s)).loc[lambda s: s.str.len() > 1]
for cl, members in dup.items():
    add("ADD-I_e1_exact_duplicates", ";".join(members), "redundancy.e1_representative (new column)", "none",
        f"representative={members[0]}; others flagged",
        f"{len(members)} E1 records share exact_nr_cluster {cl}. Keep all records; count once in E1 totals and in validation.",
        "redundancy.exact_nr_cluster (sequence-identical)", "APPROVE")

# ---------- ADD-J: accession_map many-to-one ----------
n_multi = c.execute("select count(*) from (select mrdb_acc from accession_map group by mrdb_acc having count(distinct source_acc)>1)").fetchone()[0]
n_src, n_mrdb = c.execute("select count(distinct source_acc), count(distinct mrdb_acc) from accession_map").fetchone()
add("ADD-J_accession_map_disclosure", f"[{n_multi} MRDB accessions]", "documentation / release notes", "undisclosed",
    f"disclose: {n_src} source accessions map to {n_mrdb} MRDB accessions; {n_multi} MRDB accessions carry >1 source accession",
    "Sequence-identical source entries share one MRDB accession by design, but this was not documented and lets identical proteins appear as separate E1 records.",
    "accession_map table", "APPROVE")

out = pd.DataFrame(rows, columns=COLS)
out.to_csv(f"{W}/curation_v160_addendum_citations.tsv", sep="\t", index=False)
print(out.groupby(["group_id", "recommended_decision"]).size().to_string())
print("E1 duplicate clusters:", len(dup), "records:", sum(len(m) for m in dup), "-> distinct E1 sequences:",
      e1.exact_nr_cluster.nunique(), "of", len(e1))
