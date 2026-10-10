/* MicroRhodoDB static browser (v1.6.0). Data: window.MRDB from data.js. No server or network access needed. */
"use strict";
const D = window.MRDB;
const C = D.columns;
const R = D.rows.map((r, i) => { const o = Object.fromEntries(C.map((c, j) => [c, r[j]])); o._i = i; return o; });
const SEQ = D.seqs;
const BY_SRC = new Map(R.map(r => [r.source_acc, r]));
const BY_MRDB = new Map();
R.forEach(r => { if (!BY_MRDB.has(r.mrdb_acc)) BY_MRDB.set(r.mrdb_acc, []); BY_MRDB.get(r.mrdb_acc).push(r); });
const SHOW = ["mrdb_acc", "source_acc", "organism", "length", "membership_status", "func_class", "evidence_level",
  "clade_display", "helixC_motif", "flags"];
const PS = 100;
let F = [], page = 0, sortc = null, sortd = 1;
const $ = id => document.getElementById(id);
const esc = v => v === null || v === undefined ? "" : String(v).replace(/[&<>"']/g,
  ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]));
R.forEach(r => {
  r.clade_display = r.clade_confidence === "confident" ? r.clade_id :
    (r.clade_confidence === "tentative" ? "TENTATIVE:" + r.tentative_clade_id : "");
});

/* ------------------------------------------------------------------ browse view */
function initBrowse() {
  const m = D.meta;
  let lv = {}; try { lv = JSON.parse(m.evidence_level_counts_counted || "{}"); } catch (e) { lv = {}; }
  $("ver").textContent = `v${m.version} (${m.release_date}) | ${R.length} records (${m.n_counted_records} counted, ` +
    `${m.n_engineered_records} engineered constructs excluded from counts) | ${m.license}`;
  D.status.forEach(s => $("fs").add(new Option(s.status, s.status)));
  D.clades.forEach(c => $("fc").add(new Option(`${c.clade_id} ${c.name || ""}`, c.clade_id)));
  [...new Set(R.map(r => r.func_class).filter(Boolean))].sort().forEach(f => $("ff").add(new Option(f, f)));
  $("hd").innerHTML = SHOW.map(c => `<th data-c="${c}">${c === "clade_display" ? "clade" : c}</th>`).join("");
  document.querySelectorAll("#hd th").forEach(th => th.onclick = () => {
    const c = th.dataset.c; sortd = (sortc === c) ? -sortd : 1; sortc = c; apply();
  });
  ["q", "fs", "fc", "fe", "ff", "fd", "ft", "fx", "fg"].forEach(id => $(id).addEventListener("input", () => { page = 0; apply(); }));
  $("prev").onclick = () => { if (page > 0) { page--; render(); } };
  $("next").onclick = () => { page++; render(); };
  $("dl-tsv").onclick = downloadTSV;
  $("dl-fasta").onclick = downloadFASTA;
  apply();
}
function apply() {
  const q = $("q").value.toLowerCase().trim(), s = $("fs").value, c = $("fc").value, e = $("fe").value,
    f = $("ff").value, dm = $("fd").value, ft = $("ft").checked, fx = $("fx").checked, fg = $("fg").checked;
  F = R.filter(r => (!s || r.membership_status === s) &&
    (!c || r.clade_id === c || (ft && r.clade_confidence === "tentative" && r.tentative_clade_id === c)) &&
    (!e || r.evidence_level === e) && (!f || r.func_class === f) && (!dm || r.tax_domain === dm) &&
    (!fx || r.call_conflict === 1) && (fg || r.is_engineered !== 1) &&
    (!q || [r.mrdb_acc, r.source_acc, r.organism, r.protein_name, r.helixC_motif, r.clade_name]
      .some(v => v && String(v).toLowerCase().includes(q))));
  if (sortc) F.sort((a, b) => (a[sortc] > b[sortc] ? 1 : a[sortc] < b[sortc] ? -1 : 0) * sortd);
  render();
}
function flagsHTML(r) {
  return (r.call_conflict === 1 ? '<span class="flag conflict" title="legacy v1.4 call and motif class disagree">conflict</span>' : "") +
    (r.is_engineered === 1 ? '<span class="flag eng" title="engineered construct; excluded from counts">engineered</span>' : "") +
    (r.clade_confidence === "tentative" ? '<span class="flag tent" title="distant placement, low confidence">tentative clade</span>' : "") +
    (r.membership_status === "typeI_member_curated" ? '<span class="flag cur" title="member by signed curator override (E1 primary evidence; score below member threshold)">curated member</span>' : "") +
    (r.novel_family_flag ? `<span class="flag fam" title="family-HMM flag (informational; status unchanged)">${esc(r.novel_family_flag)}</span>` : "");
}
function render() {
  const n = Math.max(1, Math.ceil(F.length / PS)); page = Math.min(page, n - 1);
  $("info").textContent = `${F.length} records match`;
  $("pg").textContent = `page ${page + 1}/${n}`;
  $("tb").innerHTML = F.slice(page * PS, (page + 1) * PS).map(r => `<tr data-a="${esc(r.source_acc)}">` + SHOW.map(c => {
    if (c === "evidence_level") return `<td><span class="badge ${esc(r[c])}">${esc(r[c])}</span></td>`;
    if (c === "flags") return `<td>${flagsHTML(r)}</td>`;
    if (c === "clade_display" && r.clade_confidence === "tentative") return `<td><i>${esc(r[c])}</i></td>`;
    return `<td>${esc(r[c])}</td>`;
  }).join("") + "</tr>").join("");
  document.querySelectorAll("#tb tr").forEach(tr => tr.onclick = () => { location.hash = "#/record/" + tr.dataset.a; });
}
function saveBlob(text, name, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}
function downloadTSV() {
  const cols = C.filter(c => c !== "_i");
  saveBlob([cols.join("\t")].concat(F.map(r => cols.map(c => r[c] ?? "").join("\t"))).join("\n") + "\n",
    "microrhododb_v" + D.meta.version + "_selection.tsv", "text/tab-separated-values");
}
function fastaRecord(r) {
  const s = SEQ[r._i];
  return `>${r.mrdb_acc} ${r.source_acc} status=${r.membership_status} evidence=${r.evidence_level} ` +
    `func=${r.func_class} clade=${r.clade_display || "none"} engineered=${r.is_engineered}\n` +
    s.replace(/(.{60})/g, "$1\n").replace(/\n$/, "") + "\n";
}
function downloadFASTA() {
  saveBlob(F.map(fastaRecord).join(""), "microrhododb_v" + D.meta.version + "_selection.fasta", "text/plain");
}

/* ------------------------------------------------------------------ record detail (#/record/<MRDB or source acc>) */
function showRecord(id) {
  const recs = BY_MRDB.get(id) || (BY_SRC.has(id) ? [BY_SRC.get(id)] : null);
  const el = $("detail");
  if (!recs) { el.innerHTML = `<button id="close-detail">close</button><h2>Not found: ${esc(id)}</h2>`; }
  else {
    const all = BY_MRDB.get(recs[0].mrdb_acc).slice()
      .sort((a, b) => b.is_mrdb_representative - a.is_mrdb_representative || (a.source_acc < b.source_acc ? -1 : 1));
    const focus = BY_SRC.has(id) ? BY_SRC.get(id) : all[0];
    el.innerHTML = `<button id="close-detail">close</button>` +
      `<h2 id="detail-title">${esc(focus.mrdb_acc)} / ${esc(focus.source_acc)}</h2>` +
      `<div><a href="#/record/${esc(focus.mrdb_acc)}">permalink #/record/${esc(focus.mrdb_acc)}</a></div>` +
      (all.length > 1 ? `<p>This MRDB accession groups ${all.length} identical-sequence source records: ` +
        all.map(r => `<a href="#/record/${esc(r.source_acc)}">${esc(r.source_acc)}</a>`).join(", ") + "</p>" : "") +
      recordHTML(focus);
  }
  el.hidden = false;
  $("close-detail").onclick = () => { el.hidden = true; if (location.hash.startsWith("#/record/")) history.back(); };
}
function recordHTML(r) {
  const kv = (k, v) => `<dt>${esc(k)}</dt><dd>${v}</dd>`;
  const sd = D.status.find(s => s.status === r.membership_status) || {};
  const fd = D.func_classes.find(f => f.func_class === r.func_class) || {};
  const pubs = (D.pubs[r.source_acc] || []).map(p => Object.fromEntries(D.pub_columns.map((c, i) => [c, p[i]])));
  let h = `<div>${flagsHTML(r)}</div><dl class="kv">` +
    kv("protein", esc(r.protein_name)) + kv("organism", esc(r.organism)) + kv("domain", esc(r.tax_domain)) +
    kv("length", esc(r.length)) +
    kv("membership status", `${esc(r.membership_status)} <span class="k">${esc(sd.definition || "")}</span>`) +
    (r.membership_status === "typeI_member_curated" ? kv("curated override", esc(r.status_reason)) : "") +
    kv("family-HMM flag", r.novel_family_flag ? `${esc(r.novel_family_flag)} <span class="k">best family HMM outscores PF01036 (E&le;1e-10); informational, status unchanged</span>` : "none") +
    kv("membership score", esc(r.membership_score)) + kv("retinal-site residue", esc(r.retinal_site_residue)) +
    kv("functional class", `${esc(r.func_class)} <span class="k">${esc(fd.definition || "")}</span>`) +
    kv("evidence level", `<span class="badge ${esc(r.evidence_level)}">${esc(r.evidence_level)}</span>`) +
    kv("function basis", esc(r.function_basis)) +
    (r.override_rule ? kv("override rule", esc(r.override_rule)) : "") +
    kv("legacy v1.4 class", esc(r.func_class_v14)) +
    kv("helix-C motif (BR 85/89/96)", esc(r.helixC_motif)) + kv("motif class", esc(r.motif_class)) +
    kv("call conflict", r.call_conflict === 1 ? `yes: ${esc(r.call_conflict_detail)}` : "no") +
    (r.e2_ref ? kv("E2 transfer reference", `<a href="#/record/${esc(r.e2_ref)}">${esc(r.e2_ref)}</a> (identity ${esc(r.e2_identity)})`) : "") +
    kv("engineered construct", r.is_engineered === 1 ?
      `yes; wild type <a href="#/record/${esc(r.wild_type_acc)}">${esc(r.wild_type_acc)}</a> (excluded from counts, E2 transfer and benchmarks)` : "no") +
    (r.exact_duplicate_of ? kv("exact duplicate of", `<a href="#/record/${esc(r.exact_duplicate_of)}">${esc(r.exact_duplicate_of)}</a>`) : "") +
    (r.e1_representative && r.e1_representative !== r.source_acc ? kv("E1 sequence representative", `<a href="#/record/${esc(r.e1_representative)}">${esc(r.e1_representative)}</a>`) : "") +
    kv("clade", r.clade_confidence === "confident" ? `${esc(r.clade_id)} ${esc(r.clade_name || "")} ${esc(r.subclade_id || "")}` :
      r.clade_confidence === "tentative" ? `<i>tentative: ${esc(r.tentative_clade_id)} ${esc(r.tentative_clade_name || "")}</i> ` +
        `(distant placement, low confidence: assigned by LWR but failed the pendant-length QC; not a clade assignment)` : "none") +
    kv("GTDB taxonomy", esc(r.gtdb_taxonomy)) + kv("retinal pocket (BR numbering)", esc(r.pocket_string_br)) +
    kv("AlphaFold DB", r.afdb_model_id ? `<a target="_blank" rel="noopener" href="https://alphafold.ebi.ac.uk/entry/${esc(r.source_acc)}">${esc(r.afdb_model_id)}</a> (pLDDT ${esc(r.afdb_global_plddt)})` : "none") +
    kv("UniProt", `<a target="_blank" rel="noopener" href="https://www.uniprot.org/uniprotkb/${esc(r.source_acc)}">${esc(r.source_acc)}</a>`) +
    "</dl>";
  h += `<h3>Publications (${pubs.length})</h3>`;
  if (!pubs.length) h += `<p class="k">No linked publication.</p>`;
  pubs.forEach(p => {
    h += `<div class="pub ${esc(p.link_role)}" data-role="${esc(p.link_role)}"><div>${esc(p.title || "(title not available)")}</div>` +
      `<div class="k">${esc(p.journal || "")} ${esc(p.year || "")} | role: ${esc(p.link_role)}` +
      `${p.counts_as_support === 1 ? " (counts as support)" : " (not counted as support)"} | verdict: ${esc(p.verdict)}</div><div>` +
      (p.pmid ? `<a class="pmid" target="_blank" rel="noopener" href="https://pubmed.ncbi.nlm.nih.gov/${esc(p.pmid)}/">PMID ${esc(p.pmid)}</a> ` : "") +
      (p.doi ? `<a class="doi" target="_blank" rel="noopener" href="https://doi.org/${esc(p.doi)}">doi:${esc(p.doi)}</a>` : "") + "</div>" +
      (p.caveat ? `<div><b>Caveat:</b> ${esc(p.caveat)}</div>` : "") + "</div>";
  });
  h += `<h3>Sequence <button id="dl-one">FASTA</button></h3><pre class="seq">${esc(SEQ[r._i])}</pre>`;
  setTimeout(() => { const b = $("dl-one"); if (b) b.onclick = () => saveBlob(fastaRecord(r), r.source_acc + ".fasta", "text/plain"); }, 0);
  return h;
}

/* ------------------------------------------------------------------ sequence search */
const AA = "ARNDCQEGHILKMFPSTWYVBZX*";
const B62 = [
  [4,-1,-2,-2,0,-1,-1,0,-2,-1,-1,-1,-1,-2,-1,1,0,-3,-2,0,-2,-1,0,-4],[-1,5,0,-2,-3,1,0,-2,0,-3,-2,2,-1,-3,-2,-1,-1,-3,-2,-3,-1,0,-1,-4],
  [-2,0,6,1,-3,0,0,0,1,-3,-3,0,-2,-3,-2,1,0,-4,-2,-3,3,0,-1,-4],[-2,-2,1,6,-3,0,2,-1,-1,-3,-4,-1,-3,-3,-1,0,-1,-4,-3,-3,4,1,-1,-4],
  [0,-3,-3,-3,9,-3,-4,-3,-3,-1,-1,-3,-1,-2,-3,-1,-1,-2,-2,-1,-3,-3,-2,-4],[-1,1,0,0,-3,5,2,-2,0,-3,-2,1,0,-3,-1,0,-1,-2,-1,-2,0,3,-1,-4],
  [-1,0,0,2,-4,2,5,-2,0,-3,-3,1,-2,-3,-1,0,-1,-3,-2,-2,1,4,-1,-4],[0,-2,0,-1,-3,-2,-2,6,-2,-4,-4,-2,-3,-3,-2,0,-2,-2,-3,-3,-1,-2,-1,-4],
  [-2,0,1,-1,-3,0,0,-2,8,-3,-3,-1,-2,-1,-2,-1,-2,-2,2,-3,0,0,-1,-4],[-1,-3,-3,-3,-1,-3,-3,-4,-3,4,2,-3,1,0,-3,-2,-1,-3,-1,3,-3,-3,-1,-4],
  [-1,-2,-3,-4,-1,-2,-3,-4,-3,2,4,-2,2,0,-3,-2,-1,-2,-1,1,-4,-3,-1,-4],[-1,2,0,-1,-3,1,1,-2,-1,-3,-2,5,-1,-3,-1,0,-1,-3,-2,-2,0,1,-1,-4],
  [-1,-1,-2,-3,-1,0,-2,-3,-2,1,2,-1,5,0,-2,-1,-1,-1,-1,1,-3,-1,-1,-4],[-2,-3,-3,-3,-2,-3,-3,-3,-1,0,0,-3,0,6,-4,-2,-2,1,3,-1,-3,-3,-1,-4],
  [-1,-2,-2,-1,-3,-1,-1,-2,-2,-3,-3,-1,-2,-4,7,-1,-1,-4,-3,-2,-2,-1,-2,-4],[1,-1,1,0,-1,0,0,0,-1,-2,-2,0,-1,-2,-1,4,1,-3,-2,-2,0,0,0,-4],
  [0,-1,0,-1,-1,-1,-1,-2,-2,-1,-1,-1,-1,-2,-1,1,5,-2,-2,0,-1,-1,0,-4],[-3,-3,-4,-4,-2,-2,-3,-2,-2,-3,-2,-3,-1,1,-4,-3,-2,11,2,-3,-4,-3,-2,-4],
  [-2,-2,-2,-3,-2,-1,-2,-3,2,-1,-1,-2,-1,3,-3,-2,-2,2,7,-1,-3,-2,-1,-4],[0,-3,-3,-3,-1,-2,-2,-3,-3,3,1,-2,1,-1,-2,-2,0,-3,-1,4,-3,-2,-1,-4],
  [-2,-1,3,4,-3,0,1,-1,0,-3,-4,0,-3,-3,-2,0,-1,-4,-3,-3,4,1,-1,-4],[-1,0,0,1,-3,3,4,-2,0,-3,-3,1,-1,-3,-1,0,-1,-3,-2,-2,1,4,-1,-4],
  [0,-1,-1,-1,-2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-2,0,0,-2,-1,-1,-1,-1,-1,-4],[-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,-4,1]];
const GO = 11, GE = 1, KMER = 3, PREFILTER = 300, TOP = 10;
const aaIndex = ch => { const i = AA.indexOf(ch); return i < 0 ? 22 : i; };
const encode = s => Uint8Array.from(s, aaIndex);
let ENC = null;
function parseQuery(text) {
  const lines = text.trim().split(/\r?\n/);
  const body = lines[0] && lines[0].startsWith(">") ? lines.slice(1) : lines;
  return body.join("").toUpperCase().replace(/[^A-Z*]/g, "");
}
/* Gotoh affine-gap Smith-Waterman. Score-only pass with O(m) memory. */
function swScore(q, s) {
  const m = s.length; const H = new Int32Array(m + 1), E = new Int32Array(m + 1).fill(-1e9);
  let best = 0;
  for (let i = 1; i <= q.length; i++) {
    const row = B62[q[i - 1]]; let diag = 0, Fv = -1e9, Hleft = 0;
    for (let j = 1; j <= m; j++) {
      const up = H[j];
      E[j] = Math.max(E[j] - GE, up - GO);
      Fv = Math.max(Fv - GE, Hleft - GO);
      let h = diag + row[s[j - 1]];
      if (E[j] > h) h = E[j]; if (Fv > h) h = Fv; if (h < 0) h = 0;
      diag = up; H[j] = h; Hleft = h; if (h > best) best = h;
    }
  }
  return best;
}
/* Full-matrix Smith-Waterman with traceback (only for the reported hits): identity and coverage. */
function swAlign(q, s) {
  const n = q.length, m = s.length, W = m + 1, NEG = -1e9;
  const H = new Int32Array((n + 1) * W), E = new Int32Array((n + 1) * W).fill(NEG), Fm = new Int32Array((n + 1) * W).fill(NEG);
  let best = 0, bi = 0, bj = 0;
  for (let i = 1; i <= n; i++) {
    const row = B62[q[i - 1]];
    for (let j = 1; j <= m; j++) {
      const k = i * W + j;
      E[k] = Math.max(E[k - 1] - GE, H[k - 1] - GO);
      Fm[k] = Math.max(Fm[k - W] - GE, H[k - W] - GO);
      let h = Math.max(0, H[k - W - 1] + row[s[j - 1]], E[k], Fm[k]);
      H[k] = h; if (h > best) { best = h; bi = i; bj = j; }
    }
  }
  let i = bi, j = bj, state = 0, ident = 0, alen = 0, qs = bi, ss = bj;
  while (i > 0 && j > 0) {
    const k = i * W + j;
    if (state === 0) {
      if (H[k] === 0) break;
      if (H[k] === H[k - W - 1] + B62[q[i - 1]][s[j - 1]]) { if (q[i - 1] === s[j - 1]) ident++; alen++; qs = i; ss = j; i--; j--; continue; }
      if (H[k] === E[k]) { state = 1; continue; }
      state = 2; continue;
    }
    if (state === 1) { alen++; ss = j; if (E[k] === H[k - 1] - GO) state = 0; j--; continue; }
    alen++; qs = i; if (Fm[k] === H[k - W] - GO) state = 0; i--;
  }
  return {score: best, identity: alen ? ident / alen : 0, qcov: (bi - qs + 1) / n, scov: (bj - ss + 1) / m, alen};
}
function runSearch() {
  const qs = parseQuery($("sq").value);
  if (qs.length < 20) { $("search-status").textContent = "Please enter a protein sequence of at least 20 residues."; return; }
  $("search-status").textContent = "searching...";
  setTimeout(() => {
    const t0 = performance.now();
    if (!ENC) ENC = SEQ.map(encode);
    const q = encode(qs);
    const qk = new Set(); for (let i = 0; i + KMER <= qs.length; i++) qk.add(qs.substr(i, KMER));
    const pre = SEQ.map((s, idx) => { let c = 0; const seen = new Set();
      for (let i = 0; i + KMER <= s.length; i++) { const k = s.substr(i, KMER); if (qk.has(k) && !seen.has(k)) { seen.add(k); c++; } }
      return [c, idx]; }).sort((a, b) => b[0] - a[0]).slice(0, PREFILTER);
    const scored = pre.map(([c, idx]) => ({idx, score: swScore(q, ENC[idx])}));
    /* ties (identical sequences) -> reviewed (Swiss-Prot) first, then the MRDB representative, then accession */
    scored.sort((a, b) => b.score - a.score || (R[b.idx].reviewed - R[a.idx].reviewed) ||
      (R[b.idx].is_mrdb_representative - R[a.idx].is_mrdb_representative) ||
      (R[a.idx].source_acc < R[b.idx].source_acc ? -1 : 1));
    const hits = scored.slice(0, TOP).map(h => Object.assign(h, swAlign(q, ENC[h.idx])));
    $("search-tb").innerHTML = hits.map((h, k) => { const r = R[h.idx];
      return `<tr data-a="${esc(r.source_acc)}"><td>${k + 1}</td><td>${esc(r.mrdb_acc)}</td><td class="hit-acc">${esc(r.source_acc)}</td>` +
        `<td>${esc(r.protein_name)}</td><td>${esc(r.organism)}</td><td>${h.score}</td><td>${(100 * h.identity).toFixed(1)}%</td>` +
        `<td>${(100 * h.qcov).toFixed(1)}%</td><td>${(100 * h.scov).toFixed(1)}%</td>` +
        `<td><span class="badge ${esc(r.evidence_level)}">${esc(r.evidence_level)}</span></td><td>${esc(r.func_class)} ${flagsHTML(r)}</td></tr>`; }).join("");
    document.querySelectorAll("#search-tb tr").forEach(tr => tr.onclick = () => { location.hash = "#/record/" + tr.dataset.a; });
    $("search-results").hidden = false;
    $("search-status").textContent = `query ${qs.length} aa; ${PREFILTER} prefiltered of ${SEQ.length} records; ` +
      `${((performance.now() - t0) / 1000).toFixed(2)} s`;
  }, 10);
}
function initSearch() {
  $("run-search").onclick = runSearch;
  $("example-search").onclick = () => { const r = BY_SRC.get("P02945"); $("sq").value = ">P02945 bacteriorhodopsin example\n" + SEQ[r._i]; };
}

/* ------------------------------------------------------------------ novel-family candidates, about */
function initNovel() {
  const N = D.novel;
  $("novel-summary").innerHTML = `<p><b>${N.candidates.length}</b> watchlist candidates in v${esc(D.meta.version)} ` +
    `(release metadata: n_novel_family_candidates = ${esc(D.meta.n_novel_family_candidates)}), from ` +
    `${esc(D.meta.n_foldseek_hits)} Foldseek structural hits that passed the funnel. ` +
    `Membership counts are unaffected by this layer.</p>`;
  $("novel-funnel").innerHTML = "<thead><tr>" + N.funnel_columns.map(c => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>" +
    N.funnel.map(r => "<tr>" + r.map(v => `<td>${esc(v)}</td>`).join("") + "</tr>").join("") + "</tbody>";
  $("novel-candidates").innerHTML = N.candidates.length ?
    "<table><thead><tr>" + N.candidate_columns.map(c => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>" +
    N.candidates.map(r => "<tr>" + r.map(v => `<td>${esc(v)}</td>`).join("") + "</tr>").join("") + "</tbody></table>" :
    `<p id="novel-none">No novel-family candidates in this release: every hit that passed the E-value, length and retinal-lysine ` +
    `filters was already in the corpus (see funnel).</p>`;
}
function initAbout() {
  const m = D.meta;
  $("about").innerHTML = `<dl class="kv">` + Object.entries(m).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") +
    `</dl><p class="note">Evidence levels: E1 direct experimental assay of this protein; E2 transfer from an E1 record ` +
    `(&ge;90% identity, &ge;80% coverage, same clade, unanimous class); E3/E4 inferred from motif and clade/legacy rules; ` +
    `E5 unassigned. E3/E4 calls whose legacy class contradicts the helix-C motif class are set to E5 'unassigned' and ` +
    `flagged as call conflicts. Engineered constructs are listed but excluded from all counts.</p>` +
    `<p class="note">Record permalinks: <code>#/record/MRDB000001</code> or <code>#/record/P02945</code>.</p>`;
}

/* ------------------------------------------------------------------ router */
function route() {
  const h = location.hash || "#/";
  const m = h.match(/^#\/record\/([A-Za-z0-9_.-]+)/);
  let view = "browse";
  if (h.startsWith("#/search")) view = "search"; else if (h.startsWith("#/novel")) view = "novel";
  else if (h.startsWith("#/about")) view = "about";
  ["browse", "search", "novel", "about"].forEach(v => {
    $("view-" + v).hidden = v !== view; $("nav-" + v).classList.toggle("on", v === view);
  });
  if (m) showRecord(m[1]); else $("detail").hidden = true;
}
initBrowse(); initSearch(); initNovel(); initAbout();
window.addEventListener("hashchange", route);
route();
