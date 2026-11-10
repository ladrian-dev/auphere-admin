"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ConnectorTools } from "@/lib/backend/agent-connectors-types";
import type { AgentAgenda } from "@/lib/backend/agenda-types";
import { CAPACITY_KINDS } from "@/lib/backend/client-access";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 057 (historia 3; T030; requisitos 2.1–2.5 y 7.1–7.4;
 * `contracts/console-api.md` §3–§5) — la agenda de un agente: leerla, activarla
 * o desactivarla en el borrador y lo que puede hacer. Activarla con Reservas
 * apagado lo enciende para todo el cliente: la API lo hace bajo la RLS del
 * cliente de la ruta. Apagar Reservas no se puede desde aquí (7.4).
 *
 * Leer pide `agents:read`; cambiar, `agents:write` (owner, admin y builder). Los
 * esquemas son estrictos: el cliente y el agente salen de la ruta, nunca del
 * cuerpo (garantía 1). Encender o apagar una sola herramienta es
 * `setConnectorToolAction` (`connector-actions.ts`), la misma puerta que las demás.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();

async function partner(perm: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, perm)) return null;
  return principal;
}

/** La agenda cambia lo que puede hacer el agente: su pantalla, la lista de agentes y Acceso. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

const agentSchema = z.object({ ref, agent: uuid }).strict();

/** La agenda del agente: si se ofrece, el módulo, si está lista, el borrador y la propuesta. */
export async function agentAgendaAction(raw: unknown): Promise<ActionResult<AgentAgenda>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentAgenda(body.ref, body.agent));
}

const reservasSchema = z
  .object({ mode: z.enum(["services", "capacity"]), capacity_kind: z.enum(CAPACITY_KINDS).nullable().optional() })
  .strict();
const setSchema = z.object({ ref, agent: uuid, enabled: z.boolean(), reservas: reservasSchema.optional() }).strict();

/**
 * Activar o desactivar la agenda (2.2, 2.3, 2.5): las 9 de una vez en el
 * borrador. Con Reservas apagado, `reservas` dice cómo se reservará; sin él, la
 * API responde `reservas_mode_required`. Desactivar nunca apaga Reservas.
 */
export async function setAgentAgendaAction(raw: unknown): Promise<ActionResult<AgentAgenda>> {
  const body = setSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() =>
    backendFor(principal).setAgentAgenda(body.ref, body.agent, {
      enabled: body.enabled,
      ...(body.enabled && body.reservas ? { reservas: { mode: body.reservas.mode, capacity_kind: body.reservas.capacity_kind ?? null } } : {}),
    }),
  );
  if (res.ok) refresh(body.ref);
  return res;
}

const toolsSchema = z.object({ ref, agent: uuid, lang: z.enum(["es", "en"]) }).strict();

/** «Qué puede hacer» (2.4): las 9, con la forma de `ConnectorTools` para el mismo diálogo. */
export async function agendaToolsAction(raw: unknown): Promise<ActionResult<ConnectorTools>> {
  const body = toolsSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).agendaTools(body.ref, body.agent, body.lang));
}
