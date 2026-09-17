import { NextResponse } from "next/server";
import { Resend } from "resend";

import { LeadSchema } from "@/domain/validation";
import { destinationsMode, leadDeliveryConfig, leadStorageConfig, leadWebhookConfig } from "@/lib/env.server";
import { buildLeadEmail } from "@/lib/leads/email";
import { buildLeadRow, insertLead, markEmailDelivered, postLeadWebhook } from "@/lib/leads/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Entrega de leads. Contrato en specs/009-…/contracts/leads-api.md.
 * Destinos: base en Supabase (registro consultable) y correo por Resend
 * (aviso). Se guarda primero; si algún destino configurado funciona, 200.
 * Rate limit e idempotencia viven en memoria del proceso (límite conocido,
 * documentado en docs/CONFIG.md); el cliente además bloquea el doble envío.
 */
const WINDOW_MS = 10 * 60 * 1000;
/**
 * En un evento la sala entera comparte la IP pública del wifi. Un límite bajo
 * deja fuera a todos menos a los primeros, y como el resultado va detrás del
 * formulario, esa gente se va sin diagnóstico. Contra los bots están el
 * honeypot, la validación estricta y la idempotencia; esto es solo un tope.
 */
const MAX_PER_WINDOW = 60;
const hits = new Map<string, number[]>();
const processed = new Map<string, { at: number; body: Record<string, unknown> }>();

export function _resetForTests(): void {
  hits.clear();
  processed.clear();
}

function rateLimited(ip: string, now: number): boolean {
  const stamps = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  stamps.push(now);
  hits.set(ip, stamps);
  return stamps.length > MAX_PER_WINDOW;
}

function cached(key: string, now: number): Record<string, unknown> | null {
  const entry = processed.get(key);
  if (!entry) return null;
  if (now - entry.at > WINDOW_MS) {
    processed.delete(key);
    return null;
  }
  return entry.body;
}

function log(level: "info" | "error", outcome: string, extra: Record<string, unknown> = {}): void {
  // Nunca datos personales ni claves: solo campaña, rango, interés y resultado.
  console[level]("[leads]", { outcome, ...extra });
}

export async function POST(request: Request): Promise<NextResponse> {
  const now = Date.now();
  const ip = ((request.headers.get("x-forwarded-for") ?? "unknown").split(",")[0] ?? "unknown").trim();
  if (rateLimited(ip, now)) {
    log("info", "rate_limited");
    return NextResponse.json({ ok: false, error: "rate_limited" }, { status: 429 });
  }

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid", fields: {} }, { status: 400 });
  }
  const parsed = LeadSchema.safeParse(raw);
  if (!parsed.success) {
    const fields: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const key = String(issue.path[0] ?? "_");
      if (!fields[key]) fields[key] = issue.message;
    }
    log("info", "invalid", { fields: Object.keys(fields) });
    return NextResponse.json({ ok: false, error: "invalid", fields }, { status: 400 });
  }
  const lead = parsed.data;
  const meta = { campaign: lead.campaign, range: lead.resultSnapshot.range, interest: lead.interest };

  if (lead.fax && lead.fax.length > 0) {
    log("info", "honeypot", meta);
    return NextResponse.json({ ok: true });
  }

  const previous = cached(lead.idempotencyKey, now);
  if (previous) {
    log("info", "duplicate", meta);
    return NextResponse.json({ ...previous, duplicate: true });
  }

  const storage = leadStorageConfig();
  const delivery = leadDeliveryConfig();
  const mode = destinationsMode(storage, delivery);

  if (mode === "demo") {
    const body = { ok: true, stored: false, delivered: false, mode: "demo" };
    processed.set(lead.idempotencyKey, { at: now, body });
    log("info", "demo", meta);
    return NextResponse.json(body);
  }
  if (mode === "misconfigured") {
    log("error", "misconfigured", meta);
    return NextResponse.json({ ok: false, error: "unavailable" }, { status: 503 });
  }

  // 1) Registro en la base (lo prioritario).
  const row = buildLeadRow(lead, { mode: "live" });
  let stored = false;
  if (storage.enabled) {
    try {
      await insertLead(storage, row);
      stored = true;
    } catch (e) {
      log("error", "store_failed", { ...meta, reason: e instanceof Error ? e.message : "unknown" });
    }
  }

  // 2) Aviso por correo.
  let delivered = false;
  let emailId: string | undefined;
  if (delivery.mode === "live") {
    try {
      const email = buildLeadEmail(lead, new Date(now));
      const resend = new Resend(delivery.apiKey);
      const { data, error } = await resend.emails.send({ from: delivery.from, to: delivery.to, replyTo: lead.email, subject: email.subject, text: email.text, html: email.html });
      if (error || !data) log("error", "email_failed", { ...meta, reason: error?.message });
      else {
        delivered = true;
        emailId = data.id;
      }
    } catch (e) {
      log("error", "email_failed", { ...meta, reason: e instanceof Error ? e.message : "unknown" });
    }
  } else if (delivery.mode === "misconfigured") {
    log("error", "email_misconfigured", meta);
  }

  // 3) Anotar en la fila que el correo salió (best-effort).
  if (stored && storage.enabled && emailId) {
    try {
      await markEmailDelivered(storage, lead.idempotencyKey, emailId);
    } catch {
      log("error", "store_mark_failed", meta);
    }
  }

  if (!stored && !delivered) {
    return NextResponse.json({ ok: false, error: "delivery_failed" }, { status: 502 });
  }

  // 4) Copia a la hoja de cálculo (webhook), best-effort.
  const webhook = leadWebhookConfig();
  let sheet: boolean | undefined;
  if (webhook.enabled) {
    try {
      await postLeadWebhook(webhook, row);
      sheet = true;
    } catch (e) {
      sheet = false;
      log("error", "sheet_failed", { ...meta, reason: e instanceof Error ? e.message : "unknown" });
    }
  }
  const body: Record<string, unknown> = { ok: true, stored, delivered, mode: "live" };
  if (sheet !== undefined) body.sheet = sheet;
  if (emailId) body.id = emailId;
  processed.set(lead.idempotencyKey, { at: now, body });
  log("info", stored && (delivered || delivery.mode !== "live") ? "delivered" : "partial", { ...meta, stored, delivered });
  return NextResponse.json(body);
}
