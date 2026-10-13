#!/usr/bin/env python
"""Independent denominator / transition / spot-check validation of the PR-7c.1a production outputs.

Usage: python denominators3.py PROD_DIR     (or env VAL_PROD)
PROD_DIR: habitat_record_availability.tsv, habitat_coverage_summary.tsv, habitat_evidence.tsv,
          pr7c1_39f5cad_record_availability.tsv
All numbers are recomputed from the production record table (and, for spot checks, the
production evidence table) with code written independently of production.
"""
import os
import sys
from collections import Counter

import pandas as pd

PR = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VAL_PROD", ".")
PHYS = ["env_broad_scale", "env_local_scale", "env_medium", "isolation_source"]
ROLES5 = PHYS + ["host"]


def read(name):
    return pd.read_csv(os.path.join(PR, name), sep="\t", dtype=str, keep_default_na=False, na_filter=False)


def flagset(s):
    return set(x for x in s.split(";") if x)


def main():
    r = read("habitat_record_availability.tsv")
    old = read("pr7c1_39f5cad_record_availability.tsv")
    summ = read("habitat_coverage_summary.tsv")
    ev = read("habitat_evidence.tsv")
    N = len(r)
    print("records: %d (39f5cad: %d)" % (N, len(old)))

    phys_any = (r[[p + "_original" for p in PHYS]] != "").any(axis=1)
    host_any = r["host_original"] != ""
    fl = r["flags"].apply(flagset)
    exp = {}  # metric -> (numerator, denominator)
    for g in ["DIRECT_SAMPLE", "VERIFIED_ISOLATE", "ORGANISM_CONTEXT_ONLY", "AMBIGUOUS", "NOT_REPORTED",
              "LOOKUP_FAILED", "NOT_SEARCHED"]:
        exp["grade:" + g] = (int((r["primary_grade"] == g).sum()), N)
    exp["usable_habitat_any_source"] = (int((r["has_usable_habitat"] == "1").sum()), N)
    for p in PHYS:
        exp["usable_field:" + p] = (int((r[p + "_original"] != "").sum()), N)
    exp["host_field:host"] = (int(host_any.sum()), N)
    for s in ["REPORTED", "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED"]:
        exp["host_association:" + s] = (int((r["host_association_status"] == s).sum()), N)
    exp["has_host_association"] = (int((r["has_host_association"] == "1").sum()), N)
    exp["host_association_only"] = (int((host_any & ~phys_any).sum()), N)
    # ASSUMPTION (metric not defined in detail by the dictionary): physical usable habitat
    # (has_usable_habitat = 1) and has_host_association = 1. The alternative (any usable physical value,
    # including physical-AMBIGUOUS records) is printed for information.
    exp["physical_habitat_and_host_association"] = (
        int(((r["has_usable_habitat"] == "1") & (r["has_host_association"] == "1")).sum()), N)
    alt_phys_host = int((phys_any & host_any).sum())
    namb = int((r["primary_grade"] == "AMBIGUOUS").sum())
    nhamb = int((r["host_association_status"] == "AMBIGUOUS").sum())
    nnr = int((r["primary_grade"] == "NOT_REPORTED").sum())
    for c in ["FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE", "DISTINCT_ACROSS_SAMPLES",
              "LITERATURE_VS_DATABASE"]:
        exp["ambiguity_class:" + c] = (int((r["ambiguity_class"] == c).sum()), namb)
        exp["host_ambiguity_class:" + c] = (int((r["host_ambiguity_class"] == c).sum()), nhamb)
    for s in sorted(set(r["not_reported_scope"]) - {""}):
        exp["not_reported_scope:" + s] = (int((r["not_reported_scope"] == s).sum()), nnr)
    tr = Counter(zip(r["pr7c1_grade"], r["primary_grade"]))
    for (a, b), n in tr.items():
        exp["pr7c1_grade_transition:%s->%s" % (a, b)] = (n, N)
    allflags = Counter(f for s in fl for f in s)
    for f, n in allflags.items():
        exp["flag:" + f] = (n, N)

    s = summ[(summ["unit"] == "source_record") & (summ["stratum_type"] == "all")]
    sm = {m: (int(a), int(b), p) for m, a, b, p in zip(s["metric"], s["numerator"], s["denominator"], s["percent"])}
    prefixes = ("grade:", "usable_habitat_any_source", "usable_field:", "host_field:", "host_association:",
                "has_host_association", "host_association_only", "physical_habitat_and_host_association",
                "ambiguity_class:", "host_ambiguity_class:", "not_reported_scope:", "pr7c1_grade_transition:",
                "flag:")
    in_scope = sorted(m for m in sm if m.startswith(prefixes) and m != "usable_habitat_any_source_of_searched")
    print("=" * 100)
    print("A. Coverage summary (unit=source_record, stratum_type=all): numerator and denominator")
    nok = 0
    bad = []
    for m in in_scope:
        got = sm[m]
        e = exp.get(m, (0, None))
        if e[1] is None:
            # metric absent from the independent computation (zero occurrences); denominator by metric family
            den = namb if m.startswith("ambiguity_class:") else nhamb if m.startswith("host_ambiguity_class:") \
                else nnr if m.startswith("not_reported_scope:") else N
            e = (0, den)
        pct = "%.2f" % (100.0 * got[0] / got[1]) if got[1] else "0.00"
        ok = (got[0], got[1]) == e and pct == got[2]
        nok += ok
        if not ok:
            bad.append(m)
        print("  %-70s prod %5d/%5d (%s%%)  indep %5d/%5d  %s" % (m, got[0], got[1], got[2], e[0], e[1],
                                                                   "OK" if ok else "MISMATCH"))
    print("in-scope summary rows: %d; matching numerator+denominator+percent: %d; mismatches: %s"
          % (len(in_scope), nok, bad))
    missing = sorted(m for m in exp if m.startswith(prefixes) and m not in sm and exp[m][0] > 0)
    print("independently non-zero metrics absent from the summary:", missing)
    print("info: alternative physical_habitat_and_host_association (any usable physical value AND host) = %d"
          % alt_phys_host)
    print("info: usable_habitat_any_source_of_searched prod=%s" % (sm.get("usable_habitat_any_source_of_searched"),))

    # ---------------------------------------------------------------------------------
    print("=" * 100)
    print("B. 39f5cad (PR-7c.1) record table vs current record table")
    o = old.set_index("source_acc")
    n = r.set_index("source_acc").loc[o.index]
    print("pr7c1_grade == 39f5cad primary_grade: %d of %d" % (int((n["pr7c1_grade"] == o["primary_grade"]).sum()),
                                                              len(o)))
    shared = [c for c in o.columns if c in n.columns]
    changed = {}
    for c in shared:
        d = n[c] != o[c]
        if d.any():
            changed[c] = list(d[d].index)
    print("columns in 39f5cad: %d; shared with current: %d; columns removed: %s" %
          (len(o.columns) + 1, len(shared) + 1, [c for c in o.columns if c not in n.columns]))
    print("new columns:", [c for c in n.columns if c not in o.columns])
    print("changed columns (records):", {c: len(v) for c, v in changed.items()})
    print("unchanged columns:", [c for c in shared if c not in changed])
    zero = {"A0ABS3TAH3", "A0ABS3TE24"}
    host_usable = n["host_original"] != ""
    gchg = set(n.index[n["primary_grade"] != o["primary_grade"]])

    # explanations per column
    def explain(c, accs):
        reasons = Counter()
        unexplained = []
        for a in accs:
            ov, nv = o.at[a, c], n.at[a, c]
            if a in zero and (c.startswith("env_") or c == "evidence_ids" or c == "flags"):
                reasons["zero_placeholder_record"] += 1
                if c == "flags":
                    if flagset(nv) - flagset(ov) != {"invalid_placeholder_value"} or flagset(ov) - flagset(nv):
                        unexplained.append(a)
                continue
            if c == "not_reported_scope":
                if ov == "database_chain_only" and nv in ("database_only_literature_not_reviewed",
                                                          "database_only_literature_inaccessible"):
                    reasons["scope_renamed:%s" % nv] += 1
                elif ov == "" and nv != "" and a in gchg:
                    reasons["new_NOT_REPORTED_after_host_separation:%s" % nv] += 1
                elif ov != "" and nv == "" and a in gchg:
                    reasons["left_NOT_REPORTED"] += 1
                else:
                    unexplained.append(a)
                continue
            if c in ("primary_grade", "db_habitat_status", "has_usable_habitat", "mapping_confidence"):
                if a in gchg and host_usable[a]:
                    reasons["host_separation (%s -> %s)" % (o.at[a, "primary_grade"], n.at[a, "primary_grade"])] += 1
                else:
                    unexplained.append(a)
                continue
            if c == "flags":
                add, rem = flagset(nv) - flagset(ov), flagset(ov) - flagset(nv)
                okset = {"host_association_only", "host_conflict", "literature_conflict",
                         "host_associated_isolation_source", "host_tissue_isolation_source_only",
                         "invalid_placeholder_value"}
                # flags whose definition depends on the physical grade/axis
                grade_dep = {"conflict", "multi_sample", "tissue_or_culture_only"}
                if add <= (okset | grade_dep) and rem <= grade_dep:
                    if rem or (add & grade_dep):
                        if a in gchg or ("conflict" in rem and n.at[a, "host_association_status"] == "AMBIGUOUS"):
                            reasons["grade/axis-dependent flag change"] += 1
                        else:
                            unexplained.append(a)
                    else:
                        reasons["new PR-7c.1a flag(s) only"] += 1
                else:
                    unexplained.append(a)
                continue
            unexplained.append(a)
        return reasons, unexplained

    for c, accs in changed.items():
        reasons, une = explain(c, accs)
        print("  %-28s changed %5d: %s; UNEXPLAINED %d %s" % (c, len(accs), dict(reasons), len(une), une[:10]))
    # flags added/removed tallies
    add_c, rem_c = Counter(), Counter()
    for a in changed.get("flags", []):
        for f in flagset(n.at[a, "flags"]) - flagset(o.at[a, "flags"]):
            add_c[f] += 1
        for f in flagset(o.at[a, "flags"]) - flagset(n.at[a, "flags"]):
            rem_c[f] += 1
    print("  flags added (records):", dict(add_c))
    print("  flags removed (records):", dict(rem_c))
    if "evidence_ids" in changed:
        for a in changed["evidence_ids"]:
            print("  evidence_ids %s removed=%s added=%s" % (a, sorted(set(o.at[a, "evidence_ids"].split(";")) -
                                                                      set(n.at[a, "evidence_ids"].split(";"))),
                                                          sorted(set(n.at[a, "evidence_ids"].split(";")) -
                                                                 set(o.at[a, "evidence_ids"].split(";")))))
    for c in [x for x in changed if x.startswith("env_")]:
        for a in changed[c]:
            print("  %s %s: %r -> %r" % (c, a, o.at[a, c], n.at[a, c]))

    # ---------------------------------------------------------------------------------
    print("=" * 100)
    print("C. Spot checks")
    hao = r[host_any & ~phys_any]
    oldg = o["primary_grade"]
    print("(a) usable host and no usable physical value: %d; flag host_association_only: %d; "
          "39f5cad grade among them: %s" % (len(hao), int(fl.apply(lambda s: "host_association_only" in s).sum()),
                                            dict(Counter(oldg.loc[hao["source_acc"]]))))
    print("    current grade among them: %s" % dict(Counter(hao["primary_grade"])))
    for a in sorted(zero):
        row = r[r["source_acc"] == a].iloc[0]
        e = ev[ev["source_acc"] == a]
        z = e[e["value_original"].str.strip() == "0"]
        print("(b) %s grade=%s pr7c1=%s isolation_source=%r env_broad/local/medium=%r/%r/%r flags_has_ipv=%s"
              % (a, row["primary_grade"], row["pr7c1_grade"], row["isolation_source_original"],
                 row["env_broad_scale_original"], row["env_local_scale_original"], row["env_medium_original"],
                 "invalid_placeholder_value" in flagset(row["flags"])))
        print("    zero items: %d, statuses %s, roles %s, sources %s; zero ids in evidence_ids: %d"
              % (len(z), dict(Counter(z["value_status"])), dict(Counter(z["role"])),
                 dict(Counter(z["evidence_source"])), sum(i in row["evidence_ids"] for i in z["evidence_id"])))
        iso = e[e["role"] == "isolation_source"]
        print("    isolation_source items:", list(zip(iso["evidence_source"], iso["value_original"],
                                                       iso["value_status"])))
    row = r[r["source_acc"] == "A0A6N7QP32"].iloc[0]
    e = ev[(ev["source_acc"] == "A0A6N7QP32") & (ev["role"] == "env_local_scale")]
    print("(c) A0A6N7QP32 env_local_scale_original=%r grade=%s pr7c1=%s; items %s; 39f5cad value %r"
          % (row["env_local_scale_original"], row["primary_grade"], row["pr7c1_grade"],
             list(zip(e["value_original"], e["value_status"])), o.at["A0A6N7QP32", "env_local_scale_original"]))
    lf = r[r["literature_status"] == "LOOKUP_FAILED"]
    litrows = ev[(ev["evidence_source"] == "literature") & ev["source_acc"].isin(lf["source_acc"])]
    print("(d) literature LOOKUP_FAILED records: %d; literature evidence rows for them: %d; grades %s; scopes %s; "
          "literature_isolate_text/organism_context_text non-empty: %d/%d; HL ids in evidence_ids: %d"
          % (len(lf), len(litrows), dict(Counter(lf["primary_grade"])), dict(Counter(lf["not_reported_scope"])),
             int((lf["literature_isolate_text"] != "").sum()), int((lf["organism_context_text"] != "").sum()),
             int(lf["evidence_ids"].str.contains("HL").sum())))
    print("    39f5cad scope for these:", dict(Counter(o.loc[lf["source_acc"], "not_reported_scope"])))
    print("(e) ambiguity_class among physical AMBIGUOUS (n=%d): %s" %
          (namb, dict(Counter(r.loc[r["primary_grade"] == "AMBIGUOUS", "ambiguity_class"]))))
    print("    host_ambiguity_class among host AMBIGUOUS (n=%d): %s" %
          (nhamb, dict(Counter(r.loc[r["host_association_status"] == "AMBIGUOUS", "host_ambiguity_class"]))))
    usable_ev = ev[ev["value_status"] == "usable"]

    def show(acc, roles):
        row = r[r["source_acc"] == acc].iloc[0]
        print("      %s  conflict_kind=%s  conflict_scope=%s" % (acc, row["conflict_kind"], row["conflict_scope"]))
        for role in roles:
            u = usable_ev[(usable_ev["source_acc"] == acc) & (usable_ev["role"] == role)]
            for _, x in u.iterrows():
                print("        %-17s %-21s %-14s %r" % (role, x["evidence_source"], x["entity_accession"],
                                                       x["value_original"][:110]))
        if row["ambiguity_class"] == "LITERATURE_VS_DATABASE":
            lr = ev[(ev["source_acc"] == acc) & (ev["evidence_source"] == "literature")]
            for _, x in lr.iterrows():
                print("        literature %s: %r" % (x["role"], x["value_original"][:200]))
    for col, axis_roles in (("ambiguity_class", PHYS), ("host_ambiguity_class", ["host"])):
        for c in ["FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE", "DISTINCT_ACROSS_SAMPLES",
                  "LITERATURE_VS_DATABASE"]:
            accs = sorted(r.loc[r[col] == c, "source_acc"])
            if not accs:
                continue
            print("    %s = %s (n=%d), examples:" % (col, c, len(accs)))
            for acc in accs[:3]:
                row = r[r["source_acc"] == acc].iloc[0]
                roles = [x for x in row["conflict_roles"].split(";") if x in axis_roles] or axis_roles
                show(acc, roles)


if __name__ == "__main__":
    main()
