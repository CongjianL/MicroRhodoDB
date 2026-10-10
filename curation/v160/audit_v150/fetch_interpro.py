"""Audit C: page the InterPro API for all UniProtKB proteins matching Pfam PF01036 (bacteriorhodopsin-like)
and PF18761 (heliorhodopsin). Writes interpro_<pfam>.tsv (accession, source_database, length, tax_id, name)."""
import json, sys, time, urllib.request
import pandas as pd

OUT = "/workspace/v150/review_auditC"


def fetch(pf):
    url = f"https://www.ebi.ac.uk/interpro/api/protein/uniprot/entry/pfam/{pf}/?page_size=200"
    rows, n = [], None
    while url:
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    if r.status == 408:
                        raise IOError("408")
                    js = json.load(r)
                break
            except Exception as e:  # noqa
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"failed {url}")
        n = js["count"]
        for res in js["results"]:
            m = res["metadata"]
            rows.append(dict(accession=m["accession"], source_database=m["source_database"], length=m.get("length"),
                             tax_id=(m.get("source_organism") or {}).get("taxId"),
                             organism=(m.get("source_organism") or {}).get("scientificName"), name=m.get("name")))
        url = js.get("next")
    df = pd.DataFrame(rows).drop_duplicates("accession")
    df.to_csv(f"{OUT}/interpro_{pf}.tsv", sep="\t", index=False)
    print(pf, "API count", n, "retrieved", len(df), time.strftime("%Y-%m-%d %H:%M:%S"))


for pf in sys.argv[1:]:
    fetch(pf)
