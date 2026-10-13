# PR-7c.2 habitat sidecar - independent verification

**Verdict: INDEPENDENT_PASS** (all 10 data checks pass with zero discrepancies; schema validation passes; screenshot review finds no blocking semantic error, 9 minor wording/layout concerns).

Method: own code (`independent_rederive.py`) written from WEB_DATA_CONTRACT §16, habitat.schema.json, contract.json and habitat_field_dictionary.md; build.py/tests not read. Sidecar: a fresh export (`data/v1.6.0/habitat/`) of commit e39a3df; re-run on the final export of 76f5e6d (see `independent_checks_76f5e6d.json`). Repo not modified.

| # | Check | Status | Key numbers |
|---|---|---|---|
| 1 | File set | PASS | 5,299 files = 5,299 MRDB; 5,466 sources each once in its MRDB file; representative first; n_source_records ok; multi-source 129, grades differ 43 |
| 2 | Per source record | PASS | 5,466 checked; all statuses/flags/has_usable/has_host verbatim; sample_link none = 18 = NO_LINK; missingness on 2,831 NR only (12 no_traceable_sample_link); also accessions, linkage, record_evidence_ids match |
| 3 | Items | PASS | 105,750 evidence rows; 59,086 display items expected = sidecar = manifest; 46,664 non-display rows absent; all 13 item fields identical; 19 empty values exported as null; groups: collection 35,077, physical 20,095, host 3,859, organism_context 55 |
| 4 | Evidence IDs | PASS | 105,659 HE + 91 HL recomputed (6 HL use literal `None` DOI), 0 mismatches; manifest `recomputed` 105,750 |
| 5 | Quarantine | PASS | Independent rule: 14 items / 7 records (12 envo_id_not_found_in_ols `ENVO:0010003`, 2 unprefixed `00000316`); sidecar identical; 0 extra/missing |
| 6 | Host leakage | PASS | 0 host/host_detail outside host; 55 organism_context items all literature scope=organism, none elsewhere |
| 7 | Literature | PASS | 91 items: pmid/doi/locator/scope/access/consistent_with_db/source_sha256/quote/URLs match; 110 reviewed records, 502 sources_checked match (sidecar omits `url`, `step`, `note`, `added_by` keys - by design, not an error) |
| 8 | summary.json | PASS | 43/43 metrics recomputed and matched (incl. percents); 39 compared with coverage TSV (source_record/all) + 2 mrdb metrics, 0 mismatches; 2540/5466, 755, 186, 207, NR scopes 2796/23/12, no link 18, 129/43 confirmed |
| 9 | manifest.json | PASS | 5,300 listed files: SHA-256 + bytes + total_bytes ok, none unlisted, all ≤64 KiB; 5 input hashes = files = contract; no timestamps, no /workspace,/mnt,/tmp strings in 5,301 files |
| 10 | URLs | PASS | 59,177 URLs, all https, allowed hosts: www.ebi.ac.uk 36,424+86, www.ncbi.nlm.nih.gov 22,571, pubmed 91, pmc 4, eutils 1 |
| - | JSON schema | PASS | 5,299 record files, summary, manifest valid (Draft 2020-12) |

Note: the evidence TSV is Python csv excel-tab dialect (quoted fields with doubled `"`); a first pass with QUOTE_NONE produced 10 false HE mismatches (verifier error, corrected). Downstream readers must use standard CSV quoting.

## Screenshot review (24 PNGs; 375 px tiles inspected by cropping)
Correct in all cases: grade wording matches scenario; host values only in Host association card ("A host is a host association, not a physical habitat"); organism context labelled "not the sampling habitat of this sequence"; no-link records Q53461/A0AAJ6N6B2 say "No traceable INSDC or sample link; sample records could not be checked" (never "not reported in the linked sample records"); conflicts (A0A9W6BMQ0, A0A411LJN5, host A0A4Q4MIR8) list all values, "none is chosen"; quarantined `ENVO:0010003` and `00000316` shown as text with "not an ontology term", no ENVO link; MRDB-level habitat not asserted for differing sources; no inferred habitat seen.

Minor concerns (non-blocking):
1. Host badge appears after the label "Physical habitat evidence:" (all cases) - can read as host being habitat evidence.
2. No-link records show badge "Host not reported" though samples could not be checked.
3. A0AAJ6N6B2 VERIFIED_ISOLATE rests on a hedged quote ("These features may reflect that ... PCC 7104 ... is isolated from the ocean"); "A publication states where the source isolate ... was obtained" overstates it (upstream audit judgement).
4. "Linkage: cds protein id (literature confidence)" (A0A411LJN5) / "(high confidence)" displays the physical-axis mapping_confidence as linkage confidence.
5. Header says nothing is "normalised", but "Sample type: isolate genome" and humanised linkage labels are audit-derived.
6. A0A411LJN5 host card: "No host is reported" yet lists Host detail `host_description` = "Not applicable"; raw field label.
7. Host-tissue isolation source shown as physical habitat (A0A4Q4MIR8 "infected leaves", host apple) - per audit rules, but worth a UI hint.
8. 375 px: multi-source table clipped at right ("Physical habitat ev…", Host column off-screen) - fine only if scrollable. No overlapping text otherwise.
9. summary `host_association_only` definition says "host reported" but 186 includes 15 host-AMBIGUOUS records.
