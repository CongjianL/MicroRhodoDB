"""Cached API helpers (Europe PMC, UniProt REST, NCBI E-utilities, Crossref, RCSB) for MicroRhodoDB v1.6.0 curation.
All raw responses are cached as JSON under ./cache so every PMID/DOI/snippet can be re-verified offline."""
import json, os, re, time, hashlib, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache')
os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'MicroRhodoDB-curation/1.6 (Biomni curation agent)'}


def _get(url, fmt='json', tries=3):
    key = hashlib.md5(url.encode()).hexdigest()
    sub = os.path.join(CACHE, 'raw')
    os.makedirs(sub, exist_ok=True)
    fp = os.path.join(sub, key + ('.json' if fmt == 'json' else '.txt'))
    if os.path.exists(fp):
        with open(fp) as f:
            d = json.load(f)
        return d['body']
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode('utf-8', 'replace')
            body = json.loads(txt) if fmt == 'json' else txt
            with open(fp, 'w') as f:
                json.dump({'url': url, 'retrieved': time.strftime('%Y-%m-%dT%H:%M:%S'), 'body': body}, f)
            return body
        except Exception as e:
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f'GET failed {url}: {err}')


# ---------------- Europe PMC ----------------
def epmc_search(query, n=25):
    url = ('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' +
           urllib.parse.urlencode({'query': query, 'format': 'json', 'pageSize': n, 'resultType': 'lite'}))
    return _get(url).get('resultList', {}).get('result', [])


def epmc_pmid(pmid):
    """core record (title, abstract, doi, year) for a PMID"""
    url = ('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' +
           urllib.parse.urlencode({'query': f'EXT_ID:{pmid} AND SRC:MED', 'format': 'json', 'resultType': 'core'}))
    res = _get(url).get('resultList', {}).get('result', [])
    if not res:
        return None
    r = res[0]
    abst = re.sub(r'<[^>]+>', '', r.get('abstractText', '') or '')
    return {'pmid': str(r.get('pmid', pmid)), 'pmcid': r.get('pmcid'), 'doi': r.get('doi', ''),
            'title': re.sub(r'<[^>]+>', '', r.get('title', '')), 'year': r.get('pubYear', ''),
            'journal': (r.get('journalInfo') or {}).get('journal', {}).get('title', ''),
            'authors': r.get('authorString', ''), 'abstract': abst}


def epmc_fulltext(pmcid):
    url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
    try:
        x = _get(url, fmt='txt')
    except Exception:
        return ''
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', x))


# ---------------- UniProt ----------------
def uniprot(acc):
    url = f'https://rest.uniprot.org/uniprotkb/{acc}.json'
    try:
        return _get(url)
    except Exception:
        return None


def uniprot_function(entry):
    out = []
    for c in (entry or {}).get('comments', []):
        if c.get('commentType') == 'FUNCTION':
            for t in c.get('texts', []):
                ev = ';'.join(f"{e.get('evidenceCode')}|{e.get('source','')}:{e.get('id','')}" for e in t.get('evidences', []))
                out.append((t['value'], ev))
    return out


def uniprot_refs(entry):
    out = []
    for r in (entry or {}).get('references', []):
        cit = r.get('citation', {})
        pm = [x['id'] for x in cit.get('citationCrossReferences', []) if x['database'] == 'PubMed']
        doi = [x['id'] for x in cit.get('citationCrossReferences', []) if x['database'] == 'DOI']
        out.append({'pmid': pm[0] if pm else '', 'doi': doi[0] if doi else '', 'title': cit.get('title', ''),
                    'year': cit.get('publicationDate', ''), 'scope': '; '.join(r.get('referencePositions', []))})
    return out


def uniprot_search(query, fields='accession,protein_name,organism_name,length,reviewed', size=25):
    url = 'https://rest.uniprot.org/uniprotkb/search?' + urllib.parse.urlencode({'query': query, 'format': 'json', 'fields': fields, 'size': size})
    return _get(url).get('results', [])


# ---------------- NCBI / Crossref / RCSB ----------------
def pubmed_summary(pmid):
    url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json'
    return _get(url)


def crossref(doi):
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi)
    try:
        return _get(url)['message']
    except Exception:
        return None


def rcsb_entry(pdb):
    try:
        return _get(f'https://data.rcsb.org/rest/v1/core/entry/{pdb}')
    except Exception:
        return None


# ---------------- snippets ----------------
def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z(\[0-9])', text or '') if s.strip()]


def snippet(text, pattern, maxlen=300):
    """return the first sentence matching regex `pattern` (verbatim; truncated around the match to <=maxlen)."""
    for s in sentences(text):
        m = re.search(pattern, s, re.I)
        if m:
            if len(s) <= maxlen:
                return s
            st = max(0, m.start() - 120)
            return s[st:st + maxlen].strip()
    return ''


def verbatim(snip, text):
    return bool(snip) and snip in (text or '')
