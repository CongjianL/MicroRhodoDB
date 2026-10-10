/**
 * Minimal Newick parser and radial phylogram layout for the MR_RT_003 preview.
 *
 * Internal-node labels in MR_RT_003.rooted.treefile ("SH-aLRT/UFBoot") are kept only as raw strings
 * and are never displayed: the PR-1 audit showed several are misassociated after re-rooting. Clade
 * support shown on the site comes from clades.json support_audit.iqtree_run1_* (bipartition-mapped).
 */

export interface TreeNode {
  name: string;
  length: number;
  children: TreeNode[];
  parent: TreeNode | null;
}

export function parseNewick(src: string): TreeNode {
  const s = src.trim();
  let i = 0;
  const root: TreeNode = { name: "", length: 0, children: [], parent: null };
  let cur = root;
  const readLabel = () => {
    let j = i;
    while (j < s.length && !",():;".includes(s[j])) j++;
    const lab = s.slice(i, j).trim();
    i = j;
    return lab;
  };
  while (i < s.length) {
    const c = s[i];
    if (c === "(") {
      const n: TreeNode = { name: "", length: 0, children: [], parent: cur };
      cur.children.push(n);
      cur = n;
      i++;
    } else if (c === ",") {
      if (!cur.parent) throw new Error("Newick: unexpected ','");
      const n: TreeNode = { name: "", length: 0, children: [], parent: cur.parent };
      cur.parent.children.push(n);
      cur = n;
      i++;
    } else if (c === ")") {
      if (!cur.parent) throw new Error("Newick: unbalanced ')'");
      cur = cur.parent;
      i++;
    } else if (c === ":") {
      i++;
      let j = i;
      while (j < s.length && !",();".includes(s[j])) j++;
      const v = Number(s.slice(i, j));
      if (!Number.isFinite(v)) throw new Error(`Newick: bad branch length at ${i}`);
      cur.length = v;
      i = j;
    } else if (c === ";") {
      i++;
      break;
    } else {
      cur.name = readLabel();
    }
  }
  if (cur !== root) throw new Error("Newick: unbalanced parentheses");
  // The outermost "(...)" creates the root's single child when the string starts with "(".
  return root.children.length === 1 && !root.name ? detach(root.children[0]) : root;
}

function detach(n: TreeNode): TreeNode {
  n.parent = null;
  return n;
}

export function leaves(root: TreeNode): TreeNode[] {
  const out: TreeNode[] = [];
  const stack = [root];
  while (stack.length) {
    const n = stack.pop()!;
    if (!n.children.length) out.push(n);
    else for (let k = n.children.length - 1; k >= 0; k--) stack.push(n.children[k]);
  }
  return out;
}

export interface RadialEdge {
  /** Group key used for colouring (level-1 clade / backbone group id) or null for mixed/backbone edges. */
  group: string | null;
  d: string;
}

export interface RadialLayout {
  edges: RadialEdge[];
  /** Angular span (radians) of each contiguous tip group in leaf order. */
  arcs: { group: string; start: number; end: number; n: number }[];
  nTips: number;
  maxDepth: number;
  radius: number;
  /** Radius per substitution/site, for the scale bar. */
  scale: number;
  /** Tip name -> angle (radians) and drawn radius, for highlighting a single tip. */
  tipPos: Map<string, { angle: number; r: number }>;
}

/**
 * Circular phylogram: tips spaced evenly by angle in leaf order; node radius = root-to-node branch
 * length (to scale). Edges: radial segment from parent radius to node radius, plus an arc at each
 * internal node spanning its children. `groupOf` maps tip name -> group (null = ungrouped).
 */
export function radialLayout(root: TreeNode, groupOf: (tip: string) => string | null, radius: number, gap = 0.035): RadialLayout {
  const tips = leaves(root);
  const n = tips.length;
  const span = 2 * Math.PI - gap * 2 * Math.PI;
  const angle = new Map<TreeNode, number>();
  const depth = new Map<TreeNode, number>();
  const group = new Map<TreeNode, string | null>();
  tips.forEach((t, k) => angle.set(t, -Math.PI / 2 + gap * Math.PI + (k + 0.5) * (span / n)));

  // preorder for depth
  const order: TreeNode[] = [];
  const st = [root];
  while (st.length) {
    const x = st.pop()!;
    order.push(x);
    for (let k = x.children.length - 1; k >= 0; k--) st.push(x.children[k]);
  }
  for (const x of order) depth.set(x, x.parent ? depth.get(x.parent)! + x.length : 0);
  for (let k = order.length - 1; k >= 0; k--) {
    const x = order[k];
    if (x.children.length) {
      angle.set(x, (angle.get(x.children[0])! + angle.get(x.children[x.children.length - 1])!) / 2);
      const gs = new Set(x.children.map((c) => group.get(c)!));
      group.set(x, gs.size === 1 ? [...gs][0] : null);
    } else group.set(x, groupOf(x.name));
  }
  const maxDepth = Math.max(...tips.map((t) => depth.get(t)!));
  const sc = radius / maxDepth;
  const pt = (r: number, a: number) => `${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)}`;

  const byGroup = new Map<string | null, string[]>();
  const push = (g: string | null, d: string) => {
    const arr = byGroup.get(g);
    if (arr) arr.push(d);
    else byGroup.set(g, [d]);
  };
  for (const x of order) {
    const a = angle.get(x)!;
    const r1 = depth.get(x)! * sc;
    if (x.parent) {
      const r0 = depth.get(x.parent)! * sc;
      push(group.get(x)!, `M${pt(r0, a)}L${pt(r1, a)}`);
    }
    if (x.children.length > 1) {
      const a0 = angle.get(x.children[0])!;
      const a1 = angle.get(x.children[x.children.length - 1])!;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      if (r1 > 0.01) push(group.get(x)!, `M${pt(r1, a0)}A${r1.toFixed(2)} ${r1.toFixed(2)} 0 ${large} 1 ${pt(r1, a1)}`);
    }
  }
  const edges = [...byGroup.entries()].map(([g, ds]) => ({ group: g, d: ds.join("") }));

  // contiguous tip groups
  const arcs: RadialLayout["arcs"] = [];
  const half = span / n / 2;
  tips.forEach((t) => {
    const g = groupOf(t.name);
    const a = angle.get(t)!;
    const last = arcs[arcs.length - 1];
    if (g && last && last.group === g) {
      last.end = a + half;
      last.n++;
    } else if (g) arcs.push({ group: g, start: a - half, end: a + half, n: 1 });
  });
  const tipPos = new Map(tips.map((t) => [t.name, { angle: angle.get(t)!, r: depth.get(t)! * sc }]));
  return { edges, arcs, nTips: n, maxDepth, radius, scale: sc, tipPos };
}

/** SVG path for an annular sector (clade ring). */
export function sectorPath(r0: number, r1: number, a0: number, a1: number): string {
  const p = (r: number, a: number) => `${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)}`;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${p(r0, a0)}L${p(r1, a0)}A${r1} ${r1} 0 ${large} 1 ${p(r1, a1)}L${p(r0, a1)}A${r0} ${r0} 0 ${large} 0 ${p(r0, a0)}Z`;
}
