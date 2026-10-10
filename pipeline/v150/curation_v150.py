#!/usr/bin/env python
"""Apply the signed v1.5.0 curator spot-check decisions (curation/spotcheck_decisions_v150.tsv) to WP5/build tables.

Curation inputs (all under curation/, human-readable TSV):
  spotcheck_decisions_v150.tsv          65 signed rows: row_id, item_type, source_acc, assertion_id, publication_id,
                                        decision, field, new_value, curator_note, decided_by, decided_at
  publication_replacements_v150.tsv     verified replacement publications (ingestion curator_replacement_verified)
  assertion_link_replacements_v150.tsv  verified replacement assertion->publication links
  field_corrections_v150.tsv            per-field corrections: target_table, source_acc, assertion_id, field, new_value

Link policy (decision -> link state):
  approve / approve_with_correction -> active, counts as support
  keep_unresolvable                 -> active, NOT counted as support (verdict unresolvable)
  annotate_conflict                 -> active, NOT counted as support, link_role = conflicting_evidence
  drop_link / replace_link / downgrade_E1 -> inactive (kept for provenance, is_active = 0)
E1 policy ("replace or downgrade"): a characterized record is E1-eligible only if it is not curator-downgraded
(decision downgrade_E1 / annotate_only) and, when it has assertion links at all, at least one active link counts
as support (verdict verified / verified_with_correction).
"""
import pandas as pd

SUPPORT_VERDICTS = {"verified", "verified_with_correction"}
LINK_STATE = {"approve": (1, 1, "support"), "approve_with_correction": (1, 1, "support"),
              "keep_unresolvable": (1, 0, "unresolvable_not_counted"),
              "annotate_conflict": (1, 0, "conflicting_evidence"),
              "drop_link": (0, 0, "dropped"), "replace_link": (0, 0, "replaced"), "downgrade_E1": (0, 0, "dropped")}
E1_REMOVING = {"downgrade_E1", "annotate_only"}


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def read_decisions(fn):
    d = pd.read_csv(fn, sep="\t", dtype=str).fillna("")
    d["aid"] = d.assertion_id.map(_int)
    d["pid"] = d.publication_id.map(_int)
    return d


def apply_link_decisions(lv, dec, repl):
    """lv: pubverify assertion_link_verification; dec: read_decisions(); repl: assertion_link_replacements."""
    lv = lv.copy()
    for c, v in [("is_active", 1), ("counts_as_support", 0), ("link_role", "not_spotchecked"), ("curator_decision", ""),
                 ("curator_note", ""), ("decided_by", ""), ("decided_at", ""), ("replaces_publication_id", "")]:
        lv[c] = v
    lv["counts_as_support"] = lv.verdict.isin(SUPPORT_VERDICTS).astype(int)
    lv.loc[lv.counts_as_support == 1, "link_role"] = "support"
    key = dict(zip(zip(lv.assertion_id.astype(int), lv.publication_id.astype(int)), lv.index))
    for r in dec[dec.aid.notna() & dec.pid.notna()].itertuples():
        i = key.get((int(r.aid), int(r.pid)))
        if i is None:
            raise ValueError(f"decision row {r.row_id}: link ({r.aid},{r.pid}) not in link table")
        act, sup, role = LINK_STATE[r.decision]
        lv.loc[i, ["is_active", "counts_as_support", "link_role", "curator_decision", "curator_note", "decided_by",
                   "decided_at"]] = [act, sup, role, r.decision, r.curator_note, r.decided_by, r.decided_at]
    rp = repl.copy()
    by = dec.decided_by.iloc[0]; at = dec.decided_at.iloc[0]
    rp = rp.assign(is_active=1, counts_as_support=1, link_role="support", curator_decision="curator_replacement_verified",
                   curator_note="replacement for dropped link(s); decision rows " + rp.decision_rows.astype(str),
                   decided_by=by, decided_at=at).drop(columns=["decision_rows"])
    out = pd.concat([lv, rp[[c for c in lv.columns if c in rp.columns]]], ignore_index=True)
    assert not out.duplicated(["assertion_id", "publication_id"]).any()
    return out


def add_publications(pub, prepl):
    new = prepl.copy()
    new["ingestion_v150"] = new.ingestion
    new["title_v150"] = new.title; new["journal_v150"] = new.journal; new["year_v150"] = new.year
    new["doi_resolves"] = True
    new["verdict_summary"] = "curator_replacement_verified (Crossref + Europe PMC abstract)"
    assert not set(new.publication_id) & set(pub.publication_id)
    return pd.concat([pub, new[[c for c in new.columns if c in pub.columns]]], ignore_index=True)


def apply_field_corrections(df, corr, table, match):
    """Apply corrections for `table` to df. match: dict corr_col -> df_col used to locate rows.
    Adds v150_corrected_fields / v150_original_values (JSON-ish 'field=value' lists) for traceability."""
    df = df.copy()
    c = corr[corr.target_table == table]
    for col in ("v150_corrected_fields", "v150_original_values"):
        if col not in df:
            df[col] = ""
    n = 0
    for r in c.itertuples():
        m = pd.Series(True, index=df.index)
        for cc, dc in match.items():
            m &= df[dc].astype(str) == str(getattr(r, cc))
        if m.sum() != 1:
            raise ValueError(f"{table}: correction {r} matches {m.sum()} rows")
        i = df.index[m][0]
        nv = "" if pd.isna(r.new_value) else r.new_value
        if r.field not in df:
            df[r.field] = ""
        old = df.at[i, r.field]
        df[r.field] = df[r.field].astype(object)
        df.at[i, r.field] = nv if nv != "" else None
        if r.field != "v150_curation_note":
            df.at[i, "v150_corrected_fields"] = ";".join(x for x in [df.at[i, "v150_corrected_fields"], r.field] if x)
            df.at[i, "v150_original_values"] = " | ".join(
                x for x in [df.at[i, "v150_original_values"], f"{r.field}={'' if pd.isna(old) else old}"] if x)
        n += 1
    return df, n


def e1_eligibility(e1, links, dec):
    """Return (eligible bool Series, reason Series) aligned to e1.index."""
    removed = dec[dec.decision.isin(E1_REMOVING)]
    rm = dict(zip(removed.source_acc, "curator_" + removed.decision + ": " + removed.curator_note))
    act = links[links.is_active == 1]
    has_link = set(links.source_acc)
    supported = set(act.loc[act.counts_as_support == 1, "source_acc"])
    ok, why = [], []
    for acc in e1.source_acc:
        if acc in rm:
            ok.append(False); why.append(rm[acc])
        elif acc in has_link and acc not in supported:
            ok.append(False); why.append("no_verified_supporting_link")
        else:
            ok.append(True); why.append("")
    return pd.Series(ok, index=e1.index), pd.Series(why, index=e1.index)
