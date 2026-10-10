"""Stage 1 (novel-family candidate layer), step 2:
Fetch EBI hmmsearch results for the 5 novel-family HMMs (built in build_hmms.py),
exclude accessions already in the v1.5.0 corpus or the external_validation benchmark set,
require the defining Type-I opsin domain (Pfam PF01036, Bac_rhodopsin) in the EBI
architecture annotation, apply a standard confident-homology E-value cutoff, batch-fetch
sequences + lengths for survivors from UniProt, apply an empirically-derived per-family
length filter, and confirm the retinal-Schiff-base Lys via hmmalign --mapali against the
original seed alignment (K-frequency argmax column, re-derived in the merged seed+candidate
alignment for correctness, same convention as build_hmms.py).

IMPORTANT METHODOLOGICAL NOTE (discovered this run): the bestrhodopsin HMM is built from the
full ~1200 aa rhodopsin-bestrophin FUSION protein. Searched against full UniProt, 15,796/15,796
"novel" raw hits are returned, but 88% of them (13,958) carry Pfam architecture PF01062
(Bestrophin) WITHOUT PF01036 (Bac_rhodopsin) -- i.e. they are ordinary standalone bestrophin
channel proteins picked up via the channel half of the fusion HMM, not rhodopsins at all. Only
121/15,796 (0.77%) carry the PF01036 opsin domain. The PF01036 requirement below is therefore a
necessary correctness filter, not just a convenience filter, and is applied to all 5 families for
consistency (it is near-redundant for the other 4, which are >97% PF01036-positive already).

Corpus membership counts are NOT touched by this script -- this only produces a separate
candidate table for sign-off review.
"""
import json, os, re, time, sqlite3, subprocess, urllib.request, urllib.error
import pandas as pd
import numpy as np
from Bio import SeqIO, AlignIO

BASE = "/workspace/v160/novel"
CACHE = f"{BASE}/cache"
CAND = f"{BASE}/candidates"
os.makedirs(CACHE, exist_ok=True)
os.makedirs(f"{CACHE}/ebi_pages", exist_ok=True)
os.makedirs(f"{CACHE}/uniprot_batch", exist_ok=True)
os.makedirs(CAND, exist_ok=True)

FAMS = ["viral_rhodopsin", "schizorhodopsin", "xenorhodopsin", "bestrhodopsin", "MerMAID"]
DB_PATH = "/workspace/v150/build/db/microrhododb_v1.5.0.sqlite"  # never modified; RO only
EXT_POS_21_PATH = "/mnt/shared-workspace/v160/curation_inputs/external_positives_new.tsv"
HMMALIGN_BIN = "/workspace/.conda/mrdb/bin/hmmalign"

EBI_RESULT_URL = "https://www.ebi.ac.uk/Tools/hmmer/api/v1/result/{job_id}"
OPSIN_PFAM = "PF01036"  # Bac_rhodopsin -- defining domain of Type-I microbial rhodopsins
EVALUE_CUTOFF = 1e-10   # standard confident-homology threshold

# NOTE: the original EBI jobs (ebi_jobs.json, submitted in a prior session) were found this run
# to be severely stale: of 1,795 post-filter candidate accessions, batch UniProt retrieval
# resolved only 1 directly, and individual /uniprotkb/{acc}.json lookups on the rest showed
# 1,787/1,795 (99.6%) are now permanently INACTIVE/DELETED from UniProt ("not part of a
# reference proteome" -- a large-scale TrEMBL redundancy cleanup that happened after the
# original EBI index snapshot was built), 7 DEMERGED (recoverable via mergeDemergeTo), and 1
# resolvable directly. Fresh hmmsearch jobs (database=uniprot) were resubmitted this run via
# POST https://www.ebi.ac.uk/Tools/hmmer/api/v1/search/hmmsearch against CURRENT UniProt and
# saved to ebi_jobs_v2_fresh.json; this script now reads that file. The stale run's outputs are
# preserved under candidates_v1_stale_STALE_DATA/ for the record.
JOBS_FILE = f"{BASE}/ebi_jobs_v2_fresh.json"
EBI_PAGE_CACHE_TAG = "v2"
UNIPROT_BATCH_CACHE_DIR = f"{CACHE}/uniprot_batch_v2"
os.makedirs(UNIPROT_BATCH_CACHE_DIR, exist_ok=True)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Phase 0: exclusion sets + cross-check external_positives_new.tsv vs external_validation
# ---------------------------------------------------------------------------
def phase0_exclusion_sets():
    log("PHASE 0: building exclusion sets")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    corpus_accs = set(pd.read_sql_query("SELECT source_acc FROM protein", conn)["source_acc"])
    ext_val_df = pd.read_sql_query("SELECT * FROM external_validation", conn)
    conn.close()
    ext_val_accs = set(ext_val_df["ext_acc"])
    log(f"  corpus (protein.source_acc): n={len(corpus_accs)}")
    log(f"  external_validation (ext_acc): n={len(ext_val_accs)}")

    ext_pos_21 = pd.read_csv(EXT_POS_21_PATH, sep="\t")
    pos21_accs = set(ext_pos_21["ext_acc"])
    overlap = pos21_accs & ext_val_accs
    only_in_21 = pos21_accs - ext_val_accs
    relationship_note = (
        f"external_positives_new.tsv has {len(pos21_accs)} ext_acc values; "
        f"{len(overlap)} of these are also present in the DB external_validation table "
        f"({len(ext_val_accs)} rows total); {len(only_in_21)} are present only in the 21-row file "
        f"({sorted(only_in_21)}). Conclusion: external_positives_new.tsv is a SUBSET of "
        f"external_validation (the 366-row table is the superset/canonical exclusion source)."
        if len(only_in_21) == 0 else
        f"external_positives_new.tsv has {len(pos21_accs)} ext_acc values; "
        f"{len(overlap)} overlap with external_validation ({len(ext_val_accs)} rows); "
        f"{len(only_in_21)} are present ONLY in the 21-row file: {sorted(only_in_21)}."
    )
    log("  " + relationship_note)
    with open(f"{CAND}/exclusion_set_relationship_note.txt", "w") as fh:
        fh.write(relationship_note + "\n")

    corpus_accs_union_extval = corpus_accs | ext_val_accs
    log(f"  union(corpus, external_validation) for exclusion = {len(corpus_accs_union_extval)}")
    return corpus_accs, ext_val_accs, corpus_accs_union_extval


# ---------------------------------------------------------------------------
# Phase 1: fetch all EBI hmmsearch hit pages per family (uses on-disk cache from prior run)
# ---------------------------------------------------------------------------
def ebi_fetch_page(job_id, page=None, retries=3):
    url = EBI_RESULT_URL.format(job_id=job_id)
    if page:
        url += f"?page={page}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                raise
            log(f"    retry {attempt+1} for {url}: {e}")
            time.sleep(2)


def phase1_fetch_hits():
    log("PHASE 1: fetching EBI hmmsearch hits (all pages) per family")
    jobs = json.load(open(JOBS_FILE))
    all_hits = {}
    stats_summary = []
    for fam in FAMS:
        jid = jobs[fam]
        cache_f = f"{CACHE}/ebi_pages/{fam}_{EBI_PAGE_CACHE_TAG}_all_hits.json"
        if os.path.exists(cache_f):
            rows = json.load(open(cache_f))
            log(f"  {fam}: loaded {len(rows)} hits from cache")
            all_hits[fam] = rows
            # still need stats for the summary table -> fetch just page 1
            d1 = ebi_fetch_page(jid, page=1)
            stats = d1["result"]["stats"]
            stats_summary.append(dict(family=fam, job_id=jid, page_count=d1.get("page_count"),
                                       nhits=stats["nhits"], nreported=stats["nreported"],
                                       nincluded=stats["nincluded"], Z=stats["Z"]))
            continue
        d1 = ebi_fetch_page(jid, page=1)
        page_count = d1.get("page_count", 1)
        stats = d1["result"]["stats"]
        hits = list(d1["result"]["hits"])
        for p in range(2, page_count + 1):
            dp = ebi_fetch_page(jid, page=p)
            hits.extend(dp["result"]["hits"])
            time.sleep(0.2)
        log(f"  {fam}: job={jid} page_count={page_count} nhits={stats['nhits']} "
            f"nincluded={stats['nincluded']} fetched={len(hits)}")
        stats_summary.append(dict(family=fam, job_id=jid, page_count=page_count,
                                   nhits=stats["nhits"], nreported=stats["nreported"],
                                   nincluded=stats["nincluded"], Z=stats["Z"]))
        json.dump(hits, open(cache_f, "w"))
        all_hits[fam] = hits
    pd.DataFrame(stats_summary).to_csv(f"{CAND}/ebi_job_stats.tsv", sep="\t", index=False)
    return all_hits


# ---------------------------------------------------------------------------
# Phase 2: is_included -> PF01036 opsin-domain requirement -> evalue cutoff ->
#          exclude corpus/external_validation accessions. Full funnel logged at every stage.
# ---------------------------------------------------------------------------
def phase2_filter(all_hits, exclusion_set):
    log(f"PHASE 2: is_included -> architecture contains {OPSIN_PFAM} -> evalue<={EVALUE_CUTOFF} "
        f"-> exclude known accessions")
    funnel = []
    survivors = {}
    excl_clean = set(a.split(".")[0] for a in exclusion_set if isinstance(a, str))
    for fam in FAMS:
        hits = all_hits[fam]
        rows = []
        for h in hits:
            md = h.get("metadata") or {}
            rows.append(dict(
                family=fam, index=h.get("index"),
                accession=md.get("accession"), identifier=md.get("identifier"),
                description=md.get("description"), species=md.get("species"),
                kingdom=md.get("kingdom"), phylum=md.get("phylum"),
                taxonomy_id=md.get("taxonomy_id"), architecture=md.get("architecture") or "",
                score=h.get("score"), evalue=h.get("evalue"),
                is_included=h.get("is_included"), is_reported=h.get("is_reported"),
                ndom=h.get("ndom"),
            ))
        df = pd.DataFrame(rows)
        n_total = len(df)

        df1 = df[df["is_included"] == True].copy()
        n_included = len(df1)

        df2 = df1[df1["architecture"].str.contains(OPSIN_PFAM, regex=False)].copy()
        n_opsin = len(df2)

        df3 = df2[df2["evalue"] <= EVALUE_CUTOFF].copy()
        n_evalue = len(df3)

        df3["accession_clean"] = df3["accession"].astype(str).str.split(".").str[0]
        is_excluded = df3["accession_clean"].isin(excl_clean) | df3["accession"].isin(exclusion_set)
        df4 = df3[~is_excluded].drop(columns=["accession_clean"]).copy()
        n_novel = len(df4)

        log(f"  {fam}: total={n_total} -> is_included={n_included} -> has_{OPSIN_PFAM}={n_opsin} "
            f"-> evalue<={EVALUE_CUTOFF}={n_evalue} -> novel(excl.known)={n_novel}")
        funnel.append(dict(family=fam, n_total_hits=n_total, n_included=n_included,
                            n_has_opsin_domain=n_opsin, n_evalue_pass=n_evalue,
                            n_novel_candidates=n_novel))
        survivors[fam] = df4
    funnel_df = pd.DataFrame(funnel)
    funnel_df.to_csv(f"{CAND}/filter_funnel.tsv", sep="\t", index=False)
    log("  funnel summary:\n" + funnel_df.to_string(index=False))
    return survivors


# ---------------------------------------------------------------------------
# Phase 3: batch-fetch UniProt sequence + length for surviving candidates, with
# individual inactive-entry resolution (MERGED/DEMERGED -> follow to replacement;
# DELETED -> permanently gone, logged and excluded, never fabricated)
# ---------------------------------------------------------------------------
def uniprot_batch_fetch(accs, batch_size=100, retries=3):
    """Returns dict acc -> sequence string for accessions resolvable via the batch
    endpoint (currently-active entries only; the batch endpoint silently omits
    inactive accessions rather than erroring)."""
    seqs = {}
    accs = sorted(set(accs))
    for i in range(0, len(accs), batch_size):
        batch = accs[i:i + batch_size]
        cache_key = f"{UNIPROT_BATCH_CACHE_DIR}/batch_{i:06d}_{len(batch)}.fasta"
        if os.path.exists(cache_key):
            txt = open(cache_key).read()
        else:
            query = ",".join(batch)
            url = f"https://rest.uniprot.org/uniprotkb/accessions?accessions={query}&format=fasta"
            txt = None
            for attempt in range(retries):
                try:
                    req = urllib.request.Request(url, headers={"Accept": "text/plain"})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        txt = r.read().decode()
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        log(f"    batch fetch failed at offset {i}: {e}")
                        txt = ""
                    else:
                        time.sleep(2)
            open(cache_key, "w").write(txt or "")
            time.sleep(0.3)
        acc_cur, seq_parts = None, []
        for line in (txt or "").split("\n"):
            if line.startswith(">"):
                if acc_cur is not None:
                    seqs[acc_cur] = "".join(seq_parts)
                parts = line[1:].split("|")
                acc_cur = parts[1] if len(parts) >= 2 else parts[0].split()[0]
                seq_parts = []
            elif line.strip():
                seq_parts.append(line.strip())
        if acc_cur is not None:
            seqs[acc_cur] = "".join(seq_parts)
    log(f"    batch endpoint: requested={len(accs)} resolved_active={len(seqs)}")
    return seqs


def uniprot_json_lookup(acc, retries=2):
    cache_f = f"{CACHE}/uniprot_inactive_lookup/{acc}.json"
    os.makedirs(f"{CACHE}/uniprot_inactive_lookup", exist_ok=True)
    if os.path.exists(cache_f):
        return json.load(open(cache_f))
    url = f"https://rest.uniprot.org/uniprotkb/{acc}.json"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode())
            json.dump(d, open(cache_f, "w"))
            return d
        except Exception as e:
            if attempt == retries - 1:
                return {"error": str(e)}
            time.sleep(1)


def resolve_inactive_accessions(missing_accs, max_workers=12):
    """For accessions not resolved by the batch endpoint, look up each individually
    to classify: Active (batch endpoint false-negative), MERGED/DEMERGED (follow to
    replacement accession(s)), or DELETED (permanently gone, no replacement)."""
    from concurrent.futures import ThreadPoolExecutor
    log(f"  resolving {len(missing_accs)} missing accessions individually "
        f"(classify active/merged/demerged/deleted)...")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = dict(zip(missing_accs, ex.map(uniprot_json_lookup, missing_accs)))

    resolution_rows = []
    replacement_targets = set()
    for acc, d in results.items():
        et = d.get("entryType")
        if et and et != "Inactive":
            resolution_rows.append(dict(original_accession=acc, resolution="active_direct_json",
                                         replacement_accessions=acc, note="resolved via individual JSON lookup"))
            replacement_targets.add(acc)
        elif et == "Inactive":
            ir = d.get("inactiveReason", {}) or {}
            reason = ir.get("inactiveReasonType")
            targets = ir.get("mergeDemergeTo") or []
            if reason in ("MERGED", "DEMERGED") and len(targets) == 1:
                resolution_rows.append(dict(original_accession=acc, resolution=f"{reason.lower()}_single_target",
                                             replacement_accessions=targets[0], note=""))
                replacement_targets.add(targets[0])
            elif reason in ("MERGED", "DEMERGED") and len(targets) > 1:
                resolution_rows.append(dict(original_accession=acc, resolution=f"{reason.lower()}_ambiguous_multi_target",
                                             replacement_accessions=";".join(targets),
                                             note="ambiguous -- not auto-resolved"))
            else:
                resolution_rows.append(dict(original_accession=acc, resolution="deleted_no_replacement",
                                             replacement_accessions="",
                                             note=ir.get("deletedReason", reason or "")))
        else:
            resolution_rows.append(dict(original_accession=acc, resolution="lookup_error",
                                         replacement_accessions="", note=str(d)[:200]))
    res_df = pd.DataFrame(resolution_rows)
    log("  resolution breakdown:\n" + res_df["resolution"].value_counts().to_string())
    return res_df, replacement_targets


def phase3_fetch_sequences(survivors):
    log("PHASE 3: batch-fetching UniProt sequences for surviving candidates")
    total_unique = set()
    for fam in FAMS:
        total_unique |= set(survivors[fam]["accession"].dropna())
    log(f"  total unique accessions to fetch across all families: {len(total_unique)}")

    seqs = uniprot_batch_fetch(total_unique)
    missing = sorted(total_unique - set(seqs))
    log(f"  active via batch endpoint: {len(seqs)}  missing (needs individual lookup): {len(missing)}")

    acc_to_replacement = {}
    if missing:
        res_df, replacement_targets = resolve_inactive_accessions(missing)
        res_df.to_csv(f"{CAND}/accession_resolution_log.tsv", sep="\t", index=False)
        new_targets = replacement_targets - set(seqs)
        if new_targets:
            log(f"  fetching sequences for {len(new_targets)} merge/demerge replacement accessions...")
            seqs.update(uniprot_batch_fetch(new_targets))
        for _, row in res_df.iterrows():
            if row["resolution"] in ("active_direct_json", "merged_single_target", "demerged_single_target"):
                acc_to_replacement[row["original_accession"]] = row["replacement_accessions"]

    n_resolved_total = sum(1 for fam in FAMS for a in survivors[fam]["accession"].dropna()
                            if a in seqs or acc_to_replacement.get(a) in seqs)
    log(f"  TOTAL resolved (direct + merge/demerge-followed): accessions with a usable sequence")

    def get_seq_for(acc):
        if acc in seqs:
            return seqs[acc]
        repl = acc_to_replacement.get(acc)
        if repl and repl in seqs:
            return seqs[repl]
        return None

    for fam in FAMS:
        survivors[fam]["resolved_accession"] = survivors[fam]["accession"].map(
            lambda a: a if a in seqs else acc_to_replacement.get(a, None))
        survivors[fam]["seq_length"] = survivors[fam]["accession"].map(
            lambda a: len(get_seq_for(a)) if get_seq_for(a) else np.nan)
        survivors[fam]["seq_fetched"] = survivors[fam]["accession"].map(lambda a: get_seq_for(a) is not None)
        n_pass = int(survivors[fam]["seq_fetched"].sum())
        log(f"  {fam}: {n_pass}/{len(survivors[fam])} candidates have a usable current sequence")

    # build final acc(original)->sequence map for downstream use (hmmalign etc. key on original accession)
    seqs_by_original = {}
    for fam in FAMS:
        for _, row in survivors[fam].iterrows():
            s = get_seq_for(row["accession"])
            if s:
                seqs_by_original[row["accession"]] = s
    return survivors, seqs_by_original


# ---------------------------------------------------------------------------
# Phase 4: empirical length filter (derived from each family's seed sequences)
# ---------------------------------------------------------------------------
def seed_length_range(fam, tol_lo=0.6, tol_hi=1.5):
    faa = f"{BASE}/seeds/fasta/{fam}.faa"
    lens = [len(r.seq) for r in SeqIO.parse(faa, "fasta")]
    lo = int(np.floor(tol_lo * min(lens)))
    hi = int(np.ceil(tol_hi * max(lens)))
    return min(lens), max(lens), lo, hi


def phase4_length_filter(survivors):
    log("PHASE 4: empirical per-family length filter (seed-range x [0.6, 1.5] tolerance)")
    length_rules = []
    post_length = {}
    for fam in FAMS:
        seed_min, seed_max, lo, hi = seed_length_range(fam)
        length_rules.append(dict(family=fam, seed_n_min=seed_min, seed_n_max=seed_max,
                                  filter_lo=lo, filter_hi=hi))
        df = survivors[fam]
        df_has_len = df[df["seq_fetched"] == True].copy()
        df_pass = df_has_len[(df_has_len["seq_length"] >= lo) & (df_has_len["seq_length"] <= hi)].copy()
        log(f"  {fam}: seed_len=[{seed_min},{seed_max}] -> filter=[{lo},{hi}]  "
            f"candidates_with_seq={len(df_has_len)} pass_length={len(df_pass)}")
        post_length[fam] = df_pass
    pd.DataFrame(length_rules).to_csv(f"{CAND}/length_filter_rules.tsv", sep="\t", index=False)
    return post_length


# ---------------------------------------------------------------------------
# Phase 5: hmmalign --mapali, re-derive retinal-K column in the merged alignment,
# check each candidate for K at that column (+/- 2 column tolerance)
# ---------------------------------------------------------------------------
def phase5_hmmalign_confirm(post_length, seqs):
    log("PHASE 5: hmmalign --mapali retinal-Schiff-base Lys confirmation")
    final = {}
    retinalK_summary = []
    for fam in FAMS:
        df = post_length[fam]
        if len(df) == 0:
            log(f"  {fam}: 0 candidates after length filter, skipping hmmalign")
            final[fam] = df.assign(has_retinalK=pd.Series(dtype=bool))
            continue
        cand_fasta = f"{CAND}/{fam}_candidates_prealign.fasta"
        with open(cand_fasta, "w") as fh:
            for acc in df["accession"]:
                fh.write(f">{acc}\n{seqs[acc]}\n")

        hmm = f"{BASE}/seeds/fasta/{fam}.hmm"
        seed_aln = f"{BASE}/seeds/fasta/{fam}.aln.fasta"
        out_sto = f"{CAND}/{fam}_mapali.sto"
        cmd = [HMMALIGN_BIN, "--amino", "--mapali", seed_aln, "--trim", "-o", out_sto, hmm, cand_fasta]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"  {fam}: hmmalign FAILED: {r.stderr[:500]}")
            final[fam] = df.assign(has_retinalK=np.nan)
            continue

        aln = AlignIO.read(out_sto, "stockholm")
        seed_ids = set(r2.id for r2 in SeqIO.parse(seed_aln, "fasta"))
        seed_rows = [r2 for r2 in aln if r2.id in seed_ids]
        cand_rows = [r2 for r2 in aln if r2.id not in seed_ids]
        log(f"  {fam}: mapali n_seed_rows={len(seed_rows)} n_cand_rows={len(cand_rows)} "
            f"aln_len={aln.get_alignment_length()}")

        arr_seed = np.array([list(str(r2.seq)) for r2 in seed_rows])
        k_freq = (arr_seed == "K").mean(axis=0)
        retinalK_col = int(np.argmax(k_freq))
        retinalK_frac = float(k_freq[retinalK_col])
        retinalK_summary.append(dict(family=fam, retinalK_col_in_mapali=retinalK_col,
                                      retinalK_frac_in_seeds=round(retinalK_frac, 3),
                                      n_seed_rows=len(seed_rows), n_cand_rows=len(cand_rows),
                                      mapali_aln_len=aln.get_alignment_length()))

        tol = 2
        has_k, col_used = [], []
        for r2 in cand_rows:
            seq = str(r2.seq)
            window = seq[max(0, retinalK_col - tol): retinalK_col + tol + 1]
            has_k.append("K" in window)
            col_used.append(window)
        cand_result = pd.DataFrame({"accession": [r2.id for r2 in cand_rows],
                                     "has_retinalK": has_k, "mapali_window": col_used})
        df_merged = df.merge(cand_result, on="accession", how="left")
        final[fam] = df_merged
        n_pass = int(df_merged["has_retinalK"].sum())
        log(f"  {fam}: {n_pass}/{len(df_merged)} candidates retain K at retinal column (+/-{tol})")

    pd.DataFrame(retinalK_summary).to_csv(f"{CAND}/retinalK_mapali_columns.tsv", sep="\t", index=False)
    return final


# ---------------------------------------------------------------------------
# Phase 6: assemble final tables
# ---------------------------------------------------------------------------
def phase6_assemble(final):
    log("PHASE 6: assembling final candidate tables")
    all_rows, counts = [], []
    for fam in FAMS:
        df = final[fam]
        if len(df) == 0:
            counts.append(dict(family=fam, n_prefilter_novel=0, n_length_pass=0, n_retinalK_pass=0))
            continue
        df = df.copy()
        df["family"] = fam
        all_rows.append(df)
        n_retinalK_pass = int(df["has_retinalK"].sum()) if "has_retinalK" in df else 0
        counts.append(dict(family=fam, n_prefilter_novel=len(df), n_length_pass=len(df),
                            n_retinalK_pass=n_retinalK_pass))
    full = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    counts_df = pd.DataFrame(counts)
    full.to_csv(f"{CAND}/novel_family_candidates_full.tsv", sep="\t", index=False)
    counts_df.to_csv(f"{CAND}/novel_family_candidate_counts.tsv", sep="\t", index=False)
    log("Final counts:\n" + counts_df.to_string(index=False))

    final_pass = full[full.get("has_retinalK", False) == True] if len(full) else full
    final_pass.to_csv(f"{CAND}/novel_family_candidates_retinalK_pass.tsv", sep="\t", index=False)

    samples = []
    for fam in FAMS:
        sub = final_pass[final_pass["family"] == fam].sort_values("evalue").head(10)
        samples.append(sub)
    sample_df = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame()
    sample_df.to_csv(f"{CAND}/novel_family_candidates_sample10_per_family.tsv", sep="\t", index=False)
    log(f"Sample table rows: {len(sample_df)}")
    return full, counts_df, final_pass, sample_df


if __name__ == "__main__":
    corpus_accs, ext_val_accs, exclusion_set = phase0_exclusion_sets()
    all_hits = phase1_fetch_hits()
    survivors = phase2_filter(all_hits, exclusion_set)
    survivors, seqs = phase3_fetch_sequences(survivors)
    post_length = phase4_length_filter(survivors)
    final = phase5_hmmalign_confirm(post_length, seqs)
    full, counts_df, final_pass, sample_df = phase6_assemble(final)
    log("DONE.")
