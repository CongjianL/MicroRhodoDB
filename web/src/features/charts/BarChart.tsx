/**
 * Horizontal bar chart with an accessible data table. The ECharts canvas is decorative for assistive
 * technology (aria-hidden); the visible summary sentence and the data table carry the numbers.
 * All values come from summary.json distributions (exporter-owned); nothing is computed or rounded
 * here except percentages of the stated denominator.
 */
import { useEffect, useId, useRef, useState } from "react";
import { fmtInt, fmtPct } from "../../lib/format";

export interface BarItem {
  key: string;
  label: string;
  value: number;
  color: string;
  href?: string;
  note?: string;
}

export function BarChart({ title, items, denominator, denominatorLabel, testId, footer }: {
  title: string;
  footer?: React.ReactNode;
  items: BarItem[];
  denominator: number;
  denominatorLabel: string;
  testId?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const headingId = useId();
  const total = items.reduce((a, b) => a + b.value, 0);

  useEffect(() => {
    let disposed = false;
    let chart: { resize: () => void; dispose: () => void } | null = null;
    let ro: ResizeObserver | null = null;
    import("./echarts-core")
      .then(({ echarts }) => {
        if (disposed || !el.current) return;
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
        const c = echarts.init(el.current, undefined, { renderer: "svg" });
        chart = c;
        const rev = [...items].reverse();
        c.setOption({
          animation: !reduce,
          grid: { left: 8, right: 64, top: 6, bottom: 6, containLabel: true },
          tooltip: {
            trigger: "item",
            formatter: (p: { dataIndex: number }) => {
              const it = rev[p.dataIndex];
              return `${it.label}: ${fmtInt(it.value)} of ${fmtInt(denominator)} (${fmtPct(it.value, denominator)})`;
            },
          },
          xAxis: { type: "value", max: Math.max(...items.map((i) => i.value)), axisLabel: { show: false }, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
          yAxis: {
            type: "category",
            data: rev.map((i) => i.label),
            axisTick: { show: false },
            axisLine: { lineStyle: { color: "#c3ced9" } },
            axisLabel: { color: "#142238", fontSize: 13, fontFamily: "system-ui, sans-serif" },
          },
          series: [{
            type: "bar",
            barMaxWidth: 22,
            data: rev.map((i) => ({ value: i.value, itemStyle: { color: i.color, borderRadius: [0, 3, 3, 0] } })),
            label: { show: true, position: "right", color: "#142238", fontSize: 12, formatter: (p: { value: number }) => fmtInt(p.value) },
          }],
        });
        ro = new ResizeObserver(() => c.resize());
        ro.observe(el.current);
      })
      .catch(() => !disposed && setFailed(true));
    return () => {
      disposed = true;
      ro?.disconnect();
      chart?.dispose();
    };
  }, [items, denominator]);

  return (
    <figure className="card flex h-full flex-col p-4" aria-labelledby={headingId} data-testid={testId}>
      <h3 id={headingId} className="text-base">{title}</h3>
      <p className="mt-0.5 text-sm text-ink-2">{denominatorLabel}: n = {fmtInt(denominator)}</p>
      {failed ? (
        <p className="mt-3 text-sm text-ink-2">Chart could not be rendered; the data table below lists the values.</p>
      ) : (
        <div ref={el} aria-hidden="true" className="mt-2 w-full" style={{ height: `${items.length * 34 + 16}px` }} />
      )}
      {footer ? <div className="mt-2 text-sm text-ink-2">{footer}</div> : null}
      <details className="mt-auto pt-2 text-sm">
        <summary className="cursor-pointer text-accent">Data table</summary>
        <table className="data-table mt-2">
          <caption className="sr-only">{title} ({denominatorLabel}, n = {fmtInt(denominator)})</caption>
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col" className="num">Records</th>
              <th scope="col" className="num">% of {fmtInt(denominator)}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.key}>
                <th scope="row" className="!static !bg-transparent !font-normal !whitespace-normal">
                  {i.href ? <a href={i.href}>{i.label}</a> : i.label}
                  {i.note ? <span className="block text-xs text-ink-2">{i.note}</span> : null}
                </th>
                <td className="num">{fmtInt(i.value)}</td>
                <td className="num">{fmtPct(i.value, denominator)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="!static !bg-transparent">Total</th>
              <td className="num font-semibold">{fmtInt(total)}</td>
              <td className="num">{fmtPct(total, denominator)}</td>
            </tr>
          </tfoot>
        </table>
      </details>
    </figure>
  );
}
