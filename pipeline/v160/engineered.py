"""Stage 1 (R-M engineered constructs): detect engineered / construct-derived sequences in the v1.5.0 corpus.

Signals (each recorded separately; no single signal is decisive):
  S1 his_tag        : >=6 consecutive His within 15 aa of either terminus (expression tag), or LEHHHHHH / GSHHHHHH motif
  S2 pdb_only       : UniProt entry has a PDB cross-reference but no EMBL/GenBank, RefSeq or Ensembl-type nucleotide xref
                      (sequence entered from a structure deposit, i.e. a crystallised construct)
  S3 named_mutation : protein name or UniProt description contains a point-mutation token (e.g. T74D, C110A)
  S4 near_identical : >=98% identity over >=90% of both sequences to another corpus record that is E1 or reviewed or
                      longer-established (earlier UniProt creation), with 1-5 substitutions -> candidate point mutant
A record is proposed as is_engineered=1 when S1 or S2 or S3 holds AND a wild-type partner can be named (S4 or
literature), or when S1 and S2 both hold. S4 alone is reported as 'possible_variant' (natural strain variants are
common) and is NOT proposed for exclusion.
"""
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_W160 = _os.environ.get("MRDB_V160_WORK", _os.path.join(_REPO, "work", "v160_stage1"))  # Stage-1 scratch dir
import json, os, re, sqlite3, subprocess, time, urllib.request
import pandas as pd

DB = _os.path.join(_REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
OUT = _os.path.join(_W160, "stage1/out")
CACHE = _os.path.join(_W160, "stage1/cache")
MM = _os.environ.get("MMSEQS", "mmseqs")
os.makedirs(OUT, exist_ok=True); os.makedirs(CACHE, exist_ok=True)

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
p = pd.read_sql("select source_acc, mrdb_acc, protein_name, organism, length, sequence, reviewed, pdb from protein", c)
vm = pd.read_sql("select source_acc, membership_status from v_master", c)
fe = pd.read_sql("select source_acc, evidence_level, func_class from function_evidence", c)
p = p.merge(vm, on="source_acc", how="left").merge(fe, on="source_acc", how="left")

# ---------- S1 his tag ----------
def his_tag(s):
    for m in re.finditer(r"H{6,}", s):
        if m.start() < 15 or len(s) - m.end() < 15:
            return f"{m.group()}@{m.start()+1}-{m.end()}"
    if re.search(r"(LE|GS)HHHHHH", s):
        return "LE/GS-HHHHHH"
    return ""
p["S1_his_tag"] = p.sequence.map(his_tag)

# ---------- S2 UniProt xrefs (cached) ----------
cache_f = f"{CACHE}/uniprot_xrefs.json"
xref = json.load(open(cache_f)) if os.path.exists(cache_f) else {}
todo = [a for a in p.source_acc if a not in xref]
fields = "accession,xref_embl,xref_refseq,xref_pdb,date_created,cc_function,ft_mutagen,protein_name"
for i in range(0, len(todo), 100):
    chunk = todo[i:i + 100]
    q = "+OR+".join(f"accession:{a}" for a in chunk)
    url = f"https://rest.uniprot.org/uniprotkb/search?query={q}&fields={fields}&format=tsv&size=500"
    for attempt in range(4):
        try:
            txt = urllib.request.urlopen(url, timeout=60).read().decode()
            break
        except Exception as e:  # noqa
            time.sleep(3 * (attempt + 1)); txt = None
    if txt is None:
        continue
    lines = txt.rstrip("\n").split("\n")
    hdr = lines[0].split("\t")
    for ln in lines[1:]:
        d = dict(zip(hdr, ln.split("\t")))
        xref[d["Entry"]] = d
    json.dump(xref, open(cache_f, "w"))
print("uniprot xrefs cached:", len(xref), "of", len(p))

def s2(a):
    d = xref.get(a)
    if d is None:
        return "not_retrieved"
    has_nt = bool(d.get("EMBL", "").strip()) or bool(d.get("RefSeq", "").strip())
    has_pdb = bool(d.get("PDB", "").strip())
    return "pdb_only" if (has_pdb and not has_nt) else ""
p["S2_pdb_only"] = p.source_acc.map(s2)
p["uniprot_created"] = p.source_acc.map(lambda a: xref.get(a, {}).get("Date of creation", ""))
p["uniprot_name"] = p.source_acc.map(lambda a: xref.get(a, {}).get("Protein names", ""))

# ---------- S3 named mutation ----------
MUT = re.compile(r"(?<![A-Za-z0-9])([ACDEFGHIKLMNPQRSTVWY])(\d{2,3})([ACDEFGHIKLMNPQRSTVWY])(?![a-z0-9])")
def s3(r):
    txt = f"{r.protein_name} {r.uniprot_name}"
    hits = [m.group(0) for m in MUT.finditer(txt)]
    return ";".join(sorted(set(hits)))
p["S3_named_mutation"] = p.apply(s3, axis=1)

# ---------- S4 near-identical partner ----------
fa = f"{CACHE}/corpus.faa"
with open(fa, "w") as fh:
    for r in p.itertuples():
        fh.write(f">{r.source_acc}\n{r.sequence}\n")
res = f"{CACHE}/nearid.m8"
if not os.path.exists(res):
    subprocess.run([MM, "easy-search", fa, fa, res, f"{CACHE}/tmp", "--min-seq-id", "0.98", "-c", "0.9", "--cov-mode", "0",
                    "--format-output", "query,target,fident,alnlen,mismatch,gapopen,qlen,tlen", "--threads", "4", "-v", "1"],
                   check=True)
m8 = pd.read_csv(res, sep="\t", names=["q", "t", "fident", "alnlen", "mm", "gaps", "qlen", "tlen"])
m8 = m8[(m8.q != m8.t) & (m8.mm.between(0, 5))]  # include 0-mismatch (tag-only / extension-only) pairs
info = p.set_index("source_acc")
def partner_rank(a):
    r = info.loc[a]
    # a record carrying its OWN named mutation (e.g. "C110A" in its own protein name) must never be
    # preferred as someone else's wild-type partner, regardless of evidence level.
    return (r.S3_named_mutation == "", not r.S1_his_tag, r.evidence_level == "E1",
            r.reviewed in (1, "1", "reviewed", True), r.S2_pdb_only == "",
            str(r.uniprot_created) and -int(str(r.uniprot_created).replace("-", "") or 0))
best = {}
for q, g in m8.groupby("q"):
    g = g.assign(rank=g.t.map(partner_rank)).sort_values("rank", ascending=False)
    t = g.iloc[0]
    best[q] = (t.t, round(t.fident * 100, 1), int(t.mm), int(t.gaps))

def mutations(a, b):
    """substitutions of a relative to b when lengths allow a gapless comparison after trimming tags."""
    sa, sb = info.loc[a].sequence, info.loc[b].sequence
    # gapless offset search (constructs often differ only by N/C-terminal extensions)
    bestoff, bestmm = None, None
    for off in range(-25, 26):
        pairs = [(i, sa[i], sb[i + off]) for i in range(len(sa)) if 0 <= i + off < len(sb)]
        if len(pairs) < 0.9 * min(len(sa), len(sb)):
            continue
        mm = [(i, x, y) for i, x, y in pairs if x != y]
        if bestmm is None or len(mm) < len(bestmm):
            bestoff, bestmm = off, mm
    if bestmm is None or len(bestmm) > 5:
        return ""
    return ";".join(f"{y}{i + bestoff + 1}{x}" for i, x, y in bestmm)  # wt-res, wt-position, construct-res

p["S4_partner"] = p.source_acc.map(lambda a: best.get(a, ("",))[0])
p["S4_identity"] = p.source_acc.map(lambda a: best.get(a, ("", ""))[1])
p["S4_substitutions_vs_partner"] = [mutations(a, best[a][0]) if a in best else "" for a in p.source_acc]

# S2 (pdb_only) alone is NOT a construct signal -- many legitimately wild-type characterized proteins are
# UniProt entries created straight from a PDB SEQRES/paper with no indexed nucleotide accession. Only S1
# (expression/purification tag) or S3 (a point-mutation token in the record's own name/description) count
# as direct evidence that THIS record (not its partner) is the lab-manipulated one.
strong = (p.S1_his_tag != "") | (p.S3_named_mutation != "")
p["proposal"] = "none"
p.loc[(p.S4_partner != "") & ~strong, "proposal"] = "possible_natural_variant_no_action"
p.loc[strong & (p.S4_partner != ""), "proposal"] = "engineered_with_wild_type"
p.loc[strong & (p.S4_partner == ""), "proposal"] = "construct_signal_no_partner_review"
# a partner that is itself strong (own tag/mutation) is a weak wild-type candidate -> downgrade for literature review
weak_partner = strong & (p.S4_partner != "") & p.S4_partner.isin(p.index[strong] if False else p.loc[strong, "source_acc"])
p.loc[weak_partner, "proposal"] = "engineered_partner_also_flagged_needs_literature"
cand = p[p.proposal != "none"].copy()
cand["wild_type_acc_proposed"] = cand.S4_partner.where(cand.proposal == "engineered_with_wild_type", "")
cols = ["proposal", "source_acc", "mrdb_acc", "protein_name", "organism", "length", "membership_status", "evidence_level",
        "func_class", "reviewed", "uniprot_created", "S1_his_tag", "S2_pdb_only", "S3_named_mutation", "S4_partner",
        "S4_identity", "S4_substitutions_vs_partner", "wild_type_acc_proposed", "pdb"]
cand[cols].sort_values(["proposal", "source_acc"]).to_csv(f"{OUT}/engineered_candidates.tsv", sep="\t", index=False)
print(cand.proposal.value_counts().to_string())
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 40)
print(cand[cand.proposal != "possible_natural_variant_no_action"][cols[:4] + cols[7:8] + cols[11:18]].to_string())
