/**
 * Download menu for the active Browse selection (spec 5.4). Exports contain exactly the filtered rows,
 * in the displayed sort order, independent of pagination and column visibility. FASTA exports load
 * sequences/corpus.fasta on demand.
 */
import { useState } from "react";
import { Disclosure } from "../../components/common";
import { loadCorpusFasta, parseCorpusFasta } from "../../data/loaders";
import type { Manifest } from "../../data/types";
import type { IndexRow } from "../../lib/browse";
import { exportFilename, saveText, selectionManifest, toFasta, toTSV, toUniqueFasta } from "../../lib/exporters";
import { fmtInt } from "../../lib/format";

let seqCache: Promise<Map<string, string>> | null = null;
const sequences = () => (seqCache ??= loadCorpusFasta().then(parseCorpusFasta).catch((e) => {
  seqCache = null;
  throw e;
}));

export function ExportMenu({ rows, filterQ, sortKey, sortDir, manifest }: {
  rows: IndexRow[];
  filterQ: string;
  sortKey: string;
  sortDir: string;
  manifest: Manifest;
}) {
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const release = manifest.dataset_release;
  const nMrdb = new Set(rows.map((r) => r.mrdb_acc)).size;
  const empty = rows.length === 0;

  const run = async (close: () => void, kind: "tsv" | "fasta" | "mrdb" | "manifest") => {
    setBusy(true);
    setMsg(kind === "fasta" || kind === "mrdb" ? { text: "Loading sequences for FASTA export..." } : null);
    try {
      let name: string;
      if (kind === "tsv") {
        name = exportFilename(release, "records_tsv", rows.length, filterQ);
        saveText(toTSV(rows), name, "text/tab-separated-values;charset=utf-8");
      } else if (kind === "fasta") {
        const seqs = await sequences();
        name = exportFilename(release, "records_fasta", rows.length, filterQ);
        saveText(toFasta(rows, seqs), name, "text/x-fasta;charset=utf-8");
      } else if (kind === "mrdb") {
        const seqs = await sequences();
        const u = toUniqueFasta(rows, seqs);
        name = exportFilename(release, "mrdb_fasta", u.n, filterQ);
        saveText(u.text, name, "text/x-fasta;charset=utf-8");
      } else {
        name = exportFilename(release, "manifest", rows.length, filterQ);
        const m = selectionManifest({
          release, releaseDate: manifest.release_date, schemaVersion: manifest.schema_version, websiteVersion: manifest.website_version,
          dbSha: manifest.source_db.sha256, filterQ, sortKey, sortDir, rows, now: new Date(),
        });
        saveText(JSON.stringify(m, null, 2) + "\n", name, "application/json");
      }
      setMsg({ text: `Downloaded ${name}` });
      close();
    } catch (e) {
      setMsg({ text: `Export failed: ${(e as Error).message}`, error: true });
    } finally {
      setBusy(false);
    }
  };

  const Item = ({ k, title, detail, close }: { k: "tsv" | "fasta" | "mrdb" | "manifest"; title: string; detail: string; close: () => void }) => (
    <li>
      <button type="button" disabled={busy || empty} onClick={() => run(close, k)} className="w-full rounded-md px-3 py-2 text-left hover:bg-subtle disabled:cursor-not-allowed disabled:opacity-60" data-testid={`export-${k}`}>
        <span className="block font-medium">{title}</span>
        <span className="block text-xs text-ink-2">{detail}</span>
      </button>
    </li>
  );

  return (
    <div className="flex flex-col items-end">
      <Disclosure label={<>Download</>} buttonClass="btn btn-primary btn-sm">
        {(close) => (
          <ul data-testid="export-menu">
            <Item close={close} k="tsv" title="Filtered source records (TSV)" detail={`${fmtInt(rows.length)} rows; legacy v1.6.0 columns first, then added columns`} />
            <Item close={close} k="fasta" title="Filtered source records (FASTA)" detail={`${fmtInt(rows.length)} sequences, one per source accession`} />
            <Item close={close} k="mrdb" title="Unique MRDB sequences (FASTA)" detail={`${fmtInt(nMrdb)} sequences, one per MRDB accession in the selection`} />
            <Item close={close} k="manifest" title="Selection manifest (JSON)" detail="Release, date, filters, counts and file names" />
          </ul>
        )}
      </Disclosure>
      <p className={`mt-1 min-h-[1.25rem] max-w-[22rem] break-all text-right text-xs ${msg?.error ? "text-danger" : "text-ink-2"}`} role="status" aria-live="polite" data-testid="export-status">
        {msg?.text ?? ""}
      </p>
    </div>
  );
}
