"""Parent verification of literature quotes (PR-7c.1).

For every literature item returned by the reviewer agents, the parent re-fetches the cited
source URL (through the same HTTP cache used for database retrieval), strips markup and checks
that the quote occurs verbatim after whitespace / typographic normalization. Results are written
next to the merged literature file; strain-match and habitat-nature judgements are applied
separately and recorded per item in `parent_check`.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path

from .http_cache import HttpCache, cache_key
from . import common as C

TAG_RE = re.compile(r"<[^>]+>")
# inline formatting tags (e.g. a superscript type-strain "T") are removed without inserting a space
INLINE_TAG_RE = re.compile(r"</?(sup|sub|i|b|em|strong|italic|bold|sc|span)(\s[^>]*)?>", re.I)


def norm_text(s: str) -> str:
    s = html.unescape(s or "")
    s = INLINE_TAG_RE.sub("", s)
    s = TAG_RE.sub(" ", s)
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2013", "-").replace("\u2014", "-").replace("\u2010", "-").replace("\u2011", "-")
         .replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " "))
    s = re.sub(r"\s+", " ", s).strip().lower()
    # citation brackets are rendered with variable spacing in XML vs HTML
    s = re.sub(r"\s*([\[\]\(\),;.\"])\s*", r"\1", s)
    return s


def source_text(cache: HttpCache, url: str) -> tuple[str | None, str, int | None]:
    params: dict = {}
    e = cache.get(url, params)  # the cache may add NCBI tool/email to params; the key must include them
    key = cache_key("GET", url, params)
    if not e["ok"] or e["status"] != 200:
        return None, key, e.get("status")
    txt = e["text"] or ""
    if url.startswith("https://www.ebi.ac.uk/europepmc/webservices/rest/search"):
        try:
            res = json.loads(txt).get("resultList", {}).get("result", [])
            txt = " ".join((r.get("title") or "") + " " + (r.get("abstractText") or "") for r in res)
        except ValueError:
            pass
    return txt, key, 200


def verify(lit: dict, cache: HttpCache) -> dict:
    out = {}
    for acc in sorted(lit):
        for i, it in enumerate(lit[acc].get("items", [])):
            url = it.get("source_url") or ""
            txt, key, status = source_text(cache, url) if url.startswith("http") else (None, "", None)
            # whitespace-insensitive comparison: XML/HTML renderings differ in spacing around
            # superscripts, quotes and citation brackets; characters themselves must match.
            found = bool(txt) and re.sub(r"\s", "", norm_text(it.get("quote", ""))) in re.sub(r"\s", "", norm_text(txt))
            sub = norm_text(it.get("habitat_text", "")) in norm_text(it.get("quote", ""))
            out[f"{acc}#{i}"] = {"url": url, "request_key": key, "http_status": status,
                                 "quote_found_in_source": found, "habitat_text_in_quote": sub,
                                 "source_sha256": C.sha256_bytes(txt.encode()) if txt else None}
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("literature", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--cache", type=Path, default=C.DEFAULT_CACHE)
    a = ap.parse_args(argv)
    lit = json.loads(a.literature.read_text(encoding="utf-8"))
    res = verify(lit, HttpCache(a.cache, offline=a.offline))
    C.dump_json(a.out, res)
    bad = [k for k, v in res.items() if not v["quote_found_in_source"]]
    print(f"items={len(res)} quote_found={len(res) - len(bad)} not_found={len(bad)}")
    for k in bad:
        print("  NOT FOUND", k, res[k]["http_status"], res[k]["url"][:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
