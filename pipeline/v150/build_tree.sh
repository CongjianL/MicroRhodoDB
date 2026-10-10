#!/usr/bin/env bash
# WP4: MR_RT_003 reference tree build.
#   domain-trim -> MAFFT L-INS-i -> ClipKIT kpic-smart-gap -> IQ-TREE2 ModelFinder (run1) -> 2 replicate runs
# Each completed stage is checkpointed to $CK (S3-backed shared workspace).
set -euo pipefail
export PATH=/workspace/.conda/mrdb/bin:$PATH
W=${1:-/workspace/v150/tree}
CK=${2:-/mnt/shared-workspace/v150/tree}
HMM=/workspace/v150/hmm
SRC=/workspace/MicroRhodoDB/pipeline/v150
mkdir -p "$CK"; cd "$W"

if [ ! -s MR_RT_003.trim.faa ]; then
  python $SRC/domain_trim.py tips.faa $HMM/PF01036.25.hmm $HMM/PF18761.8.hmm tips.dom.faa tips.dom_coords.tsv 15
  mafft --localpair --maxiterate 1000 --thread 16 --amino tips.dom.faa > MR_RT_003.msa.faa 2> mafft.log
  clipkit MR_RT_003.msa.faa -m kpic-smart-gap -o MR_RT_003.trim.faa -l > clipkit.log 2>&1
  cp tips.faa tips.tsv tips.dom.faa tips.dom_coords.tsv MR_RT_003.msa.faa MR_RT_003.trim.faa clipkit.log "$CK"/
  echo "[ck] msa done"
fi

if [ ! -s run1.treefile ]; then
  iqtree2 -s MR_RT_003.trim.faa -m MFP -mset LG,WAG,JTT,Q.pfam -B 1000 -alrt 1000 -T 16 -seed 1501 \
          --prefix run1 -quiet
  cp run1.* "$CK"/
  echo "[ck] run1 done"
fi
BEST=$(grep -m1 "Best-fit model:" run1.log | sed 's/.*Best-fit model: //; s/ chosen.*//')
[ -n "$BEST" ] || { echo "could not parse best model" >&2; exit 1; }
echo "best model: $BEST"
# replicate runs 2 and 3 in parallel (8 threads each), within this tracked job
rep() { r=$1
  if [ ! -s run$r.treefile ]; then
    iqtree2 -s MR_RT_003.trim.faa -m "$BEST" -B 1000 -alrt 1000 -T 8 -seed $((1500 + r)) --prefix run$r -quiet
    cp run$r.* "$CK"/
    echo "[ck] run$r done"
  fi; }
rep 2 & P2=$!
rep 3 & P3=$!
wait $P2; wait $P3
# pairwise RF distances between the 3 ML trees
cat run1.treefile run2.treefile run3.treefile > ml3.trees
iqtree2 -rf_all ml3.trees --prefix ml3 -quiet
cp ml3.* "$CK"/
grep -h "BEST SCORE\|Log-likelihood of the tree" run1.iqtree run2.iqtree run3.iqtree || true
echo "ALL DONE"
