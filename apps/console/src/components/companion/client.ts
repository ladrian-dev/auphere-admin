/**
 * Lado navegador del Companion en la consola (CO-03): el transporte de
 * `fetch` contra el BFF `app/api/companion/*` y el cliente que el paquete
 * construye encima (spec 003, T023). Lo que queda aquí es lo que solo tiene
 * sentido en la consola: el ancho y el modo del cajón como estado persistido.
 */
import {
  cacheRunIds,
  createFetchTransport,
  loadRunIds,
  makeCompanionClient,
  rememberRunId,
} from "@nexus/companion-ui";
export type { Err, Ok, Result } from "@nexus/companion-ui";

export const companionTransport = createFetchTransport("/api/companion");
export const companionClient = makeCompanionClient(companionTransport);
export { cacheRunIds, loadRunIds, rememberRunId };

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

