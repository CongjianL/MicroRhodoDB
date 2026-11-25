#!/usr/bin/env bash
# Assemble releases/v1.6.2/ from the immutable v1.6.1 release and curation/v162 (run from the repository root, in the
# pinned environment). Afterwards `snakemake -c 1 all_v162` rebuilds v1.6.2 independently and checks it against the
# database assembled here.
#
#   1  regenerate the decisions and require them to equal curation/v162/curation_v162_signed.tsv
#   2  build the database, export the tables, rerun the construction-review checks on it
#   3  copy the v1.6.1 scorer files (unchanged), write SHA256SUMS
# RELEASE_NOTES_v1.6.2.md is written by hand and must exist before step 3.
set -euo pipefail

REL=releases/v1.6.2
V161=releases/v1.6.1
WORK=work/v162_assemble
HMM=$V161/scorer/PF01036.25.hmm
test -f "$REL/RELEASE_NOTES_v1.6.2.md" || { echo "missing $REL/RELEASE_NOTES_v1.6.2.md"; exit 1; }
rm -rf "$WORK" && mkdir -p "$WORK" "$REL"/{db,meta,tables,validation}

python pipeline/v162/decisions_v162.py $V161/db/microrhododb_v1.6.1.sqlite $HMM "$WORK/decisions.tsv"
cmp "$WORK/decisions.tsv" curation/v162/curation_v162_signed.tsv

python pipeline/v162/build_v162.py --base $V161/db/microrhododb_v1.6.1.sqlite \
    --decisions curation/v162/curation_v162_signed.tsv \
    --tdefs curation/v162/table_definitions_v162.tsv --cdefs curation/v162/column_definitions_v162.tsv \
    --out-db "$REL/db/microrhododb_v1.6.2.sqlite" --dict-tsv "$WORK/data_dictionary_v162.tsv" \
    --log "$REL/meta/build_log_v162.txt"
DB=$REL/db/microrhododb_v1.6.2.sqlite

rm -f "$REL"/tables/*
python pipeline/v162/export_v162.py "$DB" "$REL/tables"

python pipeline/construction_review/helixc_motif.py "$DB" $HMM "$WORK/review"
python pipeline/construction_review/specificity_by_negative_class.py "$DB" "$WORK/review/specificity_by_negative_class.tsv"
python pipeline/construction_review/consistency_checks.py "$DB" "$WORK/review"
rm -f "$REL"/validation/*
for f in helixc_motif_summary specificity_by_negative_class placement_vs_membership e2_motif_mismatch; do
    cp "$WORK/review/$f.tsv" "$REL/validation/${f}_v162.tsv"
done

rm -rf "$REL/scorer" && cp -R $V161/scorer "$REL/scorer"

(cd "$REL" && find . -type f ! -name SHA256SUMS ! -name '.DS_Store' | LC_ALL=C sort | xargs shasum -a 256 > SHA256SUMS)
echo "assembled $REL: $(wc -l < "$REL/SHA256SUMS") files in SHA256SUMS"
