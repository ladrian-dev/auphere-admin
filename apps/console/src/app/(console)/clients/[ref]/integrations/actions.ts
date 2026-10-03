"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ConnectorOut, ConnectorSyncOut, ConsentOut } from "@/lib/backend/agent-tools";
import type { AgendaProPublicUrlOut } from "@/lib/backend/agent-tools-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Integraciones (spec 017, R4). Las escrituras de conector, que hasta ahora
 * vivían con la lista blanca en `tools/actions.ts` porque compartían pantalla.
 *
 * **Todas revalidan la ficha entera, no solo esta pestaña** (R4.3). Conectar
 * una integración cambia lo que Capacidades puede decir de sí misma: lo que
 * estaba encendido y no funcionaba pasa a funcionar, y el aviso de arriba
 * desaparece. Revalidar solo `/integrations` dejaba esa otra pantalla
 * mintiendo hasta que alguien recargara a mano.
 */

const ref = z.string().min(1).max(255);
const slug = z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/);

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}

/** La ficha entera: Integraciones, Capacidades y la barra de borrador. */
function revalidateRecord(r: string): void {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

export async function startConsentAction(raw: unknown): Promise<ActionResult<ConsentOut>> {
  const body = z.object({ ref, slug }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).startConsent(body.ref, body.slug));
  if (res.ok) revalidateRecord(body.ref);
  return res;
}

export async function syncConnectorAction(raw: unknown): Promise<ActionResult<ConnectorSyncOut>> {
  const body = z.object({ ref, slug }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).syncConnector(body.ref, body.slug));
  if (res.ok) revalidateRecord(body.ref);
  return res;
}

export async function connectorStatusAction(raw: unknown): Promise<ActionResult<ConnectorOut>> {
  const body = z.object({ ref, slug, op: z.enum(["pause", "resume", "disconnect"]) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const api = backendFor(principal);
  const fn =
    body.op === "pause"
      ? api.pauseConnector
      : body.op === "resume"
        ? api.resumeConnector
        : api.disconnectConnector;
  const res = await run(() => fn(body.ref, body.slug));
  if (res.ok) revalidateRecord(body.ref);
  return res;
}

export async function connectApiKeyAction(raw: unknown): Promise<ActionResult<ConnectorOut>> {
  const body = z
    .object({
      ref,
      slug,
      secrets: z
        .record(z.string().min(1).max(64), z.string().min(1).max(4096))
        .refine((s) => Object.keys(s).length >= 1 && Object.keys(s).length <= 20),
      endpoint_meta: z
        .record(z.string().min(1).max(64), z.string().max(2048))
        .refine((m) => Object.keys(m).length <= 20),
    })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() =>
    backendFor(principal).connectApiKey(body.ref, body.slug, {
      secrets: body.secrets,
      endpoint_meta: body.endpoint_meta,
    }),
  );
  if (res.ok) revalidateRecord(body.ref);
  return res;
}

/** Spec 016 (R6): enlazar o desenlazar la agenda pública del cliente. Nunca credenciales. */
export async function setAgendaProUrlAction(
  raw: unknown,
): Promise<ActionResult<AgendaProPublicUrlOut>> {
  const body = z.object({ ref, public_url: z.string().max(500).nullable() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).setAgendaProUrl(body.ref, body.public_url));
  if (res.ok) revalidateRecord(body.ref);
  return res;
}
