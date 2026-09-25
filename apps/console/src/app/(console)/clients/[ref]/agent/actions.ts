"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { consolePolicySchema } from "@/components/agent-tools/settings-schema";
import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { AgentVersion, DraftDiff } from "@/lib/backend";
import type { AgentSettingsSaved, ConsolePolicy } from "@/lib/backend/agent-tools";
import type { ClientModel } from "@/lib/backend/models";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `agent-tools` — structured settings (CP-11 / CP-31).
 *  Zod on the server (same schema as the form), `run()` for backend errors,
 *  `can()` before the write. */

const ref = z.string().min(1).max(255);

export async function saveAgentSettingsAction(raw: unknown): Promise<ActionResult<AgentSettingsSaved>> {
  const body = z.object({ ref, settings: consolePolicySchema }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).putAgentSettings(body.ref, body.settings as ConsolePolicy));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/agent`, "layout");
  return res;
}

/**
 * Spec 016 (R5.2): the client's ``respond`` model. Takes effect on the
 * next turn — no publish involved — so the toast says exactly that.
 */
export async function saveModelAction(raw: unknown): Promise<ActionResult<ClientModel>> {
  const body = z.object({ ref, model_id: z.string().min(1).max(64) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).setClientModel(body.ref, body.model_id));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/agent`, "layout");
  return res;
}

/**
 * Spec 017 (R3.2): qué cambia el borrador respecto a la versión que
 * atiende. Leer es leer — un analista que no puede publicar sí tiene que
 * poder ver lo que otro dejó preparado.
 */
export async function draftDiffAction(raw: unknown): Promise<ActionResult<DraftDiff>> {
  const body = z.object({ ref }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) return { ok: false, status: 403, message: "forbidden" };
  return run(() => backendFor(principal).getDraftDiff(body.ref));
}

/**
 * Spec 017 (R3.3): publicar desde la barra del borrador, esté el partner en
 * la pestaña que esté. El mismo acto que publicar desde «Agente», pero la
 * auditoría distingue de dónde salió; sin eso no hay forma de saber si la
 * barra sirve para algo.
 */
export async function publishFromBarAction(raw: unknown): Promise<ActionResult<AgentVersion>> {
  const body = z.object({ ref, version: z.number().int().positive() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).publishAgentVersion(body.ref, body.version, "draft_bar"));
  // La barra vive en el layout de la ficha: al publicar tiene que
  // desaparecer de TODAS las pestañas, no solo de la que estaba abierta.
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}
