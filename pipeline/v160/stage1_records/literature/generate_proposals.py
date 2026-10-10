import sys, json, re, sqlite3, csv
sys.path.insert(0, '.')
from lit import epmc_pmid, crossref, uniprot_function, uniprot_refs, sentences

I = '/mnt/shared-workspace/v160/curation_inputs/'
import pandas as pd
con = sqlite3.connect(f'file:{I}microrhododb_v1.5.0.sqlite?mode=ro', uri=True)
landmarks = pd.read_csv(I+'auditC_landmarks_uniprot.tsv', sep='\t')
checked = pd.read_csv(I+'auditC_landmark_function_check.tsv', sep='\t').set_index('source_acc')
ext = pd.read_csv(I+'external_positives_new.tsv', sep='\t')
extlit = pd.read_csv(I+'auditC_literature_landmarks_external_positives.tsv', sep='\t').set_index('ext_acc')
linkless = pd.read_csv(I+'e1_without_publication_link.tsv', sep='\t')
uni = json.load(open('cache/uniprot_summary.json'))
rcsb = json.load(open('cache/rcsb_summary.json'))
epmcD = json.load(open('cache/epmc_taskD_batch.json'))

rows = []
pid = [0]
def add(task, source_acc, mrdb_acc, protein_label, field, old, new, summary, pmid, doi, title, year, snippet, snippet_source, decision, notes):
    pid[0] += 1
    rows.append(dict(proposal_id=f'P{pid[0]:03d}', task=task, source_acc=source_acc, mrdb_acc=mrdb_acc,
        protein_label=protein_label, field=field, old_value=old, new_value=new, evidence_summary=summary,
        pmid=pmid, doi=doi, title=title, year=year, snippet=snippet, snippet_source=snippet_source,
        proposer='Biomni curation agent', decision=decision, notes=notes))

def mrdb(acc):
    r = con.execute('select mrdb_acc from protein where source_acc=?', (acc,)).fetchone()
    return r[0] if r else ''

def verify(snip, text):
    return snip in (text or '')

# ============ verify two suspect PMIDs flagged during Task A research ============
# Resolution (this session): PMID 30158607 ("Measurements of the gravitational constant
# using two independent methods", Nature 2018) is NOT present anywhere in the 41-record
# Task D input table -- it does not contaminate any current citation. The only GtACR1-
# related PMID actually present in the data is 30158697 (L1J207), which independently
# resolves to "Structural mechanisms of selectivity and gating in anion channelrhodopsins"
# (Kim et al. 2018, DOI 10.1038/s41586-018-0504-5) -- a genuine, directly relevant GtACR
# structural paper (companion paper to PMID 30158696 / DOI 10.1038/s41586-018-0511-6,
# "Crystal structure of the natural anion-conducting channelrhodopsin GtACR1", Li et al.,
# same 2018 Nature issue). Both papers are legitimate primary GtACR1 structural citations
# from different groups; 30158697 is NOT a citation error and needs no correction.
GTACR1_KIM2018 = epmc_pmid('30158697')
GTACR1_LI2018_DOI_SEARCH = crossref('10.1038/s41586-018-0511-6')
assert GTACR1_KIM2018['doi'] == '10.1038/s41586-018-0504-5', 'unexpected DOI for PMID 30158697'
# PMID 35114111 ("Structural basis for channel conduction in the pump-like channelrhodopsin
# ChRmine", Cell 2022) traced: it belongs to Task C's external-positive ChRmine entry
# (7W9W_A), not to any of the 41 Task D records -- confirmed by grep, it does not appear
# in e1_without_publication_link.tsv. Used below in Task C context notes only.
CHRMINE_PMID = epmc_pmid('35114111')

c2 = crossref('10.1038/s41593-022-01094-6')  # HcKCR1 Govorunova 2022, confirms correct PMID=35726059 (used in Task A)

# ============================= TASK A =============================
r = epmc_pmid('31024506')
add('A', 'A0A0D1E071', mrdb('A0A0D1E071'), 'UmOps1', 'evidence_level+exp_class',
    'evidence_level=E4;func_class=sensory;exp_class=None',
    'evidence_level=E1;func_class=proton_pump;exp_class=proton_pump_outward',
    'Patch-clamp electrophysiology on UmOps1 (heterologously expressed) shows green-light-driven outward proton pump activity.',
    r['pmid'], r['doi'], r['title'], r['year'],
    'Patch-clamp studies demonstrated that both rhodopsins are green light-driven outward rectifying proton pumps.',
    'abstract', '', 'Direct experimental evidence (this protein); matches brief exactly.')

add('A', 'A0A0D1EC87', mrdb('A0A0D1EC87'), 'UmOps2', 'evidence_level+exp_class',
    'evidence_level=E4;func_class=sensory;exp_class=None',
    'evidence_level=E1;func_class=proton_pump;exp_class=proton_pump_outward',
    'Patch-clamp electrophysiology on UmOps2 shows typical outward-directed, light-driven proton-pump behaviour.',
    r['pmid'], r['doi'], r['title'], r['year'],
    'In contrast, UmOps2 showed the typical behavior of light-driven, outwardly directed proton pumps, whereas UmOps3 did not exhibit any electrogenity.',
    'abstract', '', 'Direct experimental evidence (this protein); matches brief exactly.')

add('A', 'A0A0D1DV72', mrdb('A0A0D1DV72'), 'UmOps3', 'no_change',
    'evidence_level=E4;func_class=sensory (motif_only:DTS)', 'no_change',
    'PMID 31024506 tested UmOps3 by patch-clamp and found NO electrogenic (pump/channel) activity; no positive transport OR sensory-transduction function was experimentally demonstrated for UmOps3, so there is no evidence to promote it to E1 for any exp_class. Leaving the existing E4 motif-based sensory call as-is, per brief instruction.',
    r['pmid'], r['doi'], r['title'], r['year'],
    'In contrast, UmOps2 showed the typical behavior of light-driven, outwardly directed proton pumps, whereas UmOps3 did not exhibit any electrogenity.',
    'abstract', '', 'As instructed: leave as-is and report that no function was shown (negative electrophysiology result only).')

r = epmc_pmid('39305959')
add('A', 'A0A5B2VFD4', mrdb('A0A5B2VFD4'), 'Glycylhalorhodopsin (GHR)', 'evidence_level+exp_class',
    'evidence_level=E3;func_class=proton_pump;exp_class=None',
    'evidence_level=E1;func_class=anion_pump;exp_class=anion_pump (direction inward)',
    'Ion-transport assay on GHR (PDB 8XX8, this UniProt sequence) shows light-driven inward anion (Cl-/SO4 2-) pump activity, not a proton pump.',
    r['pmid'], r['doi'], r['title'], r['year'],
    'The ion-transport assay revealed that they function as light-driven inward anion pumps similar to halorhodopsins previously found in archaea and bacteria.',
    'abstract', '', 'Confirms the already-flagged audit verdict (incorrect) with a verbatim abstract quote.')

r = epmc_pmid('37130895')
add('A', 'A0A411LJN5', mrdb('A0A411LJN5'), 'SpaR', 'evidence_level+exp_class',
    'evidence_level=E4;func_class=light_gated_channel;exp_class=None',
    'evidence_level=E1;func_class=proton_pump;exp_class=proton_pump_outward',
    'Function-structure study of SpaR (PDB 8ANQ, this UniProt sequence), representative of "mirror proteorhodopsins", shows outward H+ pumping, active even at acidic pH.',
    r['pmid'], r['doi'], r['title'], r['year'],
    'Here we describe conceptually new bacterial rhodopsins which are operating as outward proton pumps at acidic pH.',
    'abstract', '', 'Confirms the already-flagged audit verdict (incorrect) with a verbatim abstract quote.')

r = epmc_pmid('15274618')
add('A', 'Q9UW81', mrdb('Q9UW81'), 'NOP-1 (Neurospora rhodopsin, NR)', 'evidence_level+exp_class',
    'evidence_level=E4;func_class=proton_pump;exp_class=None',
    'evidence_level=E1;func_class=photoreceptor_unassigned;exp_class=photoreceptor_no_transport',
    'FTIR/photocycle study explicitly states NR does not pump protons (lacks the BR-like reprotonation switch); consistent with a photoreceptor/sensory role rather than active transport. Vocabulary mapping follows the existing DB precedent for CryoR1/CryoR2 (func_class=photoreceptor_unassigned + exp_class=photoreceptor_no_transport).',
    r['pmid'], r['doi'], r['title'], r['year'],
    'Nevertheless, NR does not appear to pump protons, suggesting the absence of the reprotonation switch that is necessary for the active transport.',
    'abstract', '', 'Exact wording verified as requested by brief.')

# A5: exoKCR1 / ExoC110T / GtCCR2 / CryoR1  -------------------------------------------------
r82 = epmc_pmid('39181878')
r_wt = epmc_pmid('35726059')  # correct PMID for Govorunova 2022 Nat Neurosci (see note below)
add('A', 'A0ABF7PQ82', mrdb('A0ABF7PQ82'), 'exoKCR1', 'evidence_level+exp_class',
    'evidence_level=E5;func_class=unresolved;exp_class=None',
    'evidence_level=E1;func_class=light_gated_channel;exp_class=potassium_channel',
    ('Sequence verification (this session): the 259-aa exoKCR1 UniProt sequence (PDB 8ZAO) is an EXACT substring match (0 mismatches) of the 265-aa wild-type HcKCR1 protein sequence deposited as NCBI UOK93384.1 (the construct functionally characterized by Govorunova et al. 2022, PK/PNa=23 K+-selective channelrhodopsin). PMID 39181878 (this accession\'s own citation) also reports photocurrent recordings on "wild type KCR1". exoKCR1 is therefore the same (unmutated) protein as HcKCR1 and the K+-channel function is directly applicable.'),
    r82['pmid'], r82['doi'], r82['title'], r82['year'],
    'In contrast, H. catenoides kalium channelrhodopsin (KCR1) binds an endogenous retinal in its canonical retinal binding pocket under identical condition. However, exogenous ATR reduces the photocurrent magnitude of wild type KCR1 and also inhibits its leaky mutant C110T.',
    'abstract', '',
    f'Primary functional characterization of wild-type HcKCR1 is Govorunova et al. 2022 Nat Neurosci, correct PMID={r_wt["pmid"]} doi={r_wt["doi"]} (see note on PMID error below); snippet from that abstract: "The permeability ratio PK/PNa of 23 makes H. catenoides KCR1 (HcKCR1) a powerful hyperpolarizing tool..." Sequence identity check script: cache/seq_check_kcr.txt')

add('A', 'A0ABF7PQ84', mrdb('A0ABF7PQ84'), 'ExoC110T (C110T class1/2)', 'evidence_level+exp_class',
    'evidence_level=E5;func_class=unresolved;exp_class=None',
    'evidence_level=E1;func_class=light_gated_channel;exp_class=potassium_channel',
    'Same paper (PMID 39181878) assays this construct ("leaky mutant C110T") alongside wild-type KCR1; retains K+-channel behaviour (leaky/slow-cycling variant). Promoted to E1 per brief, but see paired engineered_flag proposal: this is a confirmed single-point mutant (C110T), not a natural sequence.',
    r82['pmid'], r82['doi'], r82['title'], r82['year'],
    'In contrast, H. catenoides kalium channelrhodopsin (KCR1) binds an endogenous retinal in its canonical retinal binding pocket under identical condition. However, exogenous ATR reduces the photocurrent magnitude of wild type KCR1 and also inhibits its leaky mutant C110T.',
    'abstract', '', 'Function class follows brief; construct status flagged separately (see engineered_flag proposal for this accession).')

add('A', 'A0ABF7PQ84', mrdb('A0ABF7PQ84'), 'ExoC110T (C110T class1/2)', 'engineered_flag',
    'unflagged', 'engineered: confirmed single-point C110T mutant (laboratory construct), not a natural isolate variant',
    'Direct sequence alignment (this session) of A0ABF7PQ84 vs A0ABF7PQ82 (exoKCR1, wild type) shows exactly one substitution, Cys->Thr at the residue equivalent to position 110 (PDB 8ZAP/8ZAQ entity pdbx_mutation also recorded; UniProt submission name is literally "C110T"). The source paper (PMID 39181878) calls it "its leaky mutant C110T", i.e. an engineered slow-cycling variant used for mechanistic study, analogous to the C110A mutant used for HcKCR1 structures.',
    r82['pmid'], r82['doi'], r82['title'], r82['year'],
    'exogenous ATR reduces the photocurrent magnitude of wild type KCR1 and also inhibits its leaky mutant C110T.',
    'abstract', '', 'Answers brief: this is a construct, not a natural variant.')

rL = epmc_pmid('29078348')
add('A', 'L1K1K8', mrdb('L1K1K8'), 'GtCCR2', 'evidence_level+exp_class',
    'evidence_level=E5;func_class=unresolved;exp_class=None',
    'evidence_level=E1;func_class=light_gated_channel;exp_class=cation_channel',
    'Primary electrophysiological characterization (laser flash-induced photocurrents) directly on Guillardia theta cation channelrhodopsin 2 (GtCCR2), which corresponds to this UniProt accession (PDB 8YEJ/8YEK map to L1K1K8). Newer cryo-EM paper PMID 39232582 (DOI 10.1016/j.molcel.2024.08.016, 2024) provides structural/secondary support and is the accession\'s own UniProt citation.',
    rL['pmid'], rL['doi'], rL['title'], rL['year'],
    'Here we analyze laser flash-induced photocurrents and photochemical conversions in Guillardia theta cation channelrhodopsin 2 (GtCCR2) and its mutants.',
    'abstract', '', 'Primary paper identified by this session\'s literature search (not the paper named in the brief, which is the structural follow-up); both are consistent, cation_channel.')

ft = json.load(open('cache/pmc_40614199_fulltext.json'))['text']
snip_cryor1 = 'Electrophysiology of CryoR1 revealed light-driven inward proton pumping activity of the protein modulated by UV light.'
assert verify(snip_cryor1, ft)
r40 = epmc_pmid('40614199')
add('A', 'A0A1I3DJQ0', mrdb('A0A1I3DJQ0'), 'CryoR1', 'evidence_level+exp_class',
    'evidence_level=E5;func_class=unresolved;exp_class=None',
    'evidence_level=E1;func_class=proton_pump_inward;exp_class=proton_pump_inward',
    'Full-text Results (Europe PMC XML, PMC12227055): "Electrophysiology of CryoR1 revealed light-driven inward proton pumping activity of the protein modulated by UV light." CryoR1 is additionally proposed as a UV sensor (abstract), i.e. a dual-role photoreceptor/ion-pump; exp_class vocabulary has no combined term, so proton_pump_inward (the directly measured transport activity) is used; the UV-sensing role is noted for the curator.',
    r40['pmid'], r40['doi'], r40['title'], r40['year'],
    snip_cryor1, 'full_text', '', 'Abstract also states: "CryoRs are sensors for UV irradiation and are also capable of inward proton translocation modulated by UV light" (verified verbatim in abstract).')

# Bonus/auxiliary finding beyond explicit brief scope: CryoR2 siblings may need same re-check
add('A', 'A0ABF7PQ05', mrdb('A0ABF7PQ05'), 'Cryorhodopsin CryoR2', 'exp_class',
    'evidence_level=E1;func_class=photoreceptor_unassigned;exp_class=photoreceptor_no_transport',
    'needs_manual_review (possibly proton_pump_inward or dual-function, pending CryoR2-specific electrophysiology check)',
    'BONUS finding, NOT explicitly requested by the brief (flagged for transparency only). A0ABF7PQ05/A0AC62AE26 (CryoR2) and A0ABF7PQ03 (PDB 8R96, an older pre-print-stage entry) share the same study as CryoR1 (PMID 40614199, "CryoRhodopsins: a new clade..." working title -> final "...comprehensive characterization..."). The full text electrophysiology sentence found in this session names CryoR1 specifically; a CryoR2-specific inward-pumping sentence was not located within the excerpts retrieved in this session, so I cannot verify whether CryoR2 itself was shown to pump protons (only the group-level abstract statement "CryoRs are... also capable of inward proton translocation" implies it). Recommend a dedicated full-text check of PMID 40614199 for CryoR2-specific electrophysiology before changing exp_class.',
    r40['pmid'], r40['doi'], r40['title'], r40['year'],
    'Our data suggest that CryoRs are sensors for UV irradiation and are also capable of inward proton translocation modulated by UV light.',
    'abstract', 'needs_manual', 'Not one of the brief\'s numbered items; included because it was discovered while verifying CryoR1. Current E1 photoreceptor_no_transport call may be stale (pre-dates the comprehensive 2025 paper) but CryoR2-specific transport data not located in this session.')

# A6: wild type / engineered flags ------------------------------------------------------
add('A', 'A0ABF7PQA2', mrdb('A0ABF7PQA2'), 'HcKCR1 (Kalium Channelrhodopsin 1 C110A)', 'engineered_flag',
    'unflagged', 'engineered: confirmed single-point C110A mutant (laboratory construct used for cryo-EM), not the unmutated wild-type isolate',
    'Direct sequence alignment (this session) of A0ABF7PQA2 vs wild-type HcKCR1 (NCBI UOK93384.1 / UniProt A0ABF7PQ82) shows exactly one substitution, Cys->Ala at residue 110. PDB 9CDC/9CDD/9CDE entities are explicitly annotated pdbx_mutation="C110A". Source paper PMID 39900567 abstract: "the slow-cycling mutant C110A of kalium channelrhodopsin 1 from Hyphochytrium catenoides (HcKCR1)".',
    '39900567', '10.1038/s41467-025-56491-9', 'Structural insights into light-gating of potassium-selective channelrhodopsin.', '2025',
    'Here, we use single-particle cryo-electron microscopy of peptidisc-incorporated protein samples to determine the structures of the slow-cycling mutant C110A of kalium channelrhodopsin 1 from Hyphochytrium catenoides (HcKCR1) in the dark and upon laser flash excitation.',
    'abstract', '', 'Function call (K+-selective channel, E1) is independently correct per auditC_landmark_function_check.tsv (verdict: function correct; membership only candidate); only the construct-vs-wild-type status is being flagged here.')

add('A', 'A0ABF7PQA2', mrdb('A0ABF7PQA2'), 'HcKCR1 (Kalium Channelrhodopsin 1 C110A)', 'wild_type_acc',
    'A0ABF7PQA2 (C110A mutant; sole E1-bearing accession for HcKCR1 function)',
    'A0ABF7PQ82 (exoKCR1; exact wild-type sequence; already proposed for E1 promotion in this table, see exoKCR1 row)',
    'UniProt search of all entries for organism "Hyphochytrium catenoides" (this session) returns exactly 3 accessions: A0ABF7PQ82 (exoKCR1, wild-type sequence, currently E5), A0ABF7PQ84 (C110T mutant), A0ABF7PQA2 (C110A mutant, currently E1). No distinct UniProt record exists yet for the literal GenBank wild-type submission (NCBI protein UOK93384.1, nucleotide MZ826861, deposited as organism "synthetic construct" because it is a codon-optimized expression construct, so UniProt\'s automatic pipeline did not create a TrEMBL entry from it). A0ABF7PQ82 is sequence-identical to UOK93384.1 over its modeled region and is therefore the best available wild-type UniProt accession already present in MicroRhodoDB.',
    '39900567', '10.1038/s41467-025-56491-9', 'Structural insights into light-gating of potassium-selective channelrhodopsin.', '2025',
    'the slow-cycling mutant C110A of kalium channelrhodopsin 1 from Hyphochytrium catenoides (HcKCR1)',
    'abstract', '', 'Recommend E1 be carried by BOTH accessions (mutant retains the function; wild-type exoKCR1 should also be E1, already proposed), rather than moving E1 off the mutant entirely, since the mutant\'s own function call is independently verified correct.')

add('A', 'A0A3G1I4H9', mrdb('A0A3G1I4H9'), 'GtCCR4 (Cation channel rhodopsin 4)', 'wild_type_acc',
    'A0A3G1I4H9 (natural fragment sequence, E1 cation_channel)', 'no_change (A0A3G1I4H9 already IS the wild-type/natural sequence)',
    'A0A3G1I4H9 is sourced from GenBank mRNA MF039475 (ECO:0000313|EMBL), i.e. a natural cloned transcript, not a PDB-only engineered-construct record; it is marked "Fragment" in UniProt because the modeled/submitted sequence does not cover the full transcript, not because of mutagenesis. A UniProt search for other Guillardia theta "CCR4"-named entries (this session) returned only L1JW97 and L1ILV6, which are unrelated CCR4-NOT transcription-complex proteins (different gene family, false lexical match), confirming no better/longer wild-type accession exists in UniProt.',
    '39232582', '10.1016/j.molcel.2024.08.016', 'The high-light-sensitivity mechanism and optogenetic properties of the bacteriorhodopsin-like channelrhodopsin GtCCR4.', '2024',
    'Our structural analyses of GtCCR2 and GtCCR4 revealed that GtCCR4 has an outwardly bent transmembrane helix, resembling the conformation of activated G-protein-coupled receptors.',
    'abstract', '', 'No engineered-mutant concern for GtCCR4, unlike HcKCR1; E1 status on A0A3G1I4H9 is already correctly placed on a natural sequence.')

print(f'Task A done: {len(rows)} rows')

# ============================= TASK B: 101-landmark sweep =============================
# Method: for each of the 101 PE1/reviewed landmarks, compare current DB evidence_level/
# func_class against UniProt's own structured FUNCTION comment + evidence code.
#   - 15 landmarks were already individually hand/script-checked in a prior audit pass
#     (auditC_landmark_function_check.tsv); 7 of those (the 3 "incorrect" + 4 "missed
#     (unresolved)") are the exact same records already fully resolved in Task A above,
#     so they are NOT duplicated here -- only cross-referenced. The 2 "function correct;
#     membership only candidate" rows concern clade/membership placement, not literature
#     evidence, and are logged as out-of-scope informational rows. The 6 "correct" rows
#     (func_class already right per a human-identified PMID, but evidence_level not yet
#     promoted to E1) get a clean E1-promotion proposal citing that PMID.
#   - The remaining 86 landmarks are swept programmatically: UniProt FUNCTION comments
#     tagged ECO:0000269 (direct experimental evidence on this protein) are extracted;
#     the comment text is keyword-classified into the DB's func_class vocabulary and
#     compared to the current DB call. ECO:0000305 ("by similarity"/inferred) is NOT
#     treated as sufficient for E1, consistent with this DB's own evidence-level policy.
#     Matches on a not-yet-E1 record are proposed for E1 promotion (citing the UniProt-
#     linked PMID, evidence_basis style "UniProt curated (ECO:0000269)" -- an evidentiary
#     standard already used elsewhere in this corpus, see e1_without_publication_link.tsv).
#     Mismatches are flagged needs_manual (no automatic func_class correction without a
#     human literature read, to avoid scaling an imperfect keyword classifier into silent
#     data changes). No ECO:0000269 tag at all -> no_change (nothing actionable).

TASKA_COVERED = {'A0A5B2VFD4', 'A0A411LJN5', 'Q9UW81', 'A0ABF7PQ82', 'A0ABF7PQ84', 'L1K1K8', 'A0A1I3DJQ0'}
MEMBERSHIP_ONLY = {'A0ABF7PQA2', 'A0A3G1I4H9'}

def classify_function_text(text):
    t = (text or '').lower()
    # negation guard: "has no proton-pumping activity", "does not appear to pump protons",
    # "not a proton pump", "lacks ... pump" -- a crude keyword scan would otherwise
    # misclassify these as proton_pump despite the sentence asserting the opposite.
    negated_pump = bool(re.search(r'\b(no|not|lacks?|without|non-?functional)\b[^.]{0,40}\bproton[- ]pump', t)) or \
                   bool(re.search(r'\bdoes not (appear to )?pump protons?\b', t))
    if 'sodium' in t and 'pump' in t:
        return 'sodium_pump'
    if ('proton' in t or 'h+' in t) and 'pump' in t and not negated_pump:
        return 'proton_pump_inward' if 'inward' in t else 'proton_pump'
    if ('chloride' in t or 'anion' in t or 'cl-' in t or 'cl\u2212' in t) and 'pump' in t:
        return 'anion_pump'
    if 'channel' in t:
        return 'light_gated_channel'
    if any(k in t for k in ('phototax', 'transducer', 'sensory', 'photophobic', 'photoattractant', 'photorepellent', 'repellent response')):
        return 'sensory'
    if any(k in t for k in ('kinase', 'phosphatase', 'cyclase', 'enzyme')):
        return 'enzyme_rhodopsin'
    if 'photoreceptor' in t:
        return 'photoreceptor_unassigned'
    return None

ECO269_RE = re.compile(r'ECO:0000269\|PubMed:(\d+)')
sweep_records = []

# --- 15 pre-checked landmarks ---
for acc, row in checked.iterrows():
    v = row['verdict']
    if acc in TASKA_COVERED:
        sweep_records.append(dict(source_acc=acc, bucket='covered_in_task_A', db_evidence_level=row['db_evidence_level'],
            db_func_class=row['db_func_class'], note=f'verdict={v}; see Task A proposal for this accession'))
        continue
    if acc in MEMBERSHIP_ONLY:
        add('B', acc, mrdb(acc), row['landmark'], 'membership_status',
            f"evidence_level={row['db_evidence_level']};func_class={row['db_func_class']};membership_status={row['db_membership_status']}",
            'no_change (function call itself is correct)',
            f"Audit verdict: '{v}'. Function/evidence_level call is already correct; the membership_status ({row['db_membership_status']}) reflects phylogenetic placement confidence, which is a clade-assignment question, not a literature-evidence question.",
            '', '', '', '', '', 'audit_table', 'out_of_scope_for_literature_task',
            'Logged for transparency at sign-off; no literature-evidence action proposed. A placement/clade-robustness review (separate workstream) could reconsider membership_status.')
        sweep_records.append(dict(source_acc=acc, bucket='membership_only_informational', db_evidence_level=row['db_evidence_level'],
            db_func_class=row['db_func_class'], note=f'verdict={v}'))
        continue
    if v == 'correct':
        # func_class already right; evidence_level not yet E1 -> propose promotion only.
        pmid_m = re.search(r'PMID:(\d+)', str(row['source']))
        pmid = pmid_m.group(1) if pmid_m else ''
        r = epmc_pmid(pmid) if pmid else None
        snip = ''
        snip_src = 'audit_summary'
        if r and r.get('abstract'):
            # try to find a sentence in the real abstract overlapping the audit's function keywords
            for s in sentences(r['abstract']):
                sl = s.lower()
                if any(k in sl for k in str(row['experimental_function']).lower().split()[:3]):
                    snip, snip_src = s, 'abstract'
                    break
        if not snip:
            snip = row['experimental_function']
        add('B', acc, mrdb(acc), row['landmark'], 'evidence_level',
            f"evidence_level={row['db_evidence_level']};func_class={row['db_func_class']}",
            f"evidence_level=E1;func_class={row['db_func_class']} (unchanged)",
            f"Prior audit pass (auditC) confirmed func_class={row['db_func_class']} is already correct per {row['source']}; this protein-specific experimental citation was not yet linked into the assertion_publication table, so evidence_level remained below E1. Promoting to E1 using the already-identified PMID.",
            (r['pmid'] if r else pmid), (r['doi'] if r else ''), (r['title'] if r else ''), (r['year'] if r else ''),
            snip, snip_src, '', f"Audit source string: {row['source']}.")
        sweep_records.append(dict(source_acc=acc, bucket='promoted_from_audit_correct', db_evidence_level=row['db_evidence_level'],
            db_func_class=row['db_func_class'], note=f'promoted to E1, PMID {pmid}'))

# Special case, individually verified this session (not left to the generic keyword
# classifier): carO (Q70LL3 / S0ELR6, Fusarium/Gibberella fujikuroi). DB currently claims
# evidence_level=E1, basis="experimental:this_protein", func_class/exp_class=proton_pump
# (outward), citing PMID 15133714. Direct reading of that paper's abstract (this session,
# cache/raw/ -- fetched via epmc_pmid) shows it is a gene-expression/genetics study only:
# carO transcription is light-induced, but "targeted mutagenesis of carO produced no
# apparent phenotypic modification, including no change in the photoinduction of
# carotenoid biosynthesis" -- i.e. a NULL knockout phenotype, and UniProt's own FUNCTION
# comment independently states "the exact role of carO ... is not known yet" (Probable
# only). No ion-transport or sensory-transduction assay was performed on carO itself. The
# existing E1/"experimental:this_protein" call is therefore NOT supported by its own cited
# source. The helixC_motif=DTD IS a robust motif (1155/1155 DTD-motif records in this
# corpus are independently called motif_class=proton_pump), so func_class=proton_pump
# remains motif-supported; only the evidence tier and basis are wrong.
CARO_PMID = epmc_pmid('15133714')
CARO_NULL_SNIPPET = ('Targeted mutagenesis of carO produced no apparent phenotypic modification, '
    'including no change in the photoinduction of carotenoid biosynthesis.')
assert verify(CARO_NULL_SNIPPET, CARO_PMID['abstract'])
for caro_acc, caro_label in (('Q70LL3', 'Opsin-like protein carO'), ('S0ELR6', 'Opsin-like protein carO')):
    add('B', caro_acc, mrdb(caro_acc), caro_label, 'evidence_level+basis+exp_class',
        'evidence_level=E1;basis=experimental:this_protein;func_class=proton_pump;exp_class=proton_pump_outward',
        'evidence_level=E4;basis=motif_only;func_class=proton_pump (unchanged, motif-supported);exp_class=None (clear)',
        'The only ECO:0000269-tagged UniProt evidence and its cited primary paper (PMID 15133714) describe a carotenoid-gene-cluster expression study, not a transport or sensory assay on carO itself; the paper reports a NULL knockout phenotype and UniProt\'s own comment states the role is "not known yet" (Probable). The current E1/experimental call over-states the evidence. helixC_motif=DTD is a robust motif (1155/1155 DTD records in this corpus independently called motif_class=proton_pump), so func_class=proton_pump stays motif-supported at E4; exp_class (direction) should be cleared since no transport assay exists.',
        CARO_PMID['pmid'], CARO_PMID['doi'], CARO_PMID['title'], CARO_PMID['year'],
        CARO_NULL_SNIPPET, 'abstract (verified verbatim)', '',
        'Individually verified (not the generic Task B keyword classifier): UniProt FUNCTION text and the primary paper abstract were both read in full this session. Downgrade proposal, not a flag-only item.')
sweep_records.append(dict(source_acc='Q70LL3', bucket='downgraded_false_E1_verified', db_evidence_level='E1', db_func_class='proton_pump', note='E1->E4; experimental basis unsupported by own cited paper (null phenotype)'))
sweep_records.append(dict(source_acc='S0ELR6', bucket='downgraded_false_E1_verified', db_evidence_level='E1', db_func_class='proton_pump', note='E1->E4; experimental basis unsupported by own cited paper (null phenotype); also one of the 41 Task D records'))

# --- remaining 86 landmarks: programmatic ECO:0000269 sweep ---
n_already_e1 = n_promote = n_mismatch = n_no_evidence = n_not_in_cache = 0
checked_accs = set(checked.index)
CARO_HANDLED = {'Q70LL3', 'S0ELR6'}
for _, lrow in landmarks.iterrows():
    acc = lrow['Entry']
    if acc in checked_accs or acc in CARO_HANDLED:
        continue
    db_ev, db_fc = lrow['evidence_level'], lrow['func_class']
    entry_func = uni.get(acc, {}).get('function', [])
    if entry_func is None:
        n_not_in_cache += 1
        continue
    best_pmid, best_text, pred_fc = None, None, None
    for text, ev_str in entry_func:
        m = ECO269_RE.search(ev_str or '')
        if m:
            fc = classify_function_text(text)
            if fc:
                best_pmid, best_text, pred_fc = m.group(1), text, fc
                break
            elif best_pmid is None:
                best_pmid, best_text, pred_fc = m.group(1), text, None
    if best_pmid is None:
        n_no_evidence += 1
        sweep_records.append(dict(source_acc=acc, bucket='no_eco269_evidence', db_evidence_level=db_ev, db_func_class=db_fc,
            note='UniProt FUNCTION comment absent or ECO:0000305/inferred only; no this-protein experimental tag found'))
        continue
    r = epmc_pmid(best_pmid)
    if pred_fc == db_fc:
        if db_ev == 'E1':
            n_already_e1 += 1
            sweep_records.append(dict(source_acc=acc, bucket='confirmed_already_E1', db_evidence_level=db_ev, db_func_class=db_fc,
                note=f'UniProt ECO:0000269 PMID {best_pmid} supports existing E1/{db_fc} call'))
        else:
            n_promote += 1
            add('B', acc, mrdb(acc), lrow['Protein names'], 'evidence_level',
                f'evidence_level={db_ev};func_class={db_fc}', f'evidence_level=E1;func_class={db_fc} (unchanged)',
                f'UniProt FUNCTION comment is tagged ECO:0000269 (direct experimental evidence on this protein, PubMed:{best_pmid}) and keyword-classifies to func_class={db_fc}, matching the DB\'s existing (computationally-derived) call. Not yet linked as E1 in MicroRhodoDB. Evidence basis follows the existing in-corpus convention "UniProt curated (ECO:0000269)".',
                (r['pmid'] if r else best_pmid), (r['doi'] if r else ''), (r['title'] if r else ''), (r['year'] if r else ''),
                best_text, 'uniprot_function_cc', '', 'Automated sweep (Task B); UniProt curator already verified ECO:0000269 against the primary paper, not independently re-read in full text this session.')
            sweep_records.append(dict(source_acc=acc, bucket='promoted_same_class', db_evidence_level=db_ev, db_func_class=db_fc,
                note=f'promoted to E1, PMID {best_pmid}'))
    else:
        n_mismatch += 1
        add('B', acc, mrdb(acc), lrow['Protein names'], 'func_class',
            f'evidence_level={db_ev};func_class={db_fc}', f'needs_manual (UniProt ECO:0000269 PMID {best_pmid} suggests func_class={pred_fc or "unclear"})',
            f'UniProt FUNCTION comment tagged ECO:0000269 (PubMed:{best_pmid}) keyword-classifies to "{pred_fc}", which does not match the DB\'s current func_class="{db_fc}". Flagging for manual review rather than auto-correcting, since the keyword classifier is not a substitute for reading the primary paper.',
            (r['pmid'] if r else best_pmid), (r['doi'] if r else ''), (r['title'] if r else ''), (r['year'] if r else ''),
            best_text, 'uniprot_function_cc', 'needs_manual', 'Automated sweep (Task B); direction of correction not asserted.')
        sweep_records.append(dict(source_acc=acc, bucket='mismatch_needs_manual', db_evidence_level=db_ev, db_func_class=db_fc,
            note=f'DB={db_fc} vs UniProt-ECO269-implied={pred_fc}, PMID {best_pmid}'))

pd.DataFrame(sweep_records).to_csv('/mnt/shared-workspace/v160/curation_agent/task_b_landmark_sweep_full.tsv', sep='\t', index=False)
print(f'Task B done: covered_in_A=7, membership_only=2, promoted_from_audit_correct=6, '
      f'already_E1={n_already_e1}, promoted_same_class={n_promote}, mismatch_needs_manual={n_mismatch}, '
      f'no_eco269_evidence={n_no_evidence}, not_in_cache={n_not_in_cache}. Total rows so far: {len(rows)}')

# ============================= TASK C: 21 external positives =============================
# Scope: only external accessions with >=95% identity to an existing corpus member are the
# "same protein" and thus eligible for a corpus-record correction/confirmation here. The
# other 19 (<95%, mostly 30-70% identity) are distinct, non-redundant proteins -- those are
# inputs to the novel-family candidate layer (step 4), not Task C corpus corrections.
HIGH_ID = ext[ext['max_identity_to_corpus'] >= 95.0]
print('Task C: external positives at >=95% identity to an existing corpus member:')
print(HIGH_ID[['ext_acc', 'protein_label', 'nearest_corpus_acc', 'max_identity_to_corpus']].to_string())

tcc = pd.read_csv('cache/task_c_corpus_current.tsv', sep='\t').set_index('source_acc')

for _, erow in HIGH_ID.iterrows():
    acc = erow['nearest_corpus_acc']
    cur = tcc.loc[acc] if acc in tcc.index else None
    if erow['ext_acc'] == 'UOK93384.1':
        # Task A independently re-verified (fresh sequence alignment, this session) that
        # UOK93384.1 is an EXACT (0-mismatch) match to A0ABF7PQ82 (exoKCR1), not to
        # A0ABF7PQA2 as this external_positives_new.tsv row's precomputed nearest_corpus_acc
        # states. A0ABF7PQA2 is itself a confirmed C110A point mutant of A0ABF7PQ82 (also
        # established in Task A / engineered-construct detection), so the two accessions
        # are >99% identical to each other, which explains the near-miss. No action needed
        # beyond what Task A already proposes (exoKCR1 E1 promotion, P-series rows above);
        # flagged here only as a data-quality note about the source file's identity-match
        # target, not a MicroRhodoDB corpus error.
        add('C', acc, mrdb(acc), erow['protein_label'], 'no_change',
            f"evidence_level={cur['evidence_level']};func_class={cur['func_class']};exp_class={cur['exp_class']}" if cur is not None else 'n/a',
            'no_change (A0ABF7PQA2 function call already correct; see data-quality note)',
            f"external_positives_new.tsv lists nearest_corpus_acc={acc} (99.6% identity) for UOK93384.1, but this session's direct sequence re-verification (Task A) found UOK93384.1 is an EXACT (0-mismatch) match to A0ABF7PQ82 (exoKCR1), and that A0ABF7PQA2 is itself a C110A point mutant of A0ABF7PQ82. A0ABF7PQA2's own current DB call (E1/light_gated_channel/potassium_channel) is already correct and needs no change from this comparison.",
            '35726059', '10.1038/s41593-022-01094-6', 'Kalium channelrhodopsins are natural optogenetic tools for synaptic inhibition', '2022',
            '', 'n/a', '', 'Data-quality observation: external_positives_new.tsv nearest_corpus_acc for UOK93384.1 would be more precisely A0ABF7PQ82, not A0ABF7PQA2 (both >99% identical to UOK93384.1; A0ABF7PQ82 is the exact/0-mismatch match). Not a MicroRhodoDB record error; no action beyond Task A\'s exoKCR1 promotion.')
    else:
        label = erow['protein_label']
        if cur is not None:
            add('C', acc, mrdb(acc), label, 'no_change',
                f"evidence_level={cur['evidence_level']};func_class={cur['func_class']};exp_class={cur['exp_class']}",
                'no_change (confirmed consistent)',
                f"External positive {erow['ext_acc']} ({label}) is {erow['max_identity_to_corpus']}% identical / {erow['query_cov']}% coverage to corpus accession {acc}, i.e. effectively the same protein. Corpus record is already evidence_level={cur['evidence_level']}, func_class={cur['func_class']}, consistent with the external record's own annotated function ({label}). No correction needed.",
                '', '', '', '', '', 'n/a', '', 'Confirmatory check only; no new literature claim made (based on existing corpus call + external file\'s own distance/identity statistics).')
        else:
            add('C', acc, mrdb(acc), label, 'needs_manual',
                'not found in cache/task_c_corpus_current.tsv', 'needs_manual (verify current DB state directly)',
                f"External positive {erow['ext_acc']} ({label}) is {erow['max_identity_to_corpus']}% identical to corpus accession {acc}, but this accession was not present in the cached current-state snapshot used by this script.",
                '', '', '', '', '', 'n/a', 'needs_manual', '')

add('C', '', '', 'remaining 19 external positives (<95% identity)', 'no_change',
    'n/a', 'no_change (out of scope for corpus-record correction)',
    f'The other 19 of 21 external positives (identity range ~30-70% to nearest corpus accession, see external_positives_new.tsv distance_class column) are distinct, non-redundant proteins, not near-duplicates of an existing MicroRhodoDB record. They are not actionable under Task C (which only corrects/confirms existing corpus records for near-identical matches); they are instead inputs to the novel-family candidate layer (bestrhodopsin, schizorhodopsin, xenorhodopsin, viral_rhodopsin, MerMAID seed families; see step 4 of the v1.6.0 work plan). One of them (7W9W_A, ChRmine, 33.1% identity) has a 2022 Cell structural paper (PMID 35114111) available in cache if useful context for that workstream, but it is not a corpus correction.',
    '', '', '', '', '', 'n/a', '', 'Scoping note for sign-off reviewers: explains why only 2 of 21 Task C rows are present above.')

print(f'Task C done. Total rows so far: {len(rows)}')

# ============================= TASK D: 41 linkless E1 records =============================
# Method: split each record's semicolon-joined pmid string, drop UniProt ECO-evidence-code
# artifacts (4-zero-prefixed tokens, e.g. "0000269"/"0000305" -- not real PMIDs), dedupe
# preserving order, and exclude the two known compilation/review papers (PMID 30349080,
# Inoue 2018 Sci Rep; PMID 33741996, Karasuyama/Kojima 2021 Commun Biol) from the PRIMARY
# slot (they are reused across dozens of unrelated records and are not protein-specific
# primary evidence) unless nothing else is available. The first remaining non-compilation
# PMID is taken as primary; doi/title/year/abstract are fetched live via Europe PMC
# (cached). If the record's own pre-existing `snippet` column text verifies verbatim in the
# fetched abstract, it is reused (already well-chosen); otherwise a best-effort sentence
# match on the record's exp_function_class/ion/direction keywords is attempted, falling
# back to the abstract's first sentence (flagged as unverified-relevance, not fabricated --
# it is still a real, verbatim sentence from the real abstract).
COMPILATION_PMIDS = {'30349080', '33741996'}
ECO_ARTIFACT_RE = re.compile(r'^0000\d{3}$')

def split_pmids(raw):
    out = []
    for tok in str(raw).split(';'):
        tok = tok.strip()
        if not tok or not tok.isdigit():
            continue
        if ECO_ARTIFACT_RE.match(tok):
            continue
        if tok not in out:
            out.append(tok)
    return out

n_primary = n_manual = 0
for _, row in linkless.iterrows():
    acc = row['source_acc']
    if acc == 'S0ELR6':
        # Cross-reference, not a normal fill-in: Task B (above) independently verified
        # that this record's only non-compilation PMID (15133714) does NOT support its
        # current E1/experimental status (null knockout phenotype in the cited paper) --
        # see the carO downgrade proposal. Filling in the doi/pmid here without that
        # context would misleadingly look like a confirmation of E1.
        add('D', acc, mrdb(acc), row['protein_label'], 'doi+pmid',
            f"doi={row['doi']};pmid={row['pmid']}", 'see Task B carO downgrade proposal (same PMID, does not support E1)',
            'PMID 15133714 is the only non-compilation PMID for this record, but Task B (this session) found it does not contain experimental evidence for carO\'s function (null knockout phenotype); a downgrade to E4/motif_only is proposed there instead of simply linking this PMID as E1 support.',
            CARO_PMID['pmid'], CARO_PMID['doi'], CARO_PMID['title'], CARO_PMID['year'],
            CARO_NULL_SNIPPET, 'abstract (verified verbatim)', '',
            'Cross-referenced with Task B to avoid a contradictory pair of proposals for the same accession.')
        n_manual += 1
        continue
    all_pmids = split_pmids(row['pmid'])
    non_compilation = [p for p in all_pmids if p not in COMPILATION_PMIDS]
    compilation_present = [p for p in all_pmids if p in COMPILATION_PMIDS]
    old_val = f"doi={row['doi']};pmid={row['pmid']}"
    if not non_compilation:
        n_manual += 1
        note = (f"Only compilation/review PMID(s) available: {','.join(compilation_present) if compilation_present else 'none'}. "
                 "Per policy these are secondary (not protein-specific primary evidence); no primary citation assigned. "
                 "Needs a manual literature search for a protein-specific primary paper.")
        add('D', acc, mrdb(acc), row['protein_label'], 'doi+pmid', old_val, 'needs_manual (no non-compilation PMID found)',
            'No protein-specific (non-compilation) PMID present in the raw citation string.',
            '', '', '', '', '', 'n/a', 'needs_manual', note)
        continue
    primary = non_compilation[0]
    r = epmc_pmid(primary)
    if r is None:
        n_manual += 1
        add('D', acc, mrdb(acc), row['protein_label'], 'doi+pmid', old_val, f'needs_manual (PMID {primary} did not resolve via Europe PMC)',
            f'Candidate non-compilation PMID {primary} found in raw string but did not resolve to a record via Europe PMC search.',
            primary, '', '', '', '', 'n/a', 'needs_manual', '')
        continue
    abstract = r.get('abstract', '') or ''
    existing_snip = str(row.get('snippet', '') or '')
    if existing_snip and verify(existing_snip, abstract):
        snip, snip_src = existing_snip, 'abstract (pre-existing snippet, verified verbatim)'
    else:
        snip, snip_src = '', None
        kws = [str(row.get(c, '')).lower() for c in ('exp_function_class', 'ion', 'direction') if pd.notna(row.get(c, None))]
        kws = [k for k in kws if k and k != 'nan']
        for s in sentences(abstract):
            sl = s.lower()
            if kws and any(k in sl for k in kws):
                snip, snip_src = s, 'abstract (keyword-matched sentence)'
                break
        if not snip:
            ss = sentences(abstract)
            if ss:
                snip, snip_src = ss[0], 'abstract (first sentence, relevance not independently verified)'
    n_primary += 1
    add('D', acc, mrdb(acc), row['protein_label'], 'doi+pmid', old_val,
        f"doi={r['doi']};pmid={r['pmid']}",
        f"Primary non-compilation citation selected from the raw doi/pmid string. {len(compilation_present)} compilation PMID(s) also present in the raw data ({','.join(compilation_present)}) are treated as secondary context, not primary evidence.",
        r['pmid'], r['doi'], r['title'], r['year'], snip, snip_src or 'n/a', '',
        f"{len(all_pmids)} raw PMID token(s) after ECO-artifact filtering; {len(non_compilation)} non-compilation.")

print(f'Task D done: primary_assigned={n_primary}, needs_manual={n_manual} (of {len(linkless)} records). Total rows so far: {len(rows)}')

# ============================= WRITE OUTPUT =============================
out_df = pd.DataFrame(rows)
out_path = '/mnt/shared-workspace/v160/curation_agent/curation_proposals_literature.tsv'
out_df.to_csv(out_path, sep='\t', index=False)
print(f'Wrote {len(out_df)} rows to {out_path}')
print(out_df['task'].value_counts())
print(out_df.groupby('task')['decision'].apply(lambda s: s.value_counts().to_dict()))
