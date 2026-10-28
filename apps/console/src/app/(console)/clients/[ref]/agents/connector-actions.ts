"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  Activation,
  AffectedSkills,
  AgentConnector,
  ConnectionPage,
  ConnectResult,
  ConnectConsent,
  Disconnected,
} from "@/lib/backend/agent-connectors-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historia 21; T129; requisitos 35 y 36) — los conectores de un
 * agente: leer su catálogo, conectar y activar en un paso, cambiar el permiso y
 * los ajustes, quitarlo de un agente; y la página de cada conexión con
 * «Reconectar» y «Desconectar para todos».
 *
 * Leer pide `agents:read`; lo demás, `agents:write`. La API vuelve a validar los
 * ajustes con el esquema del catálogo y decide: sus códigos vuelven en `code`
 * para que la pantalla los diga con palabras. Nunca viajan credenciales: la
 * clave de un conector se guarda con `integrations/actions.ts`.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const slug = z.string().regex(/^[a-z0-9][a-z0-9_-]{0,79}$/);
const permission = z.enum(["read", "ask_before_write", "read_write"]);
/** Los ajustes los valida la API con el esquema del catálogo (36.2); aquí solo el tamaño. */
const settings = z.record(z.string().min(1).max(64), z.unknown()).refine((s) => JSON.stringify(s).length <= 8000, { message: "settings_too_large" });

async function partner(perm: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, perm)) return null;
  return principal;
}

/** Un conector cambia lo que puede hacer el agente: su pantalla, la del cliente y Conectores. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

async function write<T>(r: string, fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => fn(backendFor(principal)));
  if (res.ok) refresh(r);
  return res;
}

const agentSchema = z.object({ ref, agent: uuid });

export async function agentConnectorsAction(raw: unknown): Promise<ActionResult<AgentConnector[]>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).listAgentConnectors(body.ref, body.agent));
}

const connectSchema = agentSchema.extend({ slug, permission });

/**
 * «Conectar» (35.3, 35.4): si ya está autorizado para el cliente, se activa sin
 * pedirlo otra vez; si es OAuth, vuelve la URL de la autorización y se activa al
 * terminarla; si pide una clave, `409 authorize_with_form` con el formulario.
 */
export async function connectConnectorAction(raw: unknown): Promise<ActionResult<ConnectResult>> {
  const body = connectSchema.parse(raw);
  return write(body.ref, (api) => api.connectConnector(body.ref, { integration: body.slug, agent_id: body.agent, permission: body.permission }));
}

const activationSchema = agentSchema.extend({ slug, permission, settings: settings.default({}) });

/** El permiso y los ajustes de este agente (35.5, 36.2). La conexión tiene que estar autorizada. */
export async function setActivationAction(raw: unknown): Promise<ActionResult<Activation>> {
  const body = activationSchema.parse(raw);
  return write(body.ref, (api) => api.setActivation(body.ref, body.agent, body.slug, { permission: body.permission, settings: body.settings }));
}

const removeSchema = agentSchema.extend({ slug });

/** Quitar el conector de este agente: dice qué habilidades y procedimientos se quedan sin él (35.7). */
export async function removeActivationAction(raw: unknown): Promise<ActionResult<AffectedSkills>> {
  const body = removeSchema.parse(raw);
  return write(body.ref, (api) => api.removeActivation(body.ref, body.agent, body.slug));
}

// ── La página de cada conexión (36) ─────────────────────────────────────────

const connectionSchema = z.object({ ref, connection: uuid });

export async function connectionPageAction(raw: unknown): Promise<ActionResult<ConnectionPage>> {
  const body = connectionSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getConnectionPage(body.ref, body.connection));
}

/** «Reconectar»: vuelve a pedir la autorización. Las activaciones se quedan. */
export async function reconnectConnectionAction(raw: unknown): Promise<ActionResult<ConnectConsent>> {
  const body = connectionSchema.parse(raw);
  return write(body.ref, (api) => api.reconnectConnection(body.ref, body.connection));
}

const disconnectSchema = connectionSchema.extend({ confirm: z.boolean() });

/** «Desconectar para todos» (36.4): sin `confirm`, lo afectado (`409 confirm_required`). */
export async function disconnectConnectionAction(raw: unknown): Promise<ActionResult<Disconnected>> {
  const body = disconnectSchema.parse(raw);
  return write(body.ref, (api) => api.disconnectConnection(body.ref, body.connection, body.confirm));
}
