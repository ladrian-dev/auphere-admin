import type { StoredSession } from "@/domain/types";
import { StoredSessionSchema } from "@/domain/validation";

export const SESSION_KEY = "amacrux-diagnostico:v1";

export type LoadResult =
  | { status: "empty" }
  | { status: "restored"; session: StoredSession }
  | { status: "discarded" };

let memoryFallback: string | null = null;

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    const s = window.sessionStorage;
    // Safari en modo privado puede exponer el objeto y lanzar al escribir.
    const probe = "__amacrux_probe__";
    s.setItem(probe, "1");
    s.removeItem(probe);
    return s;
  } catch {
    return null;
  }
}

function read(): string | null {
  const s = storage();
  if (s) {
    try {
      return s.getItem(SESSION_KEY);
    } catch {
      return memoryFallback;
    }
  }
  return memoryFallback;
}

function write(value: string | null): void {
  const s = storage();
  if (s) {
    try {
      if (value === null) s.removeItem(SESSION_KEY);
      else s.setItem(SESSION_KEY, value);
      return;
    } catch {
      // cae al fallback en memoria
    }
  }
  memoryFallback = value;
}

export function loadSession(): LoadResult {
  const raw = read();
  if (raw === null) return { status: "empty" };
  try {
    const parsed = StoredSessionSchema.safeParse(JSON.parse(raw));
    if (parsed.success) return { status: "restored", session: parsed.data };
  } catch {
    // JSON corrupto
  }
  write(null);
  return { status: "discarded" };
}

export function saveSession(session: StoredSession): void {
  const parsed = StoredSessionSchema.safeParse(session);
  if (!parsed.success) return; // nunca se guarda algo fuera de esquema (p. ej. un lead)
  write(JSON.stringify(parsed.data));
}

export function clearSession(): void {
  write(null);
}
