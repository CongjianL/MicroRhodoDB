#!/usr/bin/env bash
# WP4: place query sequences on MR_RT_003 with EPA-ng under the tree-inference model and two LG sensitivity models.
# usage: place_queries.sh queries.faa outdir model_tree_prefix(e.g. run1)
set -euo pipefail
export PATH=/workspace/.conda/mrdb/bin:$PATH
Q=$1; OUT=$2; PFX=${3:-run1}
T=/workspace/v150/tree; HMM=/workspace/v150/hmm; SRC=/workspace/MicroRhodoDB/pipeline/v150
mkdir -p "$OUT"; cd "$OUT"
python $SRC/domain_trim.py "$Q" $HMM/PF01036.25.hmm $HMM/PF18761.8.hmm q.dom.faa q.dom_coords.tsv 15
# remove queries identical in name to reference tips (they are placed by definition)
python - <<EOF
from Bio import SeqIO
ref={r.id for r in SeqIO.parse("$T/MR_RT_003.msa.faa","fasta")}
recs=[r for r in SeqIO.parse("q.dom.faa","fasta") if r.id not in ref]
for r in recs: r.id=r.id; r.description=""
SeqIO.write(recs,"q.nr.faa","fasta"); print("queries",len(recs))
EOF
mafft --thread 8 --addfragments q.nr.faa --keeplength "$T/MR_RT_003.msa.faa" > ref_plus_q.msa.faa 2> mafft_add.log
# apply the ClipKIT column mask of the reference alignment
python $SRC/apply_clipkit_mask.py ref_plus_q.msa.faa "$T/MR_RT_003.trim.faa.log" "$T/MR_RT_003.msa.faa" ref.trim.faa q.trim.faa
MODEL=$(grep -m1 "Best-fit model:" $T/$PFX.log | sed "s/.*Best-fit model: //; s/ chosen.*//")
CPP=/workspace/v150/epatest/modelprotein.cpp
for M in "$MODEL" "LG+G4" "LG+R4"; do
  tag=$(echo "$M" | tr '+' '_' | tr '.' '_')
  # fixed MR_RT_003 topology; branch lengths and rate parameters re-estimated under model M
  iqtree2 -s ref.trim.faa -te $T/$PFX.treefile -m "$M" -T 8 --prefix eval_$tag -quiet -redo
  RM=$(python $SRC/iqtree_to_raxml_model.py eval_$tag.iqtree $CPP)
  echo "$M -> ${RM:0:40}...${RM: -60}" > model_$tag.txt
  epa-ng --ref-msa ref.trim.faa --tree eval_$tag.treefile --query q.trim.faa --model "$RM" \
         --threads 8 --outdir . --redo --filter-max 7 > epa_$tag.log 2>&1
  mv epa_result.jplace placements_$tag.jplace
done
echo "PLACEMENT DONE"
