#!/usr/bin/env python
"""Build MicroRhodoDB v1.6.0 from the immutable v1.5.0 database plus the signed v1.6.0 curation decisions.

Inputs (all paths in config_v160.json are relative to the repository root)
  releases/v1.5.0/db/microrhododb_v1.5.0.sqlite      opened read-only (?mode=ro) and copied; never modified
  curation/v160/curation_v160_*_signed.tsv           curator sign-off (CongJian Li, 2026-10-09)
  curation/v160/link_labelling_spec_v160.tsv         compilation-link labelling spec (addendum step 2)
  curation/v160/pmid_metadata_v160.tsv               PubMed E-utilities metadata + abstracts for every new link
  curation/v160/loco_*                               Stage-1 / addendum validation tables
  curation/v160/novel_family_*                       novel-family layer (funnel + 0 final candidates)

Order of operations
  1  citation token fixes (ADD-F compilation PMIDs, ADD-G ECO pseudo-PMIDs)
  2  characterized_protein: taskD fills, promotions, carO demotion, RETIER, addendum A/B/D/E, engineered transfer
  3  E-ladder recompute (E2 re-searched with the v1.6.0 E1 reference set; ladder reproduces v1.5.0 first)
  4  conflict rule: E3/E4 (non curated_rule) conflicts -> E5 'unassigned'; E1/E2/curated_rule flagged only
  5  basis renaming, engineered flags, exact-duplicate flags, E1 representatives
  6  publications + assertion links (support / compilation / context)
  7  new tables (curation decisions, LOCO validation, novel layer), motif benchmark + spectral audit refresh
  8  drop membership.alias_v14 + compatibility views; recreate v_master
  9  sequence_source.source_release backfill; release_metadata + build_provenance; VACUUM
Usage: python pipeline/v160/build_v160.py pipeline/v160/config_v160.json [--out-db PATH] [--work-dir PATH]
                                                                     [--log PATH] [--mmseqs BIN]
  Overrides are relative to the current directory; without them the config values (relative to the repo root) apply.
  The Snakemake workflow uses the overrides to rebuild into work/ without touching the shipped release.
"""
import json, os, re, sys, sqlite3, datetime
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mrdb_v160_lib import (EXP2V14, EXP2ASSERTION, EXP2KEYWORDS, conflict, conflict_exact, motif_testable,
                           e2_search, e2_assign, ladder_row, loco_evaluate, agree_v14, wilson, is_unassigned)
from r2_clade_function import recompute as recompute_clade_function
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


def toks(s):
    if not isinstance(s, str):
        return []
    return [t.strip() for t in s.split(";") if t.strip()]


def jn(lst):
    out = []
    for x in lst:
        if x and x not in out:
            out.append(x)
    return ";".join(out) if out else None


def put(con, df, name, pk=None):
    df.to_sql(name, con, index=False, if_exists="replace")
    if pk:
        con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{name}_{"_".join(pk)} ON "{name}" ({", ".join(pk)})')


def add_cols(con, table, cols):
    have = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
    for c, t in cols:
        if c not in have:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" {t}')


def main():
    root = os.path.abspath(os.path.join(HERE, "..", ".."))
    import argparse
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("config")
    ap_.add_argument("--out-db"); ap_.add_argument("--work-dir"); ap_.add_argument("--log"); ap_.add_argument("--mmseqs")
    A = ap_.parse_args()
    C = json.load(open(A.config))
    for k, v in (("out_db", A.out_db), ("work_dir", A.work_dir), ("log_file", A.log), ("mmseqs", A.mmseqs)):
        if v:
            C[k] = os.path.abspath(v) if k != "mmseqs" else v
    P = lambda k: os.path.join(root, C[k])
    out = P("out_db")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    src = sqlite3.connect(f"file:{P('base_db')}?mode=ro", uri=True)
    con = sqlite3.connect(out)
    src.backup(con)
    src.close()
    con.execute("PRAGMA foreign_keys=OFF")
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    DEC_DATE = C["decision_date"]
    CURATOR = C["curator"]
    prov = []
    cur = os.path.join(root, C["curation_dir"])
    rec = pd.read_csv(f"{cur}/curation_v160_records_signed.tsv", sep="\t", dtype=str)
    grp = pd.read_csv(f"{cur}/curation_v160_groups_signed.tsv", sep="\t", dtype=str)
    pol = pd.read_csv(f"{cur}/curation_v160_policy_clarifications_signed.tsv", sep="\t", dtype=str)
    add = pd.read_csv(f"{cur}/curation_v160_addendum_citations_signed.tsv", sep="\t", dtype=str)
    spec = pd.read_csv(f"{cur}/link_labelling_spec_v160.tsv", sep="\t", dtype=str)
    meta = pd.read_csv(f"{cur}/pmid_metadata_v160.tsv", sep="\t", dtype=str).fillna("")
    meta = meta.set_index("pmid")
    # second sign-off round (referee follow-up, R2): membership override, clade_function recompute, E1 evidence,
    # audit corrections, Foldseek watchlist. Only rows with user_decision == APPROVE are applied.
    r2 = pd.read_csv(f"{cur}/curation_v160_r2_signed.tsv", sep="\t", dtype=str).fillna("")
    r2sel = lambda action: r2[(r2.action == action) & (r2.user_decision == "APPROVE")]
    OK = {"APPROVE", "B", "RETIER (remove E1)", "DEFER_FLAG"}
    assert set(grp.user_decision) <= OK | {"ACKNOWLEDGED (no action)", "SUPERSEDED_BY_ADDENDUM", "DEFER"}
    sel = lambda g: rec[(rec.group_id == g) & rec.user_decision.isin(OK)]
    asel = lambda g: add[add.group_id.str.startswith(g) & add.user_decision.isin(OK)]

    cp0 = pd.read_sql("select * from characterized_protein", con)
    fe0 = pd.read_sql("select * from function_evidence", con)
    mem = pd.read_sql("select source_acc, membership_status, retinal_site_residue from membership", con)
    prot = pd.read_sql("select source_acc, sequence, organism, protein_name, mrdb_acc from protein", con)
    rc = pd.read_sql("select source_acc, clade_id as rc_clade, subclade_id, clade_function_source from record_clade", con)
    log(f"v1.5.0 base: {len(fe0)} records; levels {fe0.evidence_level.value_counts().sort_index().to_dict()}")

    # ------------------------------------------------------------------ 1. citation token fixes
    FIX = {"30349080": "30349075", "33741996": "33742139"}
    ECO = re.compile(r"^0000\d{3}$")   # UniProt ECO evidence codes mis-parsed as PMIDs (ECO:0000269, ECO:0000305)
    COMP = {"30349075", "33742139"}

    def fix_pmids(s):
        t = toks(s)
        return jn([FIX.get(x, x) for x in t if not ECO.match(x)])

    for tname in ("characterized_protein", "spectral_audit"):
        df = pd.read_sql(f"select * from {tname}", con)
        nf = df.pmid.fillna("").str.contains("30349080|33741996").sum()
        ng = df.pmid.fillna("").apply(lambda s: any(ECO.match(x) for x in toks(s))).sum()
        ng269 = df.pmid.fillna("").apply(lambda s: "0000269" in toks(s)).sum()
        df["pmid"] = df.pmid.apply(fix_pmids)
        df["lambda_max_source_pmid"] = [jn([x for x in toks(p) if x in COMP]) if pd.notna(l) else None
                                        for p, l in zip(df.pmid, df.lambda_max_nm)]
        log(f"[1] {tname}: compilation-PMID rows fixed {nf}; ECO-token rows cleaned {ng} (of which ECO:0000269 {ng269})")
        if tname == "characterized_protein":
            cp = df
        else:
            sa = df
    prov.append(("characterized_protein", "curation_v160_addendum_citations_signed.tsv (ADD-F, ADD-G)", "build_v160.py",
                 "token replace", "30349080->30349075; 33741996->33742139; drop ^0000ddd$ ECO tokens", "[]"))

    # ------------------------------------------------------------------ 2. characterized_protein curation
    cp["v160_curation_note"] = None
    cp = cp.set_index("source_acc", drop=False)

    def note(acc, s):
        cp.loc[acc, "v160_curation_note"] = jn(toks(cp.loc[acc, "v160_curation_note"]) + [s])

    def doi_of(pm):
        return meta.loc[pm, "doi"] if pm in meta.index and meta.loc[pm, "doi"] else None

    # 2a taskD primary citation fills (approved new_value replaces doi/pmid; compilation PMIDs kept in lambda_max_source_pmid)
    td = sel("literature_taskD_doi_pmid_filled")
    td = td[td.new_value.str.startswith("doi=")]
    for r in td.itertuples():
        d, p = re.match(r"doi=([^;]+);pmid=(\d+)", r.new_value).groups()
        old = f"doi={cp.loc[r.source_acc, 'doi']}; pmid={cp.loc[r.source_acc, 'pmid']}"
        cp.loc[r.source_acc, ["doi", "pmid"]] = [d.lower(), p]
        note(r.source_acc, f"taskD: primary citation filled (previous {old})")
    log(f"[2a] taskD doi/pmid fills applied: {len(td)}")

    # 2b promotions to E1 (taskA + taskB); update existing rows, insert missing ones
    promo = pd.concat([sel("literature_taskA_promote_E1"), sel("literature_taskB_promote_E1")])
    PROMO_EXP = {}
    TASKB_EXP = {"proton_pump": "proton_pump_outward"}
    for r in promo.itertuples():
        m = re.search(r"exp_class=([a-z_]+)", r.new_value)
        if m:
            e = m.group(1)
        else:
            fc = re.search(r"func_class=([a-z_]+)", r.new_value).group(1)
            e = TASKB_EXP.get(fc)
            if e is None:   # light_gated_channel: resolve the channel subtype from the cited abstract
                pm = re.search(r"PMID:(\d+)", r.evidence_ref).group(1)
                txt = (meta.loc[pm, "title"] + " " + meta.loc[pm, "abstract"]).lower()
                e = "anion_channel" if "anion channel" in txt else "cation_channel"
        assert e in EXP2V14, (r.source_acc, e)
        PROMO_EXP[r.source_acc] = (e, re.search(r"PMID:(\d+)", r.evidence_ref).group(1),
                                   re.search(r"DOI:(\S+)", r.evidence_ref).group(1).rstrip('"').lower(), r.group_id)
    ENG = {}
    for r in sel("engineered_construct").itertuples():
        ENG[r.source_acc] = re.search(r"wild_type_acc=(\S+)", r.new_value).group(1)
    # engineered-construct policy ("move/extend E1 to the wild-type entry"): a wild type without its own E1 inherits
    # the construct's E1 when the construct is E1 (A0A8X6EH36 -> A0AAJ0LKB3); Option B keeps E1 on the HcKCR1 mutants.
    for e_acc, wt in ENG.items():
        if e_acc in cp.index and cp.loc[e_acc, "exp_class"] in EXP2V14 and int(cp.loc[e_acc, "e1_eligible"]) == 1 \
                and wt not in cp.index and wt not in PROMO_EXP:
            pm = toks(cp.loc[e_acc, "pmid"])[0]
            PROMO_EXP[wt] = (cp.loc[e_acc, "exp_class"], pm, doi_of(pm) or toks(cp.loc[e_acc, "doi"])[0],
                             f"engineered_construct_transfer:{e_acc}")
    pinfo = prot.set_index("source_acc"); minfo = mem.set_index("source_acc")
    n_upd = n_ins = 0
    for acc, (e, pm, doi, g) in PROMO_EXP.items():
        txt_note = f"{g}: E1 {e} (PMID {pm})"
        if acc in cp.index:
            cp.loc[acc, "pmid"] = jn([pm] + toks(cp.loc[acc, "pmid"]))
            cp.loc[acc, "doi"] = jn([doi] + toks(cp.loc[acc, "doi"]))
            cp.loc[acc, ["exp_class", "exp_class_basis", "e1_eligible", "e1_exclusion_reason"]] = \
                [e, f"curator_v160:{g}", 1, None]
            note(acc, txt_note); n_upd += 1
        else:
            row = {c: None for c in cp.columns}
            src_eng = g.split(":")[1] if g.startswith("engineered_construct_transfer") else None
            row.update(source_acc=acc, organism=pinfo.loc[acc, "organism"], protein_label=pinfo.loc[acc, "protein_name"],
                       exp_function_class=e, assay_type="see cited study", doi=doi, pmid=pm,
                       evidence_basis=("transferred_from_engineered_construct:" + src_eng) if src_eng else "curator_v160_literature",
                       snippet=meta.loc[pm, "title"] if pm in meta.index else None,
                       mapping_identity="engineered construct of this wild type" if src_eng else "100.0%id/100%cov (UniProt accession cited)",
                       in_tierA=0, exp_class=e, exp_class_basis=f"curator_v160:{g}",
                       membership_status_v150=minfo.loc[acc, "membership_status"], ms210=minfo.loc[acc, "retinal_site_residue"],
                       e1_eligible=1, v160_curation_note=txt_note)
            cp.loc[acc] = pd.Series(row); n_ins += 1
    log(f"[2b] E1 promotions: {len(PROMO_EXP)} ({n_upd} existing rows updated, {n_ins} rows inserted); "
        f"incl. engineered transfer {[a for a, v in PROMO_EXP.items() if v[3].startswith('engineered')]}")

    # 2c carO demotion
    for r in sel("literature_taskB_downgrade_carO").itertuples():
        cp.loc[r.source_acc, ["exp_class", "e1_eligible", "e1_exclusion_reason"]] = \
            [None, 0, "not_direct_function_assay (gene-expression/knockout study, null phenotype; PMID 15133714)"]
        note(r.source_acc, "taskB carO: E1 withdrawn; cited study is not a direct transport/function assay")
    # 2d RETIER (no paper beyond the lambda-max compilations)
    RETIER = set(asel("ADD-C").source_acc)
    for a in RETIER:
        cp.loc[a, ["e1_eligible", "e1_exclusion_reason"]] = [0, "lambda_max_only_compilation"]
        note(a, "ADD-C RETIER: E1 removed (lambda-max compilation only; no per-protein functional paper); lambda_max kept")
    log(f"[2c/d] carO demoted: {sel('literature_taskB_downgrade_carO').source_acc.tolist()}; RETIER: {sorted(RETIER)}")

    # 2e addendum A/B: primary PMIDs prepended (compilation PMID kept); DOIs from PubMed metadata
    for r in pd.concat([asel("ADD-A"), asel("ADD-B")]).itertuples():
        pms = toks(r.new_value.split("|")[0].replace(" ", ""))
        prim = [p for p in pms if p not in COMP]
        cp.loc[r.source_acc, "pmid"] = jn(pms)
        cp.loc[r.source_acc, "doi"] = jn([doi_of(p) for p in prim] + toks(cp.loc[r.source_acc, "doi"]))
        note(r.source_acc, f"{r.group_id}: primary PMID(s) {','.join(prim)} added")
    # 2f ADD-D flags, ADD-E CryoR2
    for r in asel("ADD-D").itertuples():
        note(r.source_acc, f"ADD-D needs_manual: E1 retained on compilation-only link; candidate primary {r.evidence_ref}")
    for r in asel("ADD-E").itertuples():
        cp.loc[r.source_acc, "pmid"] = "40614199;41580893"
        cp.loc[r.source_acc, "doi"] = jn(toks(cp.loc[r.source_acc, "doi"]) + [doi_of("41580893")])
        note(r.source_acc, "ADD-E: PMIDs filled; exp_class photoreceptor_no_transport kept; needs_manual closed")
    # 2y R2 E1 evidence caveats (full-text checks of A0A0M5L0M3/Q6R5N7; primary-paper search for A0A0P6XBM7/A0ACE3JIR6)
    R2_E1_REASON = {
        "Q6R5N7": "r2_abstract_only_no_polarity_resolved_transport_assay (PMID 16075162; full text not retrievable)",
        "A0A0P6XBM7": "r2_no_primary_paper_for_this_protein (closest assayed homolog BeNaR, 89.2% identity, PMID 36724978)",
    }
    R2_E1DOWN = set(r2sel("e1_downgrade").source_acc)
    assert R2_E1DOWN <= set(R2_E1_REASON), R2_E1DOWN
    for a in sorted(R2_E1DOWN):
        assert int(float(cp.loc[a, "e1_eligible"])) == 1, a
        cp.loc[a, ["e1_eligible", "e1_exclusion_reason"]] = [0, R2_E1_REASON[a]]
        note(a, f"R2: E1 withdrawn ({R2_E1_REASON[a]})")
    for r in r2sel("e1_keep_with_quote").itertuples():
        note(r.source_acc, f"R2: E1 kept; proton pumping of this paralog (Ps PR) shown in {r.evidence_ref}, verified in full text")
    R2_REPLACE = {}
    for r in r2sel("e1_replace_paper").itertuples():
        pm = re.search(r"PMID:(\d+)", r.evidence_ref).group(1)
        R2_REPLACE[r.source_acc] = pm
        cp.loc[r.source_acc, "pmid"] = jn([pm] + [x for x in toks(cp.loc[r.source_acc, "pmid"]) if x != pm])
        cp.loc[r.source_acc, "doi"] = jn([doi_of(pm)] + [x for x in toks(cp.loc[r.source_acc, "doi"]) if x != doi_of(pm)])
        cp.loc[r.source_acc, "protein_label"] = "PaR (Pantoea ananatis rhodopsin)"
        cp.loc[r.source_acc, ["assay_type", "evidence_basis"]] = ["light-induced pH change in E. coli cell suspension (CCCP-sensitive)",
                                                                 "curator_v160_r2_literature"]
        note(r.source_acc, f"R2: primary paper PMID {pm} added (100% identical to PaR); UniProt name 'Archaerhodopsin-2' is a "
                           f"genome-annotation misnomer (39.5% identity to AR2 P29563)")
    log(f"[2y] R2 E1 caveats: withdrawn {sorted(R2_E1DOWN)}; kept with quote {list(r2sel('e1_keep_with_quote').source_acc)}; "
        f"primary paper replaced {R2_REPLACE}")
    cp = cp.reset_index(drop=True)

    # ------------------------------------------------------------------ 2z. R2 membership override (R-F3)
    # pre-override membership is kept for the v1.5.0 ladder reproduction in step 3
    is_mem15 = dict(zip(mem.source_acc, mem.membership_status.fillna("").str.startswith("typeI_member")))
    MOV = r2sel("membership_override")
    for r in MOV.itertuples():
        st0 = mem.loc[mem.source_acc == r.source_acc, "membership_status"].iloc[0]
        assert st0.startswith("typeI_candidate") and r.source_acc in set(cp[cp.e1_eligible.astype(float) == 1].source_acc), r.source_acc
        reason = f"curated_override: E1 primary evidence ({r.evidence_ref}); scored status {st0}"
        con.execute("UPDATE membership SET membership_status='typeI_member_curated', status_reason=? WHERE source_acc=?",
                    (reason, r.source_acc))
        mem.loc[mem.source_acc == r.source_acc, "membership_status"] = "typeI_member_curated"
    log(f"[2z] R2 membership override -> typeI_member_curated: {len(MOV)} ({', '.join(MOV.source_acc)})")
    sd = pd.read_sql("select * from status_definition", con)
    if len(MOV) and "typeI_member_curated" not in set(sd.status):
        sd.loc[len(sd)] = dict(status="typeI_member_curated", status_group="member", is_member=1, is_candidate=0,
                               alias_v14=None, n_records_v150=0,
                               definition="Experimentally characterised Type-I rhodopsin (E1, primary paper, not engineered) whose "
                                          "membership score is below the member threshold; promoted by signed curator override "
                                          "(v1.6.0 R2). The score is kept in membership_score; the reason is in status_reason.")
        put(con, sd, "status_definition")

    # ------------------------------------------------------------------ 3. E-ladder recompute
    seqs = dict(zip(prot.source_acc, prot.sequence))
    qids = [s for s in mem.source_acc if s in seqs]
    is_mem = dict(zip(mem.source_acc, mem.membership_status.fillna("").str.startswith("typeI_member")))
    clade_of = dict(zip(fe0.source_acc, fe0.clade_id))
    fe = fe0.copy()
    fe["v14"] = np.where(fe.override_rule.notna(), fe.func_class, fe.func_class_v14)

    def e1_set(cpdf):
        x = cpdf[cpdf.exp_class.isin(EXP2V14) & (cpdf.e1_eligible.astype(float) == 1)]
        return dict(zip(x.source_acc, x.exp_class))

    prefer15 = {a: r for a, r in zip(fe0.source_acc, fe0.e2_ref) if isinstance(r, str)}

    def run_ladder(e1map, refs, tag, memmap=None):
        memmap = is_mem if memmap is None else memmap
        hits = e2_search(seqs, qids, refs.keys(), os.path.join(root, C["work_dir"], f"e2_{tag}"),
                         mmseqs=C.get("mmseqs", "mmseqs"), threads=C.get("threads", 8))
        e2 = e2_assign(hits, refs, clade_of, prefer15).set_index("source_acc")
        res = []
        for r in fe.itertuples():
            e2r = e2.loc[r.source_acc] if r.source_acc in e2.index else None
            res.append(ladder_row(e1map.get(r.source_acc),
                                  e2r.e2_classes if e2r is not None else None,
                                  e2r.e2_ref if e2r is not None else None,
                                  e2r.e2_identity if e2r is not None else None,
                                  memmap.get(r.source_acc, False), r.v14, r.clade_id, r.clade_function,
                                  r.override_rule, r.helixC_motif))
        out_ = pd.DataFrame(res, columns=["lvl", "cls", "bas"], index=fe.source_acc)
        out_["e2_ref"] = [e2.loc[a, "e2_ref"] if (a in e2.index and l == "E2") else None for a, l in zip(out_.index, out_.lvl)]
        out_["e2_identity"] = [e2.loc[a, "e2_identity"] if (a in e2.index and l == "E2") else None for a, l in zip(out_.index, out_.lvl)]
        return out_

    e1_v15 = e1_set(cp0)
    assert set(e1_v15) == set(fe0[fe0.evidence_level == "E1"].source_acc), "v1.5 E1 rule does not reproduce v1.5 E1 set"
    v15 = run_ladder(e1_v15, e1_v15, "v150_repro", memmap=is_mem15)
    f0 = fe0.set_index("source_acc")
    same = (v15.lvl == f0.evidence_level) & (v15.cls == f0.func_class) & (v15.bas == f0.basis)
    log(f"[3] v1.5.0 ladder reproduction: {int(same.sum())}/{len(same)} records identical (level, class, basis)")
    assert same.all(), v15[~same].join(f0[["evidence_level", "func_class", "basis"]]).head(20).to_string()

    e1_v16 = e1_set(cp)
    refs_v16 = {a: e for a, e in e1_v16.items() if a not in ENG}
    log(f"[3] v1.6.0 E1 set: {len(e1_v16)} records ({len([a for a in e1_v16 if a in ENG])} engineered); "
        f"E2 reference set (non-engineered): {len(refs_v16)}")
    CF_RECOMPUTE = len(r2sel("recompute_clade_function")) > 0
    if CF_RECOMPUTE:
        rcf = pd.read_sql("select source_acc, clade_id, subclade_id from record_clade", con)
        CF16, RCF = recompute_clade_function(rcf, refs_v16)
        cf_new = dict(zip(RCF.source_acc, RCF.clade_function))
        cfs_new = dict(zip(RCF.source_acc, RCF.clade_function_source))
        cf_old = dict(zip(fe.source_acc, fe.clade_function))
        _s = lambda x: x if isinstance(x, str) else ""
        n_chg = sum(_s(cf_new.get(a)) != _s(cf_old.get(a)) for a in fe.source_acc)
        fe["clade_function"] = fe.source_acc.map(cf_new)
        rc["clade_function_source"] = rc.source_acc.map(cfs_new)
        log(f"[3] clade_function recomputed (v1.5.0 rule, {len(refs_v16)} non-engineered E1): records changed {n_chg}; "
            f"groups with consensus {int(CF16.clade_function.notna().sum())}/{len(CF16)}")
    v16 = run_ladder(e1_v16, refs_v16, "v160")
    # signed carO decision (literature_taskB_downgrade_carO): E4, func_class proton_pump supported by the robust DTD
    # motif, not by the legacy call. Applied as signed (the unmodified ladder would give S0ELR6 E3 and Q70LL3 E5,
    # because Q70LL3's legacy v1.4 call is 'sensory').
    CARO = list(sel("literature_taskB_downgrade_carO").source_acc)
    for a in CARO:
        log(f"[3] carO {a}: unmodified ladder -> {v16.loc[a, 'lvl']}/{v16.loc[a, 'cls']}; signed -> E4/proton_pump")
        v16.loc[a, ["lvl", "cls", "bas", "e2_ref", "e2_identity"]] = ["E4", "proton_pump", "curated_rule:carO_v160_signed:DTD", None, None]
    fe.loc[fe.source_acc.isin(CARO), "override_rule"] = "carO_v160_signed"

    # ------------------------------------------------------------------ 4. conflict rule
    fe = fe.set_index("source_acc")
    fe["func_class_v150"] = fe.func_class; fe["evidence_level_v150"] = fe.evidence_level; fe["basis_v150"] = fe.basis
    fe["evidence_level"] = v16.lvl; fe["func_class"] = v16.cls; fe["basis"] = v16.bas
    fe["e2_ref"] = v16.e2_ref; fe["e2_identity"] = v16.e2_identity
    fe["exp_class"] = pd.Series(e1_v16).reindex(fe.index)
    call = fe.func_class.copy()
    fe["call_conflict"] = [conflict(a, b) for a, b in zip(call, fe.motif_class)]
    fe["call_conflict_exact"] = [conflict_exact(a, b) for a, b in zip(call, fe.motif_class)]
    curated = fe.basis.str.startswith("curated_rule")
    down = fe.evidence_level.isin(["E3", "E4"]) & ~curated & (fe.call_conflict == 1)
    fe["call_conflict_detail"] = None
    fe.loc[fe.call_conflict == 1, "call_conflict_detail"] = [
        f"v14={a}; motif={b}; action=" + ("downgraded_to_E5" if d else f"flag_only_{lv}" + ("_curated_rule" if cr else ""))
        for a, b, d, lv, cr in zip(call[fe.call_conflict == 1], fe.motif_class[fe.call_conflict == 1], down[fe.call_conflict == 1],
                                   fe.evidence_level[fe.call_conflict == 1], curated[fe.call_conflict == 1])]
    fe.loc[down, "basis"] = "conflict: v14=" + call[down] + "; motif=" + fe.motif_class[down].astype(str)
    fe.loc[down, "evidence_level"] = "E5"
    fe.loc[down, "func_class"] = "unassigned"
    signed_down = set(sel("F1_downgrade_E3").source_acc) | set(sel("F1_downgrade_E4").source_acc)
    pol_down = set(fe.index[down])
    log(f"[4] conflict downgrades applied: {len(pol_down)} (signed list {len(signed_down)}; "
        f"in both {len(signed_down & pol_down)}; signed-not-applied {len(signed_down - pol_down)}; "
        f"policy-derived extra {len(pol_down - signed_down)})")
    sna = signed_down - pol_down
    log("    signed-not-applied:", {a: fe.loc[a, "evidence_level"] for a in sorted(sna)})
    assert all(fe.loc[a, "evidence_level"] in ("E1", "E2") for a in sna), "signed downgrade skipped without E1/E2 reason"
    extra = sorted(pol_down - signed_down)
    log("    policy-derived extra downgrades (were v1.5", {a: fe.loc[a, "evidence_level_v150"] + "/" + fe.loc[a, "basis_v150"] for a in extra}, ")")
    flags_signed = set(sel("F1_flag_E2_experimental_ortholog").source_acc) | set(sel("F1_flag_E4_curated_rule").source_acc)
    log(f"    flagged-only conflicts: {int(((fe.call_conflict == 1) & ~down).sum())} "
        f"(by level {fe[(fe.call_conflict == 1) & ~down].evidence_level.value_counts().to_dict()}); "
        f"signed flag rows still flagged {len([a for a in flags_signed if fe.loc[a, 'call_conflict'] == 1])}/{len(flags_signed)}")

    # ------------------------------------------------------------------ 4b. R2 audit rules (R-V2) + schizorhodopsin reassignment
    # Signed corpus-wide rules derived from the blind audit; both move legacy-motif E4 calls to E5 'unresolved'.
    sub_of = dict(zip(rc.source_acc, rc.subclade_id.fillna("")))
    fe["subclade_tmp"] = fe.index.map(sub_of)
    R2CH = {}
    R2_RULES = [
        ("rule_xeno_DTA_DSA", "audit_rule_ASR_vs_XeR_ambiguous",
         (fe.subclade_tmp == "MR_CLD3_009.03") & (fe.evidence_level == "E4") & fe.func_class.isin(["sensory", "sensory_like"])
         & fe.helixC_motif.isin(["DTA", "DSA"]), 69),
        ("rule_opsA_DSE", "audit_rule_OpsA_like_nonpumping_lineage",
         (fe.subclade_tmp == "MR_CLD3_017.06") & (fe.evidence_level == "E4") & (fe.func_class == "proton_pump")
         & (fe.helixC_motif == "DSE"), 47),
    ]
    for action, tag, mask, n_exp in R2_RULES:
        if not len(r2sel(action)):
            continue
        assert int(mask.sum()) == n_exp, (action, int(mask.sum()))
        fe.loc[mask, "basis"] = tag + ":" + fe.loc[mask, "helixC_motif"].astype(str)
        fe.loc[mask, ["evidence_level", "func_class", "override_rule"]] = ["E5", "unresolved", tag]
        for a in fe.index[mask]:
            R2CH[a] = f"R2_{tag}"
        log(f"[4b] {action}: {int(mask.sum())} records E4 -> E5 unresolved ({tag})")
    sz = r2sel("func_reassign")
    for r in sz.itertuples():
        a = r.source_acc
        assert fe.loc[a, "evidence_level"] == "E4" and fe.loc[a, "func_class"] == "light_gated_channel", a
        fe.loc[a, ["evidence_level", "func_class", "override_rule"]] = ["E5", "unresolved", "schizorhodopsin_family_conflict"]
        fe.loc[a, "basis"] = "family_hmm_schizorhodopsin_conflicts_legacy_channel:" + str(fe.loc[a, "helixC_motif"])
        R2CH[a] = "R2_schizorhodopsin_reassigned"
    log(f"[4b] schizorhodopsin reassignment: {list(sz.source_acc)} -> E5 unresolved")
    r2m = fe.index.isin(list(R2CH))
    fe.loc[r2m, "call_conflict"] = [conflict(c, m) for c, m in zip(fe.func_class[r2m], fe.motif_class[r2m])]
    fe.loc[r2m, "call_conflict_exact"] = [conflict_exact(c, m) for c, m in zip(fe.func_class[r2m], fe.motif_class[r2m])]
    fe.loc[r2m & (fe.call_conflict == 0), "call_conflict_detail"] = None
    fe = fe.drop(columns=["subclade_tmp"])

    # ------------------------------------------------------------------ 5. basis rename, engineered, duplicates
    mo = fe.basis.str.startswith("motif_only:")
    testable = fe.motif_class.apply(motif_testable)
    fe.loc[mo & testable, "basis"] = fe.loc[mo & testable, "basis"].str.replace("motif_only:", "legacy_v14_concordant_motif:", regex=False)
    fe.loc[mo & ~testable, "basis"] = fe.loc[mo & ~testable, "basis"].str.replace("motif_only:", "legacy_v14_motif_untestable:", regex=False)
    log(f"[5] basis renamed: legacy_v14_concordant_motif {int((mo & testable).sum())}; legacy_v14_motif_untestable {int((mo & ~testable).sum())}")
    fe["is_engineered"] = [int(a in ENG) for a in fe.index]
    fe["wild_type_acc"] = [ENG.get(a) for a in fe.index]

    chg = {a: [] for a in fe.index}
    for a in fe.index:
        o, n = fe.loc[a, "evidence_level_v150"], fe.loc[a, "evidence_level"]
        if a in PROMO_EXP and o != "E1":
            chg[a].append("promoted_E1")
        if o == "E1" and n != "E1":
            chg[a].append("carO_demoted" if a in set(sel("literature_taskB_downgrade_carO").source_acc) else
                          "retier_lambda_max_only" if a in RETIER else "R2_E1_withdrawn" if a in R2_E1DOWN else "E1_removed")
        if a in R2CH:
            chg[a].append(R2CH[a])
        if a in R2_REPLACE:
            chg[a].append(f"R2_primary_paper_PMID{R2_REPLACE[a]}")
        if a in set(MOV.source_acc):
            chg[a].append("R2_membership_curated_override")
        if o == "E2" and n != "E2" and n != "E1":
            chg[a].append(f"E2_lost(ref {fe0.set_index('source_acc').loc[a, 'e2_ref']})")
        if n == "E2" and o != "E2":
            chg[a].append(f"E2_gained(ref {fe.loc[a, 'e2_ref']})")
        if o == "E2" and n == "E2" and fe0.set_index("source_acc").loc[a, "e2_ref"] != fe.loc[a, "e2_ref"]:
            chg[a].append(f"E2_ref_changed({fe0.set_index('source_acc').loc[a, 'e2_ref']}->{fe.loc[a, 'e2_ref']})")
        if a in pol_down:
            chg[a].append("F1_conflict_downgrade" + ("" if a in signed_down else "_policy_derived"))
        elif fe.loc[a, "call_conflict"] == 1:
            chg[a].append("F1_conflict_flag")
        if a in ENG:
            chg[a].append(f"engineered(wild_type {ENG[a]})")
        if a == "O74870":
            chg[a].append("needs_manual (DEFER; meiotic-role annotation, no rhodopsin function asserted)")
        if o != n and not chg[a]:
            chg[a].append(f"{o}->{n}")
    fe["v160_change"] = [";".join(chg[a]) or None for a in fe.index]
    lv = pd.crosstab(fe.evidence_level_v150, fe.evidence_level)
    log("[5] E-level transitions v1.5.0 (rows) -> v1.6.0 (cols):\n" + lv.to_string())
    log(f"[5] v1.6.0 levels (all records): {fe.evidence_level.value_counts().sort_index().to_dict()}")
    log(f"[5] v1.6.0 levels (counted, non-engineered): {fe[fe.is_engineered == 0].evidence_level.value_counts().sort_index().to_dict()}")
    e2l = sum("E2_lost" in str(x) for x in fe.v160_change); e2g = sum("E2_gained" in str(x) for x in fe.v160_change)
    e2c = sum('E2_ref_changed' in str(x) for x in fe.v160_change)
    log(f'[5] E2 lost {e2l}; E2 gained {e2g}; E2 ref changed {e2c}')

    fe = fe.reset_index().drop(columns=["v14"])
    cols = ["source_acc", "func_class", "evidence_level", "basis", "helixC_motif", "motif_class", "exp_class", "e2_ref",
            "e2_identity", "clade_id", "clade_function", "override_rule", "func_class_v14", "func_class_v150",
            "evidence_level_v150", "basis_v150", "call_conflict", "call_conflict_exact", "call_conflict_detail",
            "is_engineered", "wild_type_acc", "v160_change"]
    put(con, fe[cols], "function_evidence", ["source_acc"])

    # characterized_protein / record_clade consistency with the ladder
    cp["is_engineered"] = cp.source_acc.map(lambda a: int(a in ENG))
    put(con, cp, "characterized_protein", ["source_acc"])
    rcl = pd.read_sql("select * from record_clade", con)
    rcl["e1_class_this_record"] = rcl.source_acc.map(lambda a: EXP2V14.get(e1_v16.get(a)) if a in e1_v16 else None)
    if CF_RECOMPUTE:
        rcl["clade_function"] = rcl.source_acc.map(cf_new)
        rcl["clade_function_source"] = rcl.source_acc.map(cfs_new)
        cl = pd.read_sql("select * from clade", con)
        cfm = {(1 if r.level == "clade" else 2, r.group_id): r for r in CF16.itertuples()}
        for i, r in cl.iterrows():
            x = cfm.get((int(r.level), r.clade_id))
            if x is not None:
                cl.loc[i, ["n_E1", "top_frac", "consensus_status", "e1_function_consensus", "e1_classes_records"]] = \
                    [x.n_E1, x.top_frac, x.consensus_status, x.clade_function, x.E1_classes or None]
        put(con, cl, "clade", ["clade_id"])
        put(con, CF16, "clade_function_consensus", ["level", "group_id"])
    put(con, rcl, "record_clade", ["source_acc"])

    # exact-duplicate flags (ADD-B) and E1 representatives (ADD-I rule: sorted-first non-engineered E1 per exact cluster)
    add_cols(con, "protein", [("exact_duplicate_of", "TEXT")])
    for r in asel("ADD-B").itertuples():
        m = re.search(r"exact_duplicate_of=(\S+)", r.new_value)
        if m:
            con.execute("UPDATE protein SET exact_duplicate_of=? WHERE source_acc=?", (m.group(1), r.source_acc))
    add_cols(con, "redundancy", [("e1_representative", "TEXT")])
    red = pd.read_sql("select source_acc, exact_nr_cluster from redundancy", con)
    e1c = red[red.source_acc.isin([a for a in e1_v16 if a not in ENG])].sort_values(["exact_nr_cluster", "source_acc"])
    rep = e1c.groupby("exact_nr_cluster").source_acc.first()
    e1c["rep"] = e1c.exact_nr_cluster.map(rep)
    con.executemany("UPDATE redundancy SET e1_representative=? WHERE source_acc=?", list(zip(e1c.rep, e1c.source_acc)))
    multi = e1c.groupby("exact_nr_cluster").size()
    log(f"[5] E1 exact-sequence clusters with >1 E1 record: {int((multi > 1).sum())}; unique E1 sequences (non-engineered): {len(rep)}")
    log(f"[5] engineered records: {len(ENG)}; exact_duplicate_of set: {len(asel('ADD-B')[asel('ADD-B').new_value.str.contains('exact_duplicate_of')])}")

    # ------------------------------------------------------------------ 6. publications + links
    pub = pd.read_sql("select * from publication", con)
    ap = pd.read_sql("select * from assertion_publication", con)
    doi2pid = {str(d).lower(): int(i) for d, i in zip(pub.doi, pub.publication_id) if isinstance(d, str)}
    pmid2pid = {str(int(p)): int(i) for p, i in zip(pub.pmid, pub.publication_id) if pd.notna(p)}
    next_pid = int(pub.publication_id.max()) + 1
    new_pubs = []

    def pid_for(pm):
        nonlocal next_pid
        if pm in pmid2pid:
            return pmid2pid[pm]
        d = doi_of(pm)
        if d and d in doi2pid:
            pid = doi2pid[d]
            if pd.isna(pub.loc[pub.publication_id == pid, "pmid"]).all():
                pub.loc[pub.publication_id == pid, "pmid"] = float(pm)
            pmid2pid[pm] = pid
            return pid
        m = meta.loc[pm]
        pid = next_pid; next_pid += 1
        new_pubs.append(dict(publication_id=pid, doi=d, pmid=float(pm), title=m.title, journal=m.journal,
                             year=int(m.year) if m.year else None,
                             raw_ref=f"{m.first_author} {m.year} {m.journal} doi:{d} PMID:{pm}",
                             ingestion="pubmed_eutils_v160", notes="added v1.6.0 (PubMed E-utilities esummary/efetch)"))
        pmid2pid[pm] = pid
        if d:
            doi2pid[d] = pid
        return pid

    # ADD-E: publication 69 (CryoRhodopsins, Sci Adv 2025) gets its PMID
    pub.loc[pub.publication_id == 69, "pmid"] = 40614199.0
    pmid2pid["40614199"] = 69

    def sentence_hit(pm, exp):
        m = meta.loc[pm]
        text = f"{m.title}. {m.abstract}"
        for s in re.split(r"(?<=[.!?])\s+", text):
            if any(k in s.lower() for k in EXP2KEYWORDS.get(exp, [])):
                return s.strip()[:500]
        return None

    caveat_of = {r.source_acc: r.rationale for r in add.itertuples() if r.recommended_decision == "APPROVE_WITH_CAVEAT"}
    # post-build review: support links whose abstract lacks a class keyword get an explicit caveat
    caveat_of.setdefault("Q6R5N7", "Abstract reports heterologous expression and light-dependent photoelectric responses of "
                                   "purple-membrane films; outward proton pumping is inferred, not stated explicitly in the abstract.")
    next_aid = int(ap.assertion_id.max()) + 1
    links = []

    def link(acc, pm, exp, role, counts, decision, cnote, caveat=None):
        nonlocal next_aid
        hit = sentence_hit(pm, exp) if exp else None
        links.append(dict(assertion_id=next_aid, publication_id=pid_for(pm), source_acc=acc,
                          assertion=EXP2ASSERTION.get(exp, "lambda-max / spectral value") if role != "compilation" else "lambda-max / spectral value (compilation)",
                          verdict=("verified" if hit else "curator_approved_not_verified_in_abstract") if role == "support" else role,
                          evidence_basis="abstract" if hit else "title_metadata",
                          snippet=hit or meta.loc[pm, "title"], checked_at=now, caveat=caveat,
                          snippet_verified_in_retrieved_text=int(bool(hit)), is_active=1, counts_as_support=counts,
                          link_role=role, curator_decision=decision, curator_note=cnote, decided_by=CURATOR,
                          decided_at=DEC_DATE, replaces_publication_id=None))
        next_aid += 1

    exp_now = dict(zip(cp.source_acc, cp.exp_class))
    # (i) promotions + engineered transfer
    for acc, (e, pm, doi, g) in PROMO_EXP.items():
        cav = None
        if acc == "A0A0M5L0M3":
            cav = "Abstract reports the cryo-EM structure of this retinal-binding proteorhodopsin paralog; pumping activity is not stated in the abstract."
        if g.startswith("engineered_construct_transfer"):
            cav = f"Experiment performed on engineered construct {g.split(':')[1]} (His-tag; >=99% identity); E1 transferred to the wild type per the v1.6.0 engineered-construct policy."
        link(acc, pm, e, "support", 1, "approved_v160", f"{g} (signed {DEC_DATE})", cav)
    # (ii) taskD fills
    for r in td.itertuples():
        pm = re.search(r"pmid=(\d+)", r.new_value).group(1)
        link(r.source_acc, pm, exp_now.get(r.source_acc), "support", 1, "approved_v160", f"taskD primary citation (signed {DEC_DATE})")
    # (iii) addendum A/B primaries
    for r in pd.concat([asel("ADD-A"), asel("ADD-B")]).itertuples():
        for pm in [p for p in toks(r.new_value.split("|")[0].replace(" ", "")) if p not in COMP]:
            if any(l["source_acc"] == r.source_acc and l["publication_id"] == pid_for(pm) for l in links):
                continue
            link(r.source_acc, pm, exp_now.get(r.source_acc), "support", 1, "approved_v160",
                 f"{r.group_id} (signed {DEC_DATE})", caveat_of.get(r.source_acc))
    # (iv) CryoR2: primary support + 2026 follow-up as context
    for r in asel("ADD-E").itertuples():
        link(r.source_acc, "40614199", exp_now.get(r.source_acc), "support", 1, "approved_v160", f"ADD-E (signed {DEC_DATE})")
        link(r.source_acc, "41580893", None, "context", 0, "context_not_counted", "ADD-E follow-up study; context only")
    # (v) compilation links from the labelling spec
    for r in spec.itertuples():
        link(r.source_acc, str(r.publication_pmid), None, "compilation", 0, r.curator_decision, r.curator_note)
    # (vi) R2: new primary paper (A0ACE3JIR6) and homolog context link (A0A0P6XBM7)
    for acc, pm in R2_REPLACE.items():
        link(acc, pm, exp_now.get(acc), "support", 1, "approved_v160_r2", f"R2 e1_replace_paper (signed {DEC_DATE})",
             "Quote verified in the author's M.Sc. thesis (Univ. Guelph 2016) that reproduces this published PaR dataset; "
             "the journal version of record was not re-fetched.")
    if "A0A0P6XBM7" in R2_E1DOWN:
        link("A0A0P6XBM7", "36724978", None, "context", 0, "context_not_counted",
             "R2: BeNaR outward Na+ pump (89.2% identical homolog, not this protein); homology context only")
    nl = pd.DataFrame(links)
    R2_QUOTE = {
        ("A0A0M5L0M3", "40651474"): ("Ps PR pumps protons as demonstrated by the pH changes in E. coli cell suspension (Fig. 1F).",
                                     "fulltext (bioRxiv preprint 10.1101/2025.04.29.651185 of the same paper; Results, Fig. 1F)",
                                     "Record is the Ps PR proteorhodopsin paralog (PDB 9R22, 98.3% identity), not the retinal-less "
                                     "flotillin-associated rhodopsin named in the title."),
        ("A0ACE3JIR6", "26260121"): ("Robust light-induced acidification was observed in both cases, consistent with BR-like outward "
                                     "proton transport.", "fulltext (author thesis reproducing the published dataset; Sec. 3.4, Fig. S4)", None),
    }
    for (acc, pm), (q, basis, cav) in R2_QUOTE.items():
        if acc == "A0A0M5L0M3" and not len(r2sel("e1_keep_with_quote")):
            continue
        mk = (nl.source_acc == acc) & (nl.publication_id == pid_for(pm))
        assert mk.sum() == 1, (acc, pm, int(mk.sum()))
        nl.loc[mk, ["verdict", "evidence_basis", "snippet", "snippet_verified_in_retrieved_text"]] = ["verified_fulltext", basis, q, 1]
        if cav:
            nl.loc[mk, "caveat"] = cav
    if "Q6R5N7" in R2_E1DOWN:
        mk = (nl.source_acc == "Q6R5N7") & (nl.link_role == "support")
        assert mk.sum() == 1
        nl.loc[mk, ["link_role", "counts_as_support", "curator_decision", "curator_note"]] = \
            ["context", 0, "r2_e1_withdrawn", "R2: abstract reports a photoelectric film response only; E1 withdrawn (signed)"]
    # links already present for the same record+publication are not duplicated
    key_old = set(zip(ap.source_acc, ap.publication_id))
    dup = [(a, p) in key_old for a, p in zip(nl.source_acc, nl.publication_id)]
    nl = nl[~pd.Series(dup, index=nl.index)]
    ap = pd.concat([ap, nl], ignore_index=True)
    pub = pd.concat([pub, pd.DataFrame(new_pubs)], ignore_index=True)
    put(con, pub, "publication", ["publication_id"])
    put(con, ap, "assertion_publication", ["assertion_id", "publication_id"])
    log(f"[6] publications added: {len(new_pubs)} (total {len(pub)}); links added {len(nl)} "
        f"(skipped {sum(dup)} already present) by role {nl.link_role.value_counts().to_dict()}")
    sup_new = nl[nl.link_role == "support"]
    log(f"[6] new support links with quote verified in retrieved text (abstract or full text): {int(sup_new.snippet_verified_in_retrieved_text.sum())}/{len(sup_new)}")
    sup = set(ap[(ap.is_active == 1) & (ap.counts_as_support == 1)].source_acc)
    e1_now = fe[fe.evidence_level == "E1"].source_acc
    linkless = sorted(set(e1_now) - sup)
    log(f"[6] E1 records with >=1 active support link: {len(set(e1_now) & sup)}/{len(e1_now)}; linkless: {linkless}")

    # ------------------------------------------------------------------ 7. new / refreshed tables
    dec = pd.concat([grp.assign(source_file="curation_v160_groups_signed.tsv", row_type="group"),
                     rec.assign(source_file="curation_v160_records_signed.tsv", row_type="record"),
                     pol.assign(source_file="curation_v160_policy_clarifications_signed.tsv", row_type="policy"),
                     add.assign(source_file="curation_v160_addendum_citations_signed.tsv", row_type="addendum"),
                     r2.assign(source_file="curation_v160_r2_signed.tsv", row_type="r2_referee_followup")],
                    ignore_index=True)
    dec.insert(0, "decision_id", range(1, len(dec) + 1))
    dec["decided_by"] = CURATOR; dec["decided_at"] = DEC_DATE
    put(con, dec, "curation_v160_decision", ["decision_id"])
    log(f"[7] curation_v160_decision rows: {len(dec)}")

    nfc = pd.read_csv(f"{cur}/novel_family_candidates_v160.tsv", sep="\t", dtype=str)
    con.execute("DROP TABLE IF EXISTS novel_family_candidate")
    con.execute("CREATE TABLE novel_family_candidate (" + ", ".join(
        f'"{c}" {"REAL" if c in ("score", "evalue") else "INTEGER" if c in ("seq_length", "has_retinalK", "taxonomy_id") else "TEXT"}'
        for c in nfc.columns) + ")")
    if len(nfc):
        nfc.to_sql("novel_family_candidate", con, index=False, if_exists="append")
    put(con, pd.read_csv(f"{cur}/novel_family_funnel_v160.tsv", sep="\t"), "novel_family_funnel", ["family"])
    log(f"[7] novel_family_candidate rows: {len(nfc)} by family {nfc.family.value_counts().to_dict()} (counts unaffected)")

    # R2 tables: Foldseek structure search (R-C1), family-HMM flag (R-V3), blind audit (R-V2)
    fsh = pd.read_csv(f"{cur}/foldseek_hits_v160.tsv", sep="\t", low_memory=False)
    put(con, fsh, "foldseek_hit", ["target_id"])
    put(con, pd.read_csv(f"{cur}/foldseek_funnel_v160.tsv", sep="\t"), "foldseek_funnel")
    put(con, pd.read_csv(f"{cur}/foldseek_queries_v160.tsv", sep="\t"), "foldseek_query", ["query_id"])
    log(f"[7] foldseek_hit rows {len(fsh)} by tier {fsh.watchlist_tier.value_counts().to_dict()}")
    nff = pd.read_csv(f"{cur}/novel_family_flag_v160.tsv", sep="\t", dtype={"source_acc": str})
    nff["novel_family_hit"] = nff.novel_family_hit.where(nff.novel_family_hit.notna() & (nff.novel_family_hit != ""), None)
    assert set(nff.source_acc) == set(fe.source_acc)
    put(con, nff, "novel_family_flag", ["source_acc"])
    log(f"[7] novel_family_flag: {int(nff.novel_family_hit.notna().sum())}/{len(nff)} flagged {nff.novel_family_hit.value_counts().to_dict()}")
    smp = pd.read_csv(f"{cur}/audit_sample_v160_seed160.tsv", sep="\t", comment="#", dtype=str)
    bl = pd.read_csv(f"{cur}/audit_blind_calls_v160.tsv", sep="\t", dtype=str)
    au = bl.merge(smp.rename(columns={"evidence_level": "tier", "func_class": "db_func_class_at_audit",
                                      "call_conflict": "db_call_conflict_at_audit"}), on="source_acc", how="left", validate="1:1")
    assert len(au) == 120 and au.tier.notna().all()
    au["exact_match"] = (au.blind_call == au.db_func_class_at_audit).astype(int)
    now_fc = dict(zip(fe.source_acc, fe.func_class)); now_lv = dict(zip(fe.source_acc, fe.evidence_level))
    au["db_func_class_v160"] = au.source_acc.map(now_fc); au["db_evidence_level_v160"] = au.source_acc.map(now_lv)
    put(con, au, "audit_blind", ["audit_id"])
    ag = []
    for tier, g in list(au.groupby("tier")) + [("E2-E4", au)]:
        gr = g[g.blind_call != "unresolvable"]
        for metric, sub in (("primary_exact", g), ("secondary_exact_excl_unresolvable", gr)):
            k, n = int(sub.exact_match.sum()), len(sub); lo, hi = wilson(k, n)
            ag.append(dict(tier=tier, metric=metric, n_match=k, n=n, agreement=k / n, wilson_lo=lo, wilson_hi=hi,
                           note="pre-correction (DB calls frozen at audit draw); blind annotator used homology to characterised proteins"))
    AG = pd.DataFrame(ag)
    put(con, AG, "audit_agreement")
    for r in AG[AG.metric == "primary_exact"].itertuples():
        log(f"[7] audit {r.tier}: {r.n_match}/{r.n} = {r.agreement:.3f} [{r.wilson_lo:.3f}-{r.wilson_hi:.3f}]")

    # LOCO validation: Stage-1 V0 + addendum sensitivity + final v1.6.0 E1 set (dedup, non-engineered)
    sens = pd.read_csv(f"{cur}/loco_sensitivity_v160.tsv", sep="\t")
    st1 = pd.read_csv(f"{cur}/loco_validation_stage1_v160.tsv", sep="\t")
    v0 = sens[sens.variant == "V0_baseline"].reset_index(drop=True)
    assert np.allclose(v0[["n", "n_assigned", "n_correct"]].values, st1[["n", "n_assigned", "n_correct"]].values)
    red2 = pd.read_sql("select source_acc, e1_representative from redundancy", con)
    E = fe[(fe.evidence_level == "E1") & fe.exp_class.isin(EXP2V14) & (fe.is_engineered == 0)].merge(red2, on="source_acc", how="left")
    E = E[E.e1_representative == E.source_acc].merge(rc, on="source_acc", how="left")
    E["exp"] = E.exp_class.map(EXP2V14); E["v14"] = E.func_class_v14
    fin, fin_rec = loco_evaluate(E)
    fin.insert(0, "variant", "FINAL_v160_E1_dedup_noeng"); fin.insert(1, "n_E1", len(E)); fin.insert(2, "n_clades", E.rc_clade.nunique())
    sens["ci_method"] = "wilson"
    loco = pd.concat([sens, fin], ignore_index=True)
    loco.insert(0, "release_set", np.where(loco.variant.str.startswith("FINAL"), "1.6.0", "1.5.0_sensitivity"))
    put(con, loco, "loco_validation")
    put(con, fin_rec[["source_acc", "exp", "v14", "motif_class", "rc_clade", "sim_tier_LOO", "sim_tier_LOSO", "sim_tier_LOCO"]],
        "loco_validation_record", ["source_acc"])
    show = fin[(fin.subset == "all_E1") | ((fin.holdout == "LOCO") & (fin.subset == "sim_E4"))]
    for r in show.itertuples():
        log(f"[7] FINAL LOCO {r.subset}/{r.holdout}/{r.policy}: n={r.n} cov={r.n_assigned}/{r.n} "
            f"prec={r.n_correct}/{r.n_assigned}={r.precision:.3f} [{r.prec_lo:.2f}-{r.prec_hi:.2f}]")
    log(f"[7] FINAL set n={len(E)}, clades={E.rc_clade.nunique()}, sim tiers LOCO {fin_rec.sim_tier_LOCO.value_counts().to_dict()}")

    # motif benchmark (wp5 logic) on the final E1 set
    b = E.copy()
    b["exp_v14vocab"] = b.exp
    b["motif_call"] = b.motif_class.fillna("unassigned"); b["func_call"] = b.func_class_v14.fillna("unassigned")
    rows = []
    for c in ["motif_call", "func_call"]:
        b[f"{c}_assigned"] = ~b[c].isin(["unassigned", "insufficient_data"])
        b[f"{c}_correct"] = [agree_v14(v, e) for v, e in zip(b[c], b.exp_v14vocab)]
        for g, x in [("all", b)] + list(b.groupby("exp_v14vocab")):
            n = len(x); na = int(x[f"{c}_assigned"].sum()); k = int((x[f"{c}_assigned"] & x[f"{c}_correct"]).sum())
            lo1, hi1 = wilson(na, n); lo2, hi2 = wilson(k, na)
            rows.append(dict(call=c, exp_class=g, n=n, n_assigned=na, coverage=na / n if n else np.nan, cov_lo=lo1, cov_hi=hi1,
                             n_correct=k, precision=k / na if na else np.nan, prec_lo=lo2, prec_hi=hi2, ci_method="wilson"))
    put(con, pd.DataFrame(rows), "motif_benchmark")

    # spectral audit: lambda-max records that are E1-eligible and not engineered (v1.5 filter + engineered exclusion)
    elig = set(cp[(cp.e1_eligible.astype(float) == 1) & (cp.is_engineered == 0)].source_acc)
    n_sa0 = len(sa)
    sa = sa[sa.source_acc.isin(elig)].copy()
    sa["exp_class"] = sa.source_acc.map(dict(zip(cp.source_acc, cp.exp_class)))
    sa["func_evidence"] = sa.source_acc.map(dict(zip(fe.source_acc, fe.evidence_level)))
    put(con, sa, "spectral_audit", ["source_acc"])
    log(f"[7] spectral_audit rows {n_sa0} -> {len(sa)}")

    fcd = pd.read_sql("select * from func_class_definition", con)
    if "unassigned" not in set(fcd.func_class):
        fcd.loc[len(fcd)] = dict(func_class="unassigned",
                                 definition="v1.6.0: legacy v1.4 call conflicts with the helix-C motif prediction (E3/E4 only); "
                                            "call withdrawn, see function_evidence.call_conflict_detail", n_records=0)
    cnt = fe[fe.is_engineered == 0].func_class.value_counts()
    fcd["n_records"] = fcd.func_class.map(cnt).fillna(0).astype(int)
    fcd["n_records_incl_engineered"] = fcd.func_class.map(fe.func_class.value_counts()).fillna(0).astype(int)
    put(con, fcd, "func_class_definition", ["func_class"])

    # ------------------------------------------------------------------ 8. schema: drop alias_v14 + compat views; v_master
    for (v,) in con.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
        con.execute(f'DROP VIEW "{v}"')
    con.execute("ALTER TABLE membership DROP COLUMN alias_v14")
    # informational legacy labels elsewhere are renamed so no 'alias' mechanism remains in the schema
    for t in ("status_definition", "route3_candidate_support"):
        con.execute(f'ALTER TABLE "{t}" RENAME COLUMN alias_v14 TO status_label_v14')
    V = {
        "v_master": """SELECT p.mrdb_acc, p.source_acc, p.protein_name, p.organism, p.organism_id, p.tax_domain, p.length,
                m.membership_status, m.boundary_subtype, m.membership_score, m.retinal_site_residue,
                f.func_class, f.evidence_level, f.basis AS function_basis, f.func_class_v14, f.helixC_motif, f.motif_class,
                f.call_conflict, f.call_conflict_detail, f.is_engineered, f.wild_type_acc,
                CASE WHEN f.is_engineered = 1 THEN 0 ELSE 1 END AS counts_eligible,
                p.exact_duplicate_of, r.e1_representative,
                rc.clade_id, rc.subclade_id, rc.source AS clade_source,
                pl.clade_lwr, pl.clade_call_qc AS placement_call, c.name AS clade_name,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN pl.clade_id END AS tentative_clade_id,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN tc.name END AS tentative_clade_name,
                g.gtdb_taxonomy, a.model_id AS afdb_model_id, a.global_plddt AS afdb_global_plddt
                FROM protein p JOIN membership m USING (source_acc)
                LEFT JOIN function_evidence f USING (source_acc)
                LEFT JOIN redundancy r USING (source_acc)
                LEFT JOIN record_clade rc USING (source_acc)
                LEFT JOIN clade c ON c.clade_id = rc.clade_id
                LEFT JOIN (SELECT * FROM placement WHERE tree_id='MR_RT_003' AND is_current=1) pl USING (source_acc)
                LEFT JOIN clade tc ON tc.clade_id = pl.clade_id
                LEFT JOIN gtdb_taxonomy g USING (source_acc)
                LEFT JOIN (SELECT * FROM afdb_model WHERE status='ok') a USING (source_acc)""",
        "v_typeI_member": "SELECT * FROM v_master WHERE membership_status LIKE 'typeI_member%'",
        "v_typeI_candidate": "SELECT * FROM v_master WHERE membership_status LIKE 'typeI_candidate%'",
        "v_boundary_family": "SELECT * FROM v_master WHERE membership_status='boundary_family'",
        "v_heliorhodopsin": "SELECT * FROM v_master WHERE membership_status='heliorhodopsin'",
        "v_counted": "SELECT * FROM v_master WHERE counts_eligible = 1",
        "v_call_conflict": "SELECT * FROM v_master WHERE call_conflict = 1",
        "v_engineered": "SELECT * FROM v_master WHERE is_engineered = 1",
    }
    for k, q in V.items():
        con.execute(f"CREATE VIEW {k} AS {q}")
    log(f"[8] alias_v14 dropped; views now: {sorted(V)}")

    # ------------------------------------------------------------------ 9. provenance backfill + metadata
    n03 = con.execute("SELECT COUNT(*) FROM sequence_source WHERE source_release='2026_03'").fetchone()[0]
    nv12 = con.execute("SELECT COUNT(*) FROM sequence_source WHERE source_release='v1.2.0-corpus'").fetchone()[0]
    con.execute("UPDATE sequence_source SET provenance_note = COALESCE(provenance_note || '; ', '') || "
                "'v1.6.0: source_release backfilled from ''' || source_release || '''' "
                "WHERE source_release IN ('v1.2.0-corpus', '2026_03')")
    con.execute("UPDATE sequence_source SET source_release='UniProtKB_2026_02' WHERE source_release='v1.2.0-corpus'")
    con.execute("UPDATE sequence_source SET source_release='UniProtKB_2026_03' WHERE source_release='2026_03'")
    log(f"[9] source_release backfill: v1.2.0-corpus -> UniProtKB_2026_02 ({nv12}); 2026_03 -> UniProtKB_2026_03 ({n03})")

    counted = fe[fe.is_engineered == 0]
    lvc = counted.evidence_level.value_counts().sort_index().to_dict()
    md_new = dict(C["release_metadata"])
    md_new.update({
        "n_protein_records": str(len(fe)), "n_counted_records": str(len(counted)), "n_engineered_records": str(len(ENG)),
        "evidence_level_counts_counted": json.dumps(lvc), "evidence_level_counts_all": json.dumps(fe.evidence_level.value_counts().sort_index().to_dict()),
        "n_call_conflict": str(int(fe.call_conflict.sum())), "n_conflict_downgrades": str(len(pol_down)),
        "n_E1_unique_sequences": str(len(rep)), "n_novel_family_candidates": str(len(nfc)),
        "n_typeI_member_curated": str(len(MOV)), "n_foldseek_hits": str(len(fsh)),
        "n_novel_family_flag": str(int(nff.novel_family_hit.notna().sum())),
        "audit_agreement_primary": json.dumps({r.tier: f"{r.n_match}/{r.n}" for r in AG[AG.metric == "primary_exact"].itertuples()}),
    })
    md = pd.read_sql("select * from release_metadata", con)
    md = pd.concat([pd.DataFrame([dict(release="1.6.0", key=k, value=v) for k, v in md_new.items()]), md], ignore_index=True)
    put(con, md, "release_metadata")
    bp = pd.read_sql("select * from build_provenance", con)
    prov += [
        ("function_evidence", "v1.5.0 function_evidence + curation/v160 signed decisions", "build_v160.py + mrdb_v160_lib.py",
         "v1.5 E-ladder (reproduced 5466/5466) with v1.6.0 E1 set; MMseqs2 E2 re-search; compatibility-aware conflict rule",
         "mmseqs easy-search -s 7.5 --min-seq-id 0.9 -c 0.8 --cov-mode 0; same level-1 clade; unanimous class; " +
         ("clade_function recomputed from the v1.6.0 non-engineered E1 set (v1.5.0 rule: >=2 E1, >=80%; subclade then clade); "
          "R2 audit rules and schizorhodopsin reassignment applied after the conflict rule" if CF_RECOMPUTE else "clade_function frozen at v1.5.0"),
         '["characterized_protein", "membership", "record_clade", "protein"]'),
        ("assertion_publication", "pmid_metadata_v160.tsv; link_labelling_spec_v160.tsv; signed decisions", "build_v160.py",
         "support/compilation/context links", "snippet_verified_in_retrieved_text = class keyword found in PubMed title/abstract", '["publication"]'),
        ("loco_validation", "loco_sensitivity_v160.tsv + final v1.6.0 E1 set", "mrdb_v160_lib.loco_evaluate", "LOO/LOSO/LOCO simulated tiers",
         "Wilson 95% CI; final set = E1, non-engineered, one record per exact-sequence cluster", '["function_evidence", "record_clade", "redundancy"]'),
        ("curation_v160_decision", "curation/v160/*_signed.tsv", "build_v160.py", "concatenate", "", "[]"),
        ("novel_family_candidate", "novel_family_candidates_v160.tsv (r2_prepare_inputs.py)", "build_v160.py",
         "Foldseek watchlist rows (structure_only_no_PF01036 + underrepresented_family); no membership change", "", '["foldseek_hit"]'),
        ("foldseek_hit", "Foldseek web server (search.foldseek.com) afdb50 + mgnify_esm30; foldseek_hits_v160.tsv", "r2_prepare_inputs.py + tools/mrdb_search.py",
         "3Di+AA search of family representatives; funnel E<=1e-3, prob>=0.9, not in corpus/external set, K216, type-I over HeR, length>=200",
         "server cap 1000 hits per query and database; MerMAID query skipped", "[]"),
        ("novel_family_flag", "tools/family_flag.py on the corpus FASTA (novel_family_flag_v160.tsv)", "tools/family_flag.py",
         "hmmsearch 5 family HMMs + PF01036", "-Z 5466 -E 1e-5; flag = best family E<=1e-10 and bits > PF01036 bits", "[]"),
        ("audit_blind", "audit_sample_v160_seed160.tsv + audit_blind_calls_v160.tsv", "build_v160.py",
         "blind re-annotation of 120 records (40 per tier E2-E4)", "Wilson 95% CI (audit_agreement)", "[]"),
        ("clade_function_consensus", "record_clade + v1.6.0 E1 set", "r2_clade_function.py", "v1.5.0 consensus rule", ">=2 E1, >=80%", '["record_clade", "characterized_protein"]'),
        ("membership", "v1.5.0 membership", "build_v160.py", "DROP COLUMN alias_v14; status_definition/route3_candidate_support alias_v14 renamed status_label_v14", "", "[]"),
        ("sequence_source", "v1.5.0 sequence_source", "build_v160.py", "source_release backfill", "UniProtKB_2026_02 / UniProtKB_2026_03", "[]"),
    ]
    for t, sdat, scr, alg, par, dep in prov:
        bp.loc[len(bp)] = dict(table_name=t, source_data=sdat, script=scr, algorithm=alg, params=par, upstream_deps=dep,
                               release="1.6.0", built_at=now)
    put(con, bp, "build_provenance")
    con.commit()
    con.execute("VACUUM")
    con.close()
    logp = os.path.join(root, C["log_file"])
    os.makedirs(os.path.dirname(logp), exist_ok=True)
    open(logp, "w").write("\n".join(LOG) + "\n")
    print("built", out)


if __name__ == "__main__":
    main()
