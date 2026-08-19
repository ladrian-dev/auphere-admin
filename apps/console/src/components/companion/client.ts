/**
 * Browser side of the Companion (CO-03): `fetch` against the BFF under
 * `app/api/companion/*`. Never throws — every call returns a discriminated
 * result, because a drawer that throws takes the whole console shell down
 * with it.
 *
 * `status` and `code` are carried through deliberately. The confirmation
 * card has to tell 409 `action_expired` ("you ran out of time") from 412
 * `state_changed` ("someone changed this while you were deciding"): §4.2
 * of the contract says they are different causes with the same way out,
 * and a single "it failed" would leave the user guessing which.
 */
import type {
  CompanionAction,
  CompanionBudget,
  CompanionDecision,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionThread,
  CompanionThreadRuns,
} from "@/lib/backend/companion";

import type { PageContext } from "./page-context";

export type Ok<T> = { ok: true; data: T };
export type Err = { ok: false; status: number; detail: string; code: string | null };
export type Result<T> = Ok<T> | Err;

const base = "/api/companion";

async function call<T>(path: string, init?: RequestInit): Promise<Result<T>> {
  try {
    const res = await fetch(`${base}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
      cache: "no-store",
    });
    if (res.status === 204) return { ok: true, data: null as T };
    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    if (!res.ok) {
      const b = body as { detail?: unknown; code?: unknown } | null;
      return {
        ok: false,
        status: res.status,
        detail: b && typeof b.detail === "string" ? b.detail : `HTTP ${res.status}`,
        code: b && typeof b.code === "string" ? b.code : null,
      };
    }
    return { ok: true, data: body as T };
  } catch {
    // Offline, DNS, aborted — indistinguishable here and all mean the same
    // to the user: we could not reach the Companion.
    return { ok: false, status: 0, detail: "network", code: null };
  }
}

export const companionClient = {
  listThreads: () => call<CompanionThread[]>("/threads"),
  createThread: (body: { title?: string; client_ref?: string; mode?: "consult" | "build" }) =>
    call<CompanionThread>("/threads", { method: "POST", body: JSON.stringify(body) }),
  patchThread: (id: string, body: { title?: string; archived?: boolean; mode?: "consult" | "build" }) =>
    call<CompanionThread>(`/threads/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  /** Runs of a thread, ascending (§5.2) — the source of the run index. */
  threadRuns: (threadId: string) => call<CompanionThreadRuns>(`/threads/${encodeURIComponent(threadId)}/runs`),
  startRun: (threadId: string, prompt: string, pageContext: PageContext | null) =>
    call<CompanionRunStarted>(`/threads/${encodeURIComponent(threadId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ prompt, page_context: pageContext }),
    }),
  runEvents: (runId: string, sinceSeq = 0) =>
    call<CompanionEvents>(`/runs/${encodeURIComponent(runId)}/events?since_seq=${sinceSeq}`),
  /** The ONLY way to stop a run. Aborting the stream does not reach the API. */
  cancelRun: (runId: string) => call<null>(`/runs/${encodeURIComponent(runId)}`, { method: "DELETE" }),
  resumeRun: (runId: string, body: { action_id: string; decision: CompanionDecision; note?: string }) =>
    call<CompanionResumed>(`/runs/${encodeURIComponent(runId)}/resume`, { method: "POST", body: JSON.stringify(body) }),
  getAction: (actionId: string) => call<CompanionAction>(`/actions/${encodeURIComponent(actionId)}`),
  budget: () => call<CompanionBudget>("/budget"),
  streamUrl: (runId: string, sinceSeq: number) =>
    `${base}/runs/${encodeURIComponent(runId)}/stream?since_seq=${sinceSeq}`,
};

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

const WIDTH_KEY = "nexus.companion.width";
const MODE_KEY = "nexus.companion.mode";
const RUNS_KEY = (threadId: string) => `nexus.companion.runs.${threadId}`;

export const MIN_WIDTH = 380;
export const MAX_WIDTH = 880;
export const DEFAULT_WIDTH = 480;

export function loadWidth(): number {
  const raw = read(WIDTH_KEY);
  const n = raw ? Number.parseInt(raw, 10) : Number.NaN;
  if (!Number.isFinite(n)) return DEFAULT_WIDTH;
  return clampWidth(n);
}
export function saveWidth(px: number): void {
  write(WIDTH_KEY, String(clampWidth(px)));
}
export function clampWidth(px: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(px)));
}

export function loadMode(): "consult" | "build" {
  // Consult is safe by omission: read-only tools. Anything unreadable in
  // storage falls back to it rather than to the mode that can write.
  return read(MODE_KEY) === "build" ? "build" : "consult";
}
export function saveMode(mode: "consult" | "build"): void {
  write(MODE_KEY, mode);
}

// ── the persisted UI state as an external store ────────────────────────
//
// Width and mode live in `localStorage`, which is an external system, so
// they are read through `useSyncExternalStore` rather than copied into
// React state inside an effect. Two things fall out of that and both are
// wanted: the server snapshot is the default (so hydration matches, and
// nothing flashes at a wrong width), and a second tab that changes the
// width updates this one through the `storage` event.

type Listener = () => void;
const listeners = new Set<Listener>();
let widthCache: number | null = null;
let modeCache: "consult" | "build" | null = null;

function emit(): void {
  for (const l of listeners) l();
}

export function subscribeUi(listener: Listener): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === WIDTH_KEY) widthCache = null;
    if (e.key === MODE_KEY) modeCache = null;
    listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Cached: `getSnapshot` must be referentially stable between renders. */
export function getWidth(): number {
  if (widthCache === null) widthCache = loadWidth();
  return widthCache;
}
export function getWidthServer(): number {
  return DEFAULT_WIDTH;
}
export function setWidth(px: number): void {
  const next = clampWidth(px);
  if (next === widthCache) return;
  widthCache = next;
  saveWidth(next);
  emit();
}

export function getMode(): "consult" | "build" {
  if (modeCache === null) modeCache = loadMode();
  return modeCache;
}
export function getModeServer(): "consult" | "build" {
  return "consult";
}
export function setMode(mode: "consult" | "build"): void {
  if (mode === modeCache) return;
  modeCache = mode;
  saveMode(mode);
  emit();
}

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
