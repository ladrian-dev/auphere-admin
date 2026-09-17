import type { Lead } from "@/domain/types";

export type LeadErrorKind = "invalid" | "rate_limited" | "unavailable" | "delivery_failed" | "network" | "timeout";

export class LeadSubmitError extends Error {
  constructor(
    public readonly kind: LeadErrorKind,
    public readonly fields?: Record<string, string>,
  ) {
    super(kind);
    this.name = "LeadSubmitError";
  }
  /** Los 4xx de validación no se reintentan tal cual; el resto sí. */
  get retryable(): boolean {
    return this.kind !== "invalid";
  }
}

/** Qué pasó con el contacto: entregado, simulado, o no llegó a ninguna parte. */
export type DeliveryOutcome = "delivered" | "demo" | "failed";

export interface SaveOutcome {
  delivered: boolean;
  /** Guardado en la base de leads (Supabase). */
  stored?: boolean;
  duplicate?: boolean;
  mode?: "demo" | "live";
}

export interface LeadRepository {
  saveLead(lead: Lead): Promise<SaveOutcome>;
}

/** Desarrollo/demostración sin servidor: registra un aviso sin datos personales. */
export class LocalLeadRepository implements LeadRepository {
  async saveLead(lead: Lead): Promise<SaveOutcome> {
    console.info("[leads:local]", { campaign: lead.campaign, interest: lead.interest, range: lead.resultSnapshot.range });
    return { delivered: false, mode: "demo" };
  }
}

/** Envío al Route Handler del mismo origen. */
export class HttpLeadRepository implements LeadRepository {
  constructor(
    private readonly endpoint = "/api/leads",
    private readonly timeoutMs = 12_000,
    private readonly fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  async saveLead(lead: Lead): Promise<SaveOutcome> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await this.fetchImpl(this.endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(lead),
        signal: controller.signal,
      });
    } catch (e) {
      throw new LeadSubmitError(e instanceof Error && e.name === "AbortError" ? "timeout" : "network");
    } finally {
      clearTimeout(timer);
    }
    const body = (await res.json().catch(() => ({}))) as { ok?: boolean; delivered?: boolean; stored?: boolean; duplicate?: boolean; mode?: "demo" | "live"; error?: string; fields?: Record<string, string> };
    if (res.ok && body.ok) return { delivered: body.delivered ?? false, stored: body.stored ?? false, duplicate: body.duplicate, mode: body.mode };
    if (res.status === 400) throw new LeadSubmitError("invalid", body.fields);
    if (res.status === 429) throw new LeadSubmitError("rate_limited");
    if (res.status === 503) throw new LeadSubmitError("unavailable");
    throw new LeadSubmitError("delivery_failed");
  }
}

export function defaultLeadRepository(): LeadRepository {
  return new HttpLeadRepository();
}
