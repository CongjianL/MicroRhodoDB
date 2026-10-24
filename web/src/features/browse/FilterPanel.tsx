/** Browse filter controls. Every control has an explicit label; changes are committed to the URL. */
import { useEffect, useId, useState } from "react";
import type { Clades, EvidenceLevel, Vocabulary } from "../../data/types";
import { CLADE_STATES, DOMAINS, statusesForGroup, type BrowseState } from "../../lib/browse";
import { CLADE_STATE_LABEL, EVIDENCE_LEVELS, FUNC_LABEL, FUNC_ORDER, STATUS_LABEL } from "../../lib/format";

type Patch = Partial<BrowseState>;

function Field({ label, children, help, id }: { label: string; children: React.ReactNode; help?: React.ReactNode; id: string }) {
  return (
    <div>
      <label htmlFor={id} className="field-label">{label}</label>
      {children}
      {help ? <p className="help mt-1 text-xs">{help}</p> : null}
    </div>
  );
}

/** Text input that commits after a short pause (or Enter) and re-syncs when the URL changes. */
export function DebouncedInput({ value, onCommit, delay = 300, ...rest }: {
  value: string;
  onCommit: (v: string) => void;
  delay?: number;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  useEffect(() => {
    if (v === value) return;
    const t = setTimeout(() => onCommit(v), delay);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v]);
  return (
    <input
      {...rest}
      value={v}
      onChange={(e) => setV(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          if (v !== value) onCommit(v);
        }
      }}
    />
  );
}

function Check({ checked, onChange, children, testId }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode; testId?: string }) {
  const id = useId();
  return (
    <div className="flex items-start gap-2 py-0.5">
      <input id={id} type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-[#1665b5]" checked={checked} onChange={(e) => onChange(e.target.checked)} data-testid={testId} />
      <label htmlFor={id} className="text-sm leading-snug">{children}</label>
    </div>
  );
}

export function FilterPanel({ s, update, clades, vocab, residues }: {
  s: BrowseState;
  update: (p: Patch) => void;
  clades: Clades;
  vocab: Vocabulary;
  residues: string[];
}) {
  const ids = {
    q: useId(), status: useId(), func: useId(), ev: useId(), clade: useId(), sub: useId(), state: useId(), domain: useId(),
    lin: useId(), motif: useId(), residue: useId(), lmin: useId(), lmax: useId(), pdbid: useId(), afdb: useId(),
  };
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const subs = clades.subclades.filter((x) => !s.clade || x.parent_clade_id === s.clade);
  return (
    <div className="space-y-4" data-testid="filter-panel">
      <Field id={ids.q} label="Text search" help="MRDB or source accession, protein name, organism, helix-C motif or clade name (substring, case-insensitive).">
        <DebouncedInput id={ids.q} type="search" className="field" value={s.q} onCommit={(q) => update({ q })} placeholder="e.g. halorhodopsin" data-testid="filter-q" autoComplete="off" spellCheck={false} />
      </Field>

      <Field id={ids.status} label="Membership status">
        <select id={ids.status} className="field" value={s.status} onChange={(e) => update({ status: e.target.value as BrowseState["status"] })} data-testid="filter-status">
          <option value="">Any status in this view</option>
          {statusesForGroup(s.group).map((x) => <option key={x} value={x}>{STATUS_LABEL[x]}</option>)}
        </select>
      </Field>

      <Field id={ids.func} label="Functional class">
        <select id={ids.func} className="field" value={s.func} onChange={(e) => update({ func: e.target.value as BrowseState["func"] })} data-testid="filter-func">
          <option value="">Any</option>
          {FUNC_ORDER.map((f) => <option key={f} value={f}>{FUNC_LABEL[f]}</option>)}
        </select>
      </Field>

      <Field id={ids.ev} label="Evidence level" help={s.evidence ? `${s.evidence}: ${evDef.get(s.evidence as EvidenceLevel)}` : "E1–E5 are evidence types, not probabilities."}>
        <select id={ids.ev} className="field" value={s.evidence} onChange={(e) => update({ evidence: e.target.value as BrowseState["evidence"] })} data-testid="filter-evidence">
          <option value="">Any</option>
          {EVIDENCE_LEVELS.map((e) => <option key={e} value={e}>{e} - {evDef.get(e)}</option>)}
        </select>
      </Field>

      <fieldset className="space-y-2 rounded-md border border-line p-3">
        <legend className="px-1 text-sm font-semibold">Phylogeny (MR_RT_003)</legend>
        <Field id={ids.clade} label="Level-1 clade or backbone group">
          <select id={ids.clade} className="field" value={s.clade} onChange={(e) => update({ clade: e.target.value, sub: "" })} data-testid="filter-clade">
            <option value="">Any</option>
            {clades.level1.map((c) => (
              <option key={c.clade_id} value={c.clade_id}>
                {c.clade_id} - {c.name}{c.support_audit.iqtree_run1_meets_support_thresholds ? "" : " (support caveat)"}
              </option>
            ))}
          </select>
        </Field>
        <Check checked={s.tent} onChange={(tent) => update({ tent })} testId="filter-tent">
          Include tentative placements for the selected clade
        </Check>
        <Field id={ids.sub} label="Subclade">
          <select id={ids.sub} className="field" value={s.sub} onChange={(e) => update({ sub: e.target.value })} data-testid="filter-sub">
            <option value="">Any</option>
            {subs.map((c) => <option key={c.clade_id} value={c.clade_id}>{c.clade_id}{c.name ? ` - ${c.name}` : ""}</option>)}
          </select>
        </Field>
        <Field id={ids.state} label="Placement state">
          <select id={ids.state} className="field" value={s.state} onChange={(e) => update({ state: e.target.value as BrowseState["state"] })} data-testid="filter-state">
            <option value="">Any</option>
            {CLADE_STATES.map((c) => <option key={c} value={c}>{CLADE_STATE_LABEL[c]}</option>)}
          </select>
        </Field>
      </fieldset>

      <fieldset className="space-y-2 rounded-md border border-line p-3">
        <legend className="px-1 text-sm font-semibold">Taxonomy</legend>
        <Field id={ids.domain} label="Taxonomic domain" help="Viral and environmental records have no domain in v1.6.1; filter viruses with the lineage field.">
          <select id={ids.domain} className="field" value={s.domain} onChange={(e) => update({ domain: e.target.value as BrowseState["domain"] })} data-testid="filter-domain">
            <option value="">Any</option>
            {DOMAINS.map((d) => <option key={d} value={d}>{d === "none" ? "No domain assigned" : d}</option>)}
          </select>
        </Field>
        <Field id={ids.lin} label="Lineage contains">
          <DebouncedInput id={ids.lin} type="search" className="field" value={s.lin} onCommit={(lin) => update({ lin })} placeholder="e.g. Viruses, Haloarchaea" data-testid="filter-lin" autoComplete="off" />
        </Field>
      </fieldset>

      <fieldset className="space-y-2 rounded-md border border-line p-3">
        <legend className="px-1 text-sm font-semibold">Sequence</legend>
        <Field id={ids.motif} label="Helix-C motif (exact)">
          <DebouncedInput id={ids.motif} className="field font-mono uppercase" value={s.motif} maxLength={5} onCommit={(motif) => update({ motif: motif.toUpperCase().replace(/[^A-Z-]/g, "") })} placeholder="e.g. DTE" data-testid="filter-motif" autoComplete="off" />
        </Field>
        <Field id={ids.residue} label="Retinal-site residue">
          <select id={ids.residue} className="field" value={s.residue} onChange={(e) => update({ residue: e.target.value })} data-testid="filter-residue">
            <option value="">Any</option>
            {residues.map((r) => <option key={r} value={r}>{r === "none" ? "Not reported" : r === "-" ? "- (recorded as gap)" : r}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field id={ids.lmin} label="Min length (aa)">
            <DebouncedInput id={ids.lmin} className="field tabular" inputMode="numeric" value={s.lmin === null ? "" : String(s.lmin)} onCommit={(v) => update({ lmin: /^\d{1,5}$/.test(v) ? Number(v) : null })} data-testid="filter-lmin" />
          </Field>
          <Field id={ids.lmax} label="Max length (aa)">
            <DebouncedInput id={ids.lmax} className="field tabular" inputMode="numeric" value={s.lmax === null ? "" : String(s.lmax)} onCommit={(v) => update({ lmax: /^\d{1,5}$/.test(v) ? Number(v) : null })} data-testid="filter-lmax" />
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-2 rounded-md border border-line p-3">
        <legend className="px-1 text-sm font-semibold">Structures and evidence</legend>
        <Check checked={s.pdb} onChange={(pdb) => update({ pdb })} testId="filter-pdb">Has experimental PDB structure</Check>
        <Field id={ids.pdbid} label="PDB ID">
          <DebouncedInput id={ids.pdbid} className="field font-mono uppercase" value={s.pdbid} maxLength={4} onCommit={(v) => update({ pdbid: /^[0-9][A-Za-z0-9]{3}$/.test(v) ? v.toUpperCase() : "" })} placeholder="e.g. 1C3W" data-testid="filter-pdbid" autoComplete="off" />
        </Field>
        <Field id={ids.afdb} label="AlphaFold DB model">
          <select id={ids.afdb} className="field" value={s.afdb} onChange={(e) => update({ afdb: e.target.value as BrowseState["afdb"] })} data-testid="filter-afdb">
            <option value="">Any</option>
            <option value="1">Available</option>
            <option value="0">Not available</option>
          </select>
        </Field>
        <Check checked={s.conflict} onChange={(conflict) => update({ conflict })} testId="filter-conflict">Function-call conflict only</Check>
        <Check checked={s.curated} onChange={(curated) => update({ curated })} testId="filter-curated">Curated membership override only</Check>
        <Check checked={s.pub} onChange={(pub) => update({ pub })} testId="filter-pub">Has supporting publication link</Check>
      </fieldset>
    </div>
  );
}
