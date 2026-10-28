"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { AgentChannels, ChannelChange, ChannelPage, OwnerLink } from "@/lib/backend/channel-config-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historias 10 y 11; T111, T112, T114 y T115) — la página de cada
 * canal (guardar con la revisión que leyó la pantalla, deshacer durante 10
 * minutos, el historial), su menú ⋯ (pasar a otro agente, pausar y reanudar;
 * desconectar sigue en `channels/actions.ts`) y el enlace del dueño por agente
 * (crear, «Revocar y crear», revocar).
 *
 * `channels:read` para leer, `channels:write` para todo lo demás. La API vuelve
 * a validar y decide: sus códigos vuelven en `code` para que la pantalla los
 * diga con palabras. El enlace del dueño solo viaja en la respuesta de crearlo.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const channelSchema = z.object({ ref, channel: uuid });
const agentSchema = z.object({ ref, agent: uuid });

async function partner(permission: "channels:read" | "channels:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

/** El estado de un número sale en la tarjeta del agente, su pantalla y la lista de clientes. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

async function write<T>(r: string, fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await partner("channels:write");
  if (!principal) return forbidden;
  const res = await run(() => fn(backendFor(principal)));
  if (res.ok) refresh(r);
  return res;
}

export async function channelPageAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = channelSchema.parse(raw);
  const principal = await partner("channels:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getChannelPage(body.ref, body.channel));
}

export async function channelHistoryAction(raw: unknown): Promise<ActionResult<ChannelChange[]>> {
  const body = channelSchema.parse(raw);
  const principal = await partner("channels:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getChannelHistory(body.ref, body.channel));
}

// La API normaliza a E.164 y deduplica (32.4): aquí solo el tamaño.
const phone = z.string().trim().min(1).max(40);
const recipient = z.object({
  name: z.string().trim().min(1).max(80),
  via: z.enum(["whatsapp", "email", "inbox"]),
  phone_e164: z.string().trim().max(40).nullable().optional(),
  email: z.string().trim().max(320).nullable().optional(),
  client_user_id: z.string().max(160).nullable().optional(),
});
const configSchema = channelSchema.extend({
  revision: z.number().int().min(0),
  config: z.object({
    audience: z.object({
      mode: z.enum(["unset", "team_only", "everyone"]),
      test_numbers: z.array(phone).max(200),
      exceptions: z.array(phone).max(200),
    }),
    // 50 como la API: el límite de 10 lo dice ella con su código (33.1).
    escalation: z.object({ recipients: z.array(recipient).max(50), summary: z.boolean() }),
    wait_message: z.string().max(2000).nullable(),
  }),
});

/** Guardar con `If-Match`: `412 revision_conflict` con `current` y `changes` si otra persona guardó antes. */
export async function saveChannelConfigAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = configSchema.parse(raw);
  return write(body.ref, (api) => api.saveChannelConfig(body.ref, body.channel, body.revision, body.config));
}

/** Deshacer el último cambio, durante 10 minutos (`409 undo_window_closed` después). */
export async function undoChannelConfigAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = channelSchema.parse(raw);
  return write(body.ref, (api) => api.undoChannelConfig(body.ref, body.channel));
}

const moveSchema = channelSchema.extend({ to: uuid });

/** Pasar el número a otro agente (34.2): conserva su configuración y sus conversaciones. */
export async function moveChannelAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = moveSchema.parse(raw);
  return write(body.ref, (api) => api.moveChannel(body.ref, body.channel, body.to));
}

export async function pauseChannelAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = channelSchema.parse(raw);
  return write(body.ref, (api) => api.pauseChannel(body.ref, body.channel));
}

export async function resumeChannelAction(raw: unknown): Promise<ActionResult<ChannelPage>> {
  const body = channelSchema.parse(raw);
  return write(body.ref, (api) => api.resumeChannel(body.ref, body.channel));
}

// ── El enlace del dueño por agente (31) ─────────────────────────────────────

export async function agentChannelsAction(raw: unknown): Promise<ActionResult<AgentChannels>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("channels:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).listAgentChannels(body.ref, body.agent));
}

const linkSchema = agentSchema.extend({
  mode: z.enum(["coexistence", "cloud_api", "whatsapp_login"]),
  replace: z.boolean().optional(),
});

/**
 * Crear el enlace (31.1): la URL vuelve **solo** aquí. `409 link_pending_exists`
 * (con `link_id`) si ya hay uno: la pantalla ofrece «Revocar y crear»
 * (`replace: true`). `409 whatsapp_login_unavailable` fuera de la beta.
 */
export async function createOwnerLinkAction(raw: unknown): Promise<ActionResult<OwnerLink>> {
  const body = linkSchema.parse(raw);
  return write(body.ref, (api) => api.createOwnerLink(body.ref, body.agent, { mode: body.mode, ...(body.replace ? { replace: true } : {}) }));
}

const revokeSchema = agentSchema.extend({ link: uuid });

export async function revokeOwnerLinkAction(raw: unknown): Promise<ActionResult<null>> {
  const body = revokeSchema.parse(raw);
  return write(body.ref, (api) => api.revokeOwnerLink(body.ref, body.agent, body.link));
}
