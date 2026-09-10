// ── local persistence ──────────────────────────────────────────────────
//
// Everything here is a browser convenience and degrades to "we do not
// know" rather than to a wrong answer. `localStorage` throws in private
// mode and in some embedded webviews, so every access is guarded.

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode — the feature degrades, it does not break */
  }
}

const RUNS_KEY = (threadId: string) => `nexus.companion.runs.${threadId}`;

/**
 * Cached run ids of a thread — **a cache, not the source**.
 *
 * The source is `GET /console/companion/threads/{id}/runs` (§5.2 of the
 * contract, added in v1.1). This cache exists for one reason: if that call
 * fails, the drawer can still rebuild whatever this browser saw before,
 * instead of showing an empty conversation. It is a degraded path, never
 * the norm — and it must not be trusted over the server, because a run
 * started on another machine would be missing from it.
 */
export function loadRunIds(threadId: string): string[] {
  const raw = read(RUNS_KEY(threadId));
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function rememberRunId(threadId: string, runId: string): string[] {
  const current = loadRunIds(threadId);
  if (current.includes(runId)) return current;
  // Bounded: a long-lived thread must not grow the key without limit.
  const next = [...current, runId].slice(-40);
  write(RUNS_KEY(threadId), JSON.stringify(next));
  return next;
}

/** Overwrite the cache with what the server just said is authoritative. */
export function cacheRunIds(threadId: string, runIds: string[]): void {
  write(RUNS_KEY(threadId), JSON.stringify(runIds.slice(-40)));
}
