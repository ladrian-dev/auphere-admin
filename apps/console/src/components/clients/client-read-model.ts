import type { MessageKey } from "@/i18n/messages";
import type { Job } from "@/lib/backend";
import type { ClientRead, Network, ReadFailure, ReadResult } from "@/lib/backend/clients-v2";

/**
 * Spec 047 (T050, requisitos 5.5, 5.7 y 14.7) — qué dice la tarjeta de lectura
 * del Panel según el trabajo `client_read`. Puro: el componente solo pinta.
 *
 * - **leyendo**: el trabajo está en cola o en marcha;
 * - **hecho**: lo encontrado, «Leído de la web · revísalo», con «Revisar»; si
 *   alguna red no se dejó leer, se dice cuál;
 * - **fallido**: el motivo, con «Reintentar» (el cliente sigue usable);
 * - **nada**: sin web ni redes no hay tarjeta (el Panel dice lo que falta).
 */

export type ReadView =
  | { kind: "none" }
  | { kind: "reading"; site: string | null; pages: number }
  | { kind: "done"; site: string | null; result: ReadResult; blocked: Network[] }
  | { kind: "failed"; site: string | null; reason: ReadFailure | "other" };

const KNOWN: ReadonlySet<string> = new Set(["unreachable", "blocked", "no_text", "too_large", "extract_failed", "timeout", "nothing_to_read"]);

function pagesOf(job: Job): number {
  const blocks = Array.isArray(job.progress?.blocks) ? (job.progress.blocks as Record<string, unknown>[]) : [];
  const pages = blocks.find((b) => b.key === "pages");
  return typeof pages?.read === "number" ? pages.read : 0;
}

export function readView(data: ClientRead | null): ReadView {
  if (!data?.job || data.job.kind !== "client_read") return { kind: "none" };
  const { job, website } = data;
  if (job.status === "queued" || job.status === "running") return { kind: "reading", site: website, pages: pagesOf(job) };
  if (job.status === "failed") {
    const code = job.error_code ?? "";
    return { kind: "failed", site: website, reason: KNOWN.has(code) ? (code as ReadFailure) : "other" };
  }
  const result = (job.result ?? {}) as Partial<ReadResult>;
  const full: ReadResult = {
    website: result.website ?? website,
    sources: result.sources ?? [],
    found: { locations: 0, hours: 0, services: 0, policies: 0, faqs: 0, links: 0, ...result.found },
    applied: result.applied ?? 0,
    suggested: result.suggested ?? 0,
    translated_from: result.translated_from ?? null,
  };
  const blocked = full.sources.filter((s) => s.status === "failed").map((s) => s.network);
  return { kind: "done", site: full.website ?? website, result: full, blocked };
}

export function isLive(view: ReadView): boolean {
  return view.kind === "reading";
}

/** La espera creciente de `contracts/console-api.md`: 1, 2, 4… hasta 10 s. */
export function pollDelay(attempt: number): number {
  return Math.min(10_000, 1000 * 2 ** Math.max(0, attempt));
}

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** «2 sedes, el horario, 12 servicios y 3 preguntas frecuentes». Vacío si no hay nada. */
export function foundSummary(found: ReadResult["found"], t: T): string {
  const parts: string[] = [];
  const counted = (n: number, one: MessageKey, other: MessageKey) => {
    if (n === 1) parts.push(t(one));
    else if (n > 1) parts.push(t(other, { n }));
  };
  counted(found.locations, "business.read.found.locations.one", "business.read.found.locations.other");
  if (found.hours > 0) parts.push(t("business.read.found.hours"));
  counted(found.services, "business.read.found.services.one", "business.read.found.services.other");
  if (found.policies > 0) parts.push(t("business.read.found.policies"));
  counted(found.faqs, "business.read.found.faqs.one", "business.read.found.faqs.other");
  counted(found.links, "business.read.found.links.one", "business.read.found.links.other");
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")}${t("business.read.and")}${parts[parts.length - 1]}`;
}

export function languageName(locale: string, code: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}
