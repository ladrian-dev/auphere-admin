import type { MessageKey } from "@/i18n/messages";
import type { Job } from "@/lib/backend";
import type { ClientRead, Network, NetworkRead, NetworkReadStatus, ReadFailure, ReadResult } from "@/lib/backend/clients-v2";

/**
 * Spec 047 (T050, requisitos 5.5, 5.7 y 14.7) — qué dice la tarjeta de lectura
 * del Panel según el trabajo `client_read`. Puro: el componente solo pinta.
 *
 * - **leyendo**: el trabajo está en cola o en marcha;
 * - **hecho**: lo encontrado, lo que falta revisar con «Revisar» y, por red, lo
 *   que se leyó, la que no deja leer perfiles sin cuenta (que no es un fallo,
 *   59.4) y la que falló, con su motivo (59.7);
 * - **fallido**: el motivo, con «Reintentar» (el cliente sigue usable);
 * - **nada**: sin web ni redes no hay tarjeta (el Panel dice lo que falta).
 */

/** Cómo fue una red, con el motivo ya del vocabulario de la consola. */
export type NetworkLine = { network: Network; status: NetworkReadStatus; reason: ReadFailure | "other" | null };

export type ReadView =
  | { kind: "none" }
  | { kind: "reading"; site: string | null; pages: number }
  | { kind: "done"; site: string | null; result: ReadResult; networks: NetworkLine[]; toReview: number; structured: boolean }
  | { kind: "failed"; site: string | null; reason: ReadFailure | "other"; networks: NetworkLine[] };

const KNOWN: ReadonlySet<string> = new Set(["unreachable", "blocked", "no_text", "too_large", "extract_failed", "timeout", "nothing_to_read"]);
const STATUSES: ReadonlySet<string> = new Set(["read", "blocked_by_network", "failed"]);

function isNetworkRead(value: unknown): value is NetworkRead {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return typeof v.network === "string" && typeof v.status === "string" && STATUSES.has(v.status);
}

function reasonOf(code: unknown): ReadFailure | "other" {
  return typeof code === "string" && KNOWN.has(code) ? (code as ReadFailure) : "other";
}

/**
 * Las redes de la enmienda (59.4): las de `GET …/business/read` si ya traen su
 * estado; si no, las del `result` del trabajo; y, para una lectura de antes,
 * las fuentes fallidas de siempre (un «blocked» de una red social es que no
 * deja leer, no un fallo).
 */
export function networkLines(data: ClientRead): NetworkLine[] {
  const result = (data.job?.result ?? {}) as Record<string, unknown>;
  const fromTop = (data.networks ?? []).filter(isNetworkRead);
  const fromJob = Array.isArray(result.networks) ? (result.networks as unknown[]).filter(isNetworkRead) : [];
  const fresh = fromTop.length ? fromTop : fromJob;
  if (fresh.length) {
    return fresh.map((n) => ({ network: n.network, status: n.status, reason: n.status === "failed" ? reasonOf(n.reason) : null }));
  }
  const sources = Array.isArray(result.sources) ? (result.sources as ReadResult["sources"]) : [];
  return sources
    .filter((s) => s.status === "failed")
    .map((s) =>
      s.failure === "blocked" && s.network !== "web"
        ? { network: s.network, status: "blocked_by_network" as const, reason: null }
        : { network: s.network, status: "failed" as const, reason: reasonOf(s.failure) },
    );
}

function structuredOf(data: ClientRead): boolean {
  if (typeof data.structured === "boolean") return data.structured;
  return (data.job?.result as Record<string, unknown> | null)?.structured === true;
}

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
    return { kind: "failed", site: website, reason: reasonOf(job.error_code), networks: networkLines(data) };
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
  return {
    kind: "done",
    site: full.website ?? website,
    result: full,
    networks: networkLines(data),
    // Lo aplicado queda «Leído de la web · revísalo» y lo propuesto, al lado: las dos cosas se revisan.
    toReview: Math.max(0, full.applied) + Math.max(0, full.suggested),
    structured: structuredOf(data),
  };
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
