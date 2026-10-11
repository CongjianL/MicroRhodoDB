/** PR-3a: async-control primitives behind the Mol* viewer race fixes (no Mol* involved). */
import { describe, expect, it } from "vitest";
import { Generations, Mutex, SingleFlight } from "../../src/features/structure/loadControl";

const tick = (ms = 0) => new Promise<void>((r) => setTimeout(r, ms));
function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}

describe("Generations", () => {
  it("only the latest request is current; invalidate makes all stale", () => {
    const g = new Generations();
    const a = g.next();
    expect(g.isCurrent(a)).toBe(true);
    const b = g.next();
    expect(g.isCurrent(a)).toBe(false);
    expect(g.isCurrent(b)).toBe(true);
    g.invalidate();
    expect(g.isCurrent(b)).toBe(false);
  });

  it("a slow older request that resolves last cannot commit", async () => {
    const g = new Generations();
    const committed: string[] = [];
    const slow = deferred<string>();
    const fast = deferred<string>();
    const req = (p: Promise<string>) => {
      const my = g.next();
      return p.then((v) => { if (g.isCurrent(my)) committed.push(v); });
    };
    const r1 = req(slow.promise);
    const r2 = req(fast.promise);
    fast.resolve("AFDB");
    await r2;
    slow.resolve("5ZIM");
    await r1;
    expect(committed).toEqual(["AFDB"]);
  });
});

describe("Mutex", () => {
  it("runs sections FIFO without interleaving async steps", async () => {
    const m = new Mutex();
    const log: string[] = [];
    const section = (id: string, ms: number) => m.run(async () => {
      log.push(`${id}:start`);
      await tick(ms);
      log.push(`${id}:end`);
      return id;
    });
    const out = await Promise.all([section("a", 15), section("b", 1), section("c", 5)]);
    expect(out).toEqual(["a", "b", "c"]);
    expect(log).toEqual(["a:start", "a:end", "b:start", "b:end", "c:start", "c:end"]);
    expect(m.size).toBe(0);
  });

  it("a rejected section reaches its caller only and does not block the queue", async () => {
    const m = new Mutex();
    const first = m.run(async () => { await tick(2); throw new Error("boom"); });
    const second = m.run(() => "ok");
    expect(m.size).toBe(2);
    await expect(first).rejects.toThrow("boom");
    await expect(second).resolves.toBe("ok");
    expect(m.size).toBe(0);
  });

  it("synchronous throws are also contained", async () => {
    const m = new Mutex();
    await expect(m.run(() => { throw new Error("sync"); })).rejects.toThrow("sync");
    await expect(m.run(() => 1)).resolves.toBe(1);
  });
});

describe("SingleFlight", () => {
  it("concurrent callers share one initialisation", async () => {
    const sf = new SingleFlight<object>();
    let starts = 0;
    const d = deferred<object>();
    const start = () => { starts++; return d.promise; };
    const p1 = sf.get(start);
    const p2 = sf.get(start);
    const p3 = sf.get(start);
    expect(starts).toBe(1);
    expect(sf.started).toBe(true);
    const obj = {};
    d.resolve(obj);
    const vals = await Promise.all([p1, p2, p3]);
    expect(vals.every((v) => v === obj)).toBe(true);
    expect(await sf.get(start)).toBe(obj);
    expect(starts).toBe(1);
  });

  it("resets after a failed initialisation so a retry can start again", async () => {
    const sf = new SingleFlight<string>();
    let starts = 0;
    await expect(sf.get(async () => { starts++; throw new Error("init failed"); })).rejects.toThrow("init failed");
    await tick();
    expect(sf.started).toBe(false);
    await expect(sf.get(async () => { starts++; return "viewer"; })).resolves.toBe("viewer");
    expect(starts).toBe(2);
  });
});
