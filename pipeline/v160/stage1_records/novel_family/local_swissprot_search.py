"""Stage 1 (novel-family candidate layer), step 2b:
Supplementary LOCAL hmmsearch against a freshly-downloaded, current Swiss-Prot (reviewed
UniProtKB; stable, curated, no demerge/deletion churn -- unlike EBI's indexed TrEMBL-heavy
"uniprot" snapshot, which step 2 (fetch_and_filter_candidates.py) found to be lagging a
large-scale UniProt redundancy cleanup: 1,787/1,795 of its surviving candidate accessions are
now permanently deleted). This step searches the same 5 family HMMs locally against
uniprot_sprot.fasta (575,748 sequences, downloaded today from the current UniProt release),
applies the same exclusion/length/retinal-K logic, and produces a second, currently-resolvable
candidate table. Runs in ~1-4s per family (HMMER 3.4, local binary).
"""
import os, re, time, sqlite3, subprocess, urllib.request
import pandas as pd
import numpy as np
from Bio import SeqIO, AlignIO

BASE = "/workspace/v160/novel"
CAND = f"{BASE}/candidates"
LOCAL = f"{BASE}/local_search"
CACHE = f"{BASE}/cache"
os.makedirs(CAND, exist_ok=True)

FAMS = ["viral_rhodopsin", "schizorhodopsin", "xenorhodopsin", "bestrhodopsin", "MerMAID"]
DB_PATH = "/workspace/v150/build/db/microrhododb_v1.5.0.sqlite"
HMMALIGN_BIN = "/workspace/.conda/mrdb/bin/hmmalign"
SPROT_FASTA = f"{BASE}/refdb/uniprot_sprot.fasta"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def exclusion_sets():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    corpus_accs = set(pd.read_sql_query("SELECT source_acc FROM protein", conn)["source_acc"])
    ext_val_accs = set(pd.read_sql_query("SELECT ext_acc FROM external_validation", conn)["ext_acc"])
    conn.close()
    return corpus_accs | ext_val_accs


TBLOUT_COLS = ["family", "accession", "swissprot_entry", "evalue", "score", "description"]


def parse_tblout(path, fam):
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.split(None, 18)
            target = parts[0]
            evalue_full = float(parts[4])
            score_full = float(parts[5])
            desc = parts[18].strip() if len(parts) > 18 else ""
            m = re.match(r"^(sp|tr)\|([^|]+)\|(\S+)$", target)
            acc = m.group(2) if m else target
            rows.append(dict(family=fam, accession=acc, swissprot_entry=target,
                              evalue=evalue_full, score=score_full, description=desc))
    return pd.DataFrame(rows, columns=TBLOUT_COLS)


def load_sprot_seqs():
    log("  indexing Swiss-Prot sequences by accession...")
    seqs = {}
    for rec in SeqIO.parse(SPROT_FASTA, "fasta"):
        m = re.match(r"^(sp|tr)\|([^|]+)\|", rec.id)
        acc = m.group(2) if m else rec.id
        seqs[acc] = str(rec.seq)
    log(f"  indexed {len(seqs)} Swiss-Prot sequences")
    return seqs


def seed_length_range(fam, tol_lo=0.6, tol_hi=1.5):
    faa = f"{BASE}/seeds/fasta/{fam}.faa"
    lens = [len(r.seq) for r in SeqIO.parse(faa, "fasta")]
    lo = int(np.floor(tol_lo * min(lens)))
    hi = int(np.ceil(tol_hi * max(lens)))
    return min(lens), max(lens), lo, hi


def hmmalign_confirm(fam, df, seqs):
    if len(df) == 0:
        return df.assign(has_retinalK=pd.Series(dtype=bool))
    cand_fasta = f"{CAND}/{fam}_sprot_candidates_prealign.fasta"
    with open(cand_fasta, "w") as fh:
        for acc in df["accession"]:
            fh.write(f">{acc}\n{seqs[acc]}\n")
    hmm = f"{BASE}/seeds/fasta/{fam}.hmm"
    seed_aln = f"{BASE}/seeds/fasta/{fam}.aln.fasta"
    out_sto = f"{CAND}/{fam}_sprot_mapali.sto"
    cmd = [HMMALIGN_BIN, "--amino", "--mapali", seed_aln, "--trim", "-o", out_sto, hmm, cand_fasta]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  {fam}: hmmalign FAILED: {r.stderr[:300]}")
        return df.assign(has_retinalK=np.nan)
    aln = AlignIO.read(out_sto, "stockholm")
    seed_ids = set(r2.id for r2 in SeqIO.parse(seed_aln, "fasta"))
    seed_rows = [r2 for r2 in aln if r2.id in seed_ids]
    cand_rows = [r2 for r2 in aln if r2.id not in seed_ids]
    arr_seed = np.array([list(str(r2.seq)) for r2 in seed_rows])
    k_freq = (arr_seed == "K").mean(axis=0)
    retinalK_col = int(np.argmax(k_freq))
    log(f"  {fam}: mapali retinalK_col={retinalK_col} (frac={k_freq[retinalK_col]:.2f} in seeds) "
        f"n_seed_rows={len(seed_rows)} n_cand_rows={len(cand_rows)}")
    tol = 2
    has_k, windows = [], []
    for r2 in cand_rows:
        seq = str(r2.seq)
        window = seq[max(0, retinalK_col - tol): retinalK_col + tol + 1]
        has_k.append("K" in window)
        windows.append(window)
    cand_result = pd.DataFrame({"accession": [r2.id for r2 in cand_rows],
                                 "has_retinalK": has_k, "mapali_window": windows})
    return df.merge(cand_result, on="accession", how="left")


if __name__ == "__main__":
    log("Loading exclusion sets + Swiss-Prot sequence index")
    excl = exclusion_sets()
    excl_clean = set(a.split(".")[0] for a in excl if isinstance(a, str))
    seqs = load_sprot_seqs()

    all_final = []
    funnel = []
    for fam in FAMS:
        df = parse_tblout(f"{LOCAL}/{fam}_sprot.tbl", fam)
        n_raw = len(df)
        df["accession_clean"] = df["accession"].str.split(".").str[0]
        df_novel = df[~(df["accession_clean"].isin(excl_clean) | df["accession"].isin(excl))].drop(columns=["accession_clean"])
        n_novel = len(df_novel)

        seed_min, seed_max, lo, hi = seed_length_range(fam)
        df_novel = df_novel.copy()
        df_novel["seq_length"] = df_novel["accession"].map(lambda a: len(seqs.get(a, "")) or np.nan)
        df_len = df_novel[(df_novel["seq_length"] >= lo) & (df_novel["seq_length"] <= hi)]
        n_len = len(df_len)

        log(f"{fam}: sprot_hits(E<=1e-10)={n_raw} -> novel(excl.corpus+extval)={n_novel} "
            f"-> length[{lo},{hi}]_pass={n_len}")

        df_final = hmmalign_confirm(fam, df_len, seqs)
        n_retinalK = int(df_final["has_retinalK"].sum()) if len(df_final) and "has_retinalK" in df_final else 0
        log(f"{fam}: retinalK_pass={n_retinalK}/{len(df_final)}")
        funnel.append(dict(family=fam, n_sprot_hits=n_raw, n_novel_excl_known=n_novel,
                            n_length_pass=n_len, n_retinalK_pass=n_retinalK))
        if len(df_final):
            all_final.append(df_final)

    funnel_df = pd.DataFrame(funnel)
    funnel_df.to_csv(f"{CAND}/swissprot_funnel.tsv", sep="\t", index=False)
    log("Swiss-Prot funnel:\n" + funnel_df.to_string(index=False))

    FULL_COLS = TBLOUT_COLS + ["seq_length", "has_retinalK", "mapali_window"]
    full = pd.concat(all_final, ignore_index=True) if all_final else pd.DataFrame(columns=FULL_COLS)
    full.to_csv(f"{CAND}/swissprot_candidates_full.tsv", sep="\t", index=False)
    if len(full):
        final_pass = full[full.get("has_retinalK", False) == True].sort_values(["family", "evalue"])
    else:
        final_pass = pd.DataFrame(columns=FULL_COLS)
    final_pass.to_csv(f"{CAND}/swissprot_candidates_retinalK_pass.tsv", sep="\t", index=False)
    log(f"FINAL Swiss-Prot candidates passing all filters: {len(final_pass)}")
    log(final_pass[["family", "accession", "description", "evalue", "seq_length"]].to_string(index=False) if len(final_pass) else "  (none)")
