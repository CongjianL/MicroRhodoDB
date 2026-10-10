#!/usr/bin/env python
"""Scripted walkthrough of the static v1.6.0 browser (site/) under file:// and under HTTP, or against a live URL.

  python tests/browser_walkthrough_v160.py <site_dir> <db.sqlite> <out.tsv> [--url https://...]

Every displayed number is compared with the release database. Exit status 0 only if every step passes and no
JavaScript error (console error or uncaught page error) occurred in any mode. Requires the `playwright` Python
package with Chromium installed (python -m playwright install chromium).
"""
import argparse
import functools
import http.server
import os
import socketserver
import sqlite3
import sys
import threading

from playwright.sync_api import sync_playwright


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site"); ap.add_argument("db"); ap.add_argument("out"); ap.add_argument("--url")
    a = ap.parse_args()
    site = os.path.abspath(a.site)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    q = lambda s: con.execute(s).fetchone()[0]
    n_all = q("select count(*) from v_master")
    n_conf = q("select count(*) from v_master where call_conflict=1")
    n_e1 = q("select count(*) from v_master where evidence_level='E1'")
    n_e1_noeng = q("select count(*) from v_master where evidence_level='E1' and is_engineered=0")
    n_017 = q("select count(*) from v_master where clade_id='MR_CLD3_017'")
    n_017_t = n_017 + q("select count(*) from v_master where coalesce(clade_id,'')='' and tentative_clade_id='MR_CLD3_017'")
    rows = []

    def log(mode, step, expected, observed, ok):
        rows.append((mode, step, str(expected), str(observed), "PASS" if ok else "FAIL"))

    def walk(pg, base, mode, errs):
        pg.goto(base + "index.html")
        pg.wait_for_function("document.getElementById('info').textContent.length>0", timeout=30000)
        info = pg.inner_text("#info")
        log(mode, "load: all records listed", f"{n_all} records match", info, info == f"{n_all} records match")
        # filters vs DB
        pg.select_option("#fe", "E1")
        log(mode, "E1 filter (incl. engineered)", n_e1, pg.inner_text("#info"), pg.inner_text("#info").startswith(f"{n_e1} "))
        # FASTA download of the E1 selection
        with pg.expect_download() as d:
            pg.click("#dl-fasta")
        fa = open(d.value.path()).read()
        log(mode, "FASTA download of E1 selection", n_e1, fa.count(">"), fa.count(">") == n_e1 and "P02945" in fa)
        with pg.expect_download() as d:
            pg.click("#dl-tsv")
        tsv = open(d.value.path()).read().strip().split("\n")
        log(mode, "TSV download of E1 selection (rows excl. header)", n_e1, len(tsv) - 1, len(tsv) - 1 == n_e1)
        pg.uncheck("#fg")
        log(mode, "E1 filter excluding engineered", n_e1_noeng, pg.inner_text("#info"),
            pg.inner_text("#info").startswith(f"{n_e1_noeng} "))
        pg.check("#fg"); pg.select_option("#fe", "")
        pg.check("#fx")
        log(mode, "call-conflict filter", n_conf, pg.inner_text("#info"), pg.inner_text("#info").startswith(f"{n_conf} "))
        pg.uncheck("#fx")
        pg.select_option("#fc", "MR_CLD3_017")
        log(mode, "clade MR_CLD3_017 (confident)", n_017, pg.inner_text("#info"), pg.inner_text("#info").startswith(f"{n_017} "))
        pg.check("#ft")
        log(mode, "clade MR_CLD3_017 + tentative", n_017_t, pg.inner_text("#info"), pg.inner_text("#info").startswith(f"{n_017_t} "))
        pg.uncheck("#ft"); pg.select_option("#fc", "")
        # deep links
        pg.goto(base + "index.html#/record/MRDB000001")
        pg.wait_for_selector("#detail-title")
        t = pg.inner_text("#detail-title")
        log(mode, "deep link #/record/MRDB000001", "MRDB000001 / P02945", t, t == "MRDB000001 / P02945")
        npub = pg.locator("#detail .pub").count()
        log(mode, "P02945 publications displayed", ">=1 with DOI link", npub,
            npub >= 1 and pg.locator("#detail a.doi").count() >= 1)
        pg.goto(base + "index.html#/record/A0A0D1E071")
        pg.wait_for_function("document.getElementById('detail-title').textContent.includes('A0A0D1E071')")
        txt = pg.inner_text("#detail")
        log(mode, "deep link UmOps1: E1 + PMID 31024506", "PMID 31024506 shown", "PMID 31024506" in txt,
            "PMID 31024506" in txt and pg.locator("#detail a.pmid").count() >= 1)
        pg.goto(base + "index.html#/record/A0ABF7PQA2")
        pg.wait_for_function("document.getElementById('detail-title').textContent.includes('A0ABF7PQA2')")
        txt = pg.inner_text("#detail")
        log(mode, "engineered construct flagged with wild type", "engineered + A0ABF7PQ82",
            "engineered" in txt and "A0ABF7PQ82" in txt, "engineered" in txt and "A0ABF7PQ82" in txt)
        log(mode, "conflict + v1.4 + motif classes shown", "call conflict: yes", "call conflict\nyes" in txt or "yes:" in txt,
            "legacy v1.4 class" in txt and "motif class" in txt and "yes:" in txt)
        # sequence search
        pg.goto(base + "index.html#/search")
        pg.click("#example-search"); pg.click("#run-search")
        pg.wait_for_selector("#search-tb tr", timeout=60000)
        top = pg.inner_text("#search-tb tr:first-child .hit-acc")
        cells = pg.locator("#search-tb tr:first-child td").all_inner_texts()
        log(mode, "sequence search: BR example top hit", "P02945, 100% identity", f"{top} {cells[6]} qcov {cells[7]}",
            top == "P02945" and cells[6] == "100.0%" and cells[7] == "100.0%")
        nh = pg.locator("#search-tb tr").count()
        log(mode, "sequence search returns top 10", 10, nh, nh == 10)
        log(mode, "search page states CLI needed for membership score", "mrdb_search.py mentioned",
            "mrdb_search.py" in pg.inner_text("#view-search"), "mrdb_search.py" in pg.inner_text("#view-search"))
        # a non-identical query (HcKCR1 UOK93384.1; DIAMOND: 99.6% to A0ABF7PQA2)
        qseq = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cli_queries_12.faa")).read().split(">")[1]
        pg.fill("#sq", ">" + qseq); pg.click("#run-search")
        pg.wait_for_function("document.querySelector('#search-tb tr:first-child .hit-acc').textContent!=='P02945'")
        top = pg.inner_text("#search-tb tr:first-child .hit-acc")
        idt = float(pg.locator("#search-tb tr:first-child td").all_inner_texts()[6].rstrip("%"))
        log(mode, "sequence search: HcKCR1 UOK93384.1 top hit", "A0ABF7PQ82/PQA2/PQ84, identity >= 99%", f"{top} {idt}%",
            top in ("A0ABF7PQ82", "A0ABF7PQA2", "A0ABF7PQ84") and idt >= 99.0)
        # novel view
        pg.goto(base + "index.html#/novel")
        pg.wait_for_selector("#novel-summary b")
        n_cand = q("select count(*) from novel_family_candidate")
        shown = pg.locator("#novel-candidates tbody tr").count()
        ok = (pg.locator("#novel-none").count() == 0 and shown == n_cand and
              pg.locator("#novel-funnel tbody tr").count() == 5 and pg.inner_text("#novel-summary b") == str(n_cand))
        log(mode, "novel-family view: Foldseek watchlist rows + 5-family HMM funnel", f"{n_cand} / 5",
            f"{shown} / {pg.locator('#novel-funnel tbody tr').count()}", ok)
        # R2: curated member override and family-HMM flag on record pages
        pg.goto(base + "index.html#/record/A0A1I3DJQ0")
        pg.wait_for_function("document.getElementById('detail-title').textContent.includes('A0A1I3DJQ0')")
        txt = pg.inner_text("#detail")
        ok = "typeI_member_curated" in txt and "curated override" in txt and "PMID:40614199" in txt
        log(mode, "curated member A0A1I3DJQ0: status + override reason", "typeI_member_curated + PMID:40614199", ok, ok)
        pg.goto(base + "index.html#/record/A0AAP2RB57")
        pg.wait_for_function("document.getElementById('detail-title').textContent.includes('A0AAP2RB57')")
        txt = pg.inner_text("#detail")
        ok = "schizorhodopsin" in txt and "schizorhodopsin_family_conflict" in txt and "unresolved" in txt
        log(mode, "schizorhodopsin A0AAP2RB57: family flag + override rule + E5 unresolved", "flag + rule shown", ok, ok)
        log(mode, "JavaScript errors", 0, len(errs), len(errs) == 0)

    with sync_playwright() as p:
        b = p.chromium.launch()
        modes = []
        if a.url:
            modes.append(("live", a.url.rstrip("/") + "/"))
        else:
            modes.append(("file", f"file://{site}/"))
            H = functools.partial(QuietHandler, directory=site)
            srv = socketserver.TCPServer(("127.0.0.1", 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            modes.append(("http", f"http://127.0.0.1:{srv.server_address[1]}/"))
        for mode, base in modes:
            ctx = b.new_context(accept_downloads=True)
            pg = ctx.new_page()
            errs = []
            pg.on("console", lambda m, e=errs: e.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda x, e=errs: e.append(str(x)))
            walk(pg, base, mode, errs)
            ctx.close()
        b.close()
    with open(a.out, "w") as f:
        f.write("mode\tstep\texpected\tobserved\tresult\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    nfail = sum(r[-1] == "FAIL" for r in rows)
    print(f"{len(rows)} steps, {nfail} failed -> {a.out}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
