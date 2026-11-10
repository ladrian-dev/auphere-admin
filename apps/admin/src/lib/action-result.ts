/**
 * Spec 047 (T150): how a server action of the catalog, router and
 * certification screens says it failed. A refusal of the API keeps its `code`
 * (the screen words it), the gate's list of what is missing, and the API's own
 * sentence when the screen has none.
 */
import { BackendError } from "@/lib/backend";

export type Failure = {
  ok: false;
  error: string;
  code?: string;
  /** From the activation gate: code → what is missing, in words. */
  missing?: Record<string, string>;
};
export type Result<T> = { ok: true; data: T } | Failure;

export function toFailure(err: unknown, words: Record<string, string> = {}): Failure {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const d = detail as { code: unknown; messages?: unknown; message?: unknown };
      const code = String(d.code);
      const missing =
        d.messages && typeof d.messages === "object" ? (d.messages as Record<string, string>) : undefined;
      const message = typeof d.message === "string" ? d.message : undefined;
      return { ok: false, error: words[code] ?? message ?? code, code, ...(missing ? { missing } : {}) };
    }
    if (err.status === 422) return { ok: false, error: "Revisa los campos: la API no los acepta." };
    return { ok: false, error: `La API respondió ${err.status}.` };
  }
  return { ok: false, error: err instanceof Error ? err.message : String(err) };
}
