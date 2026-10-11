/**
 * Small async-control primitives for the structure viewer (PR-3a). Pure TypeScript, no Mol*:
 * unit tested in tests/unit/loadControl.test.ts.
 *
 * - Generations: monotonic request ids; only the latest request may commit UI state.
 * - Mutex: FIFO serialisation of critical sections (all Mol* state changes), so two loads can never
 *   interleave their clear/build steps and an older build can never finish after a newer one.
 * - SingleFlight: one shared initialisation promise (one Mol* plugin per viewer), reset on failure
 *   so that a later attempt can retry.
 */

export class Generations {
  private n = 0;
  /** Start a new request; every earlier request becomes stale. */
  next(): number {
    return ++this.n;
  }
  isCurrent(g: number): boolean {
    return g === this.n;
  }
  /** Make every outstanding request stale (e.g. on unmount). */
  invalidate(): void {
    this.n++;
  }
}

export class Mutex {
  private tail: Promise<unknown> = Promise.resolve();
  private pending = 0;
  run<T>(fn: () => Promise<T> | T): Promise<T> {
    this.pending++;
    const result = this.tail.then(() => fn());
    // Keep the chain alive whatever fn does; errors are reported to the caller only.
    this.tail = result.then(
      () => { this.pending--; },
      () => { this.pending--; },
    );
    return result;
  }
  /** Number of sections queued or running (diagnostics and tests). */
  get size(): number {
    return this.pending;
  }
}

export class SingleFlight<T> {
  private p: Promise<T> | null = null;
  get(start: () => Promise<T>): Promise<T> {
    if (!this.p) {
      const p = start();
      this.p = p;
      p.catch(() => {
        if (this.p === p) this.p = null;
      });
    }
    return this.p;
  }
  get started(): boolean {
    return this.p !== null;
  }
}
