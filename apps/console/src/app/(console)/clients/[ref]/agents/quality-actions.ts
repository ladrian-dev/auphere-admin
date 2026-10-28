"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  AgentReview,
  HistoryEntry,
  PlaygroundReply,
  PlaygroundSession,
  PublishPreview,
  QualityJob,
  RestoreResult,
  TestRunAccepted,
  TestSuite,
} from "@/lib/backend/agent-quality-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historias 8 y 9; T089 y T094) — las acciones de la pantalla del
 * agente entre el borrador y los clientes de verdad: el playground, las
 * pruebas, la revisión, «Guardar», deshacer, el historial y restaurar.
 *
 * Leer pide `agents:read` (quien solo lee lo ve todo, 20.5); escribir, probar
 * y guardar, `agents:write`. Saltar la puerta es de owner o admin: la API lo
 * decide (`override_forbidden`) y la pantalla ni siquiera lo ofrece a los demás
 * (§V). Zod aquí con los límites de la API; sus códigos vuelven en `code`.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });

async function partner(permission: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

/** La pestaña Agentes y el marco del cliente dicen si hay borrador o versión. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

// ── el playground (requisito 20) ────────────────────────────────────────────

/** Una hora simulada en la zona del negocio: `2026-10-27T11:20` o con su desfase. */
const localTime = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/);

export async function playgroundSessionsAction(raw: unknown): Promise<ActionResult<PlaygroundSession[]>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).listPlaygroundSessions(body.ref, body.agent));
}

const openSchema = agentSchema.extend({
  version: z.union([z.literal("draft"), z.number().int().positive()]).optional(),
  now: localTime.optional(),
});

/** Una conversación nueva con el borrador o con una versión, con su hora y su agenda. */
export async function openPlaygroundAction(raw: unknown): Promise<ActionResult<PlaygroundSession>> {
  const body = openSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() =>
    backendFor(principal).openPlaygroundSession(body.ref, body.agent, {
      ...(body.version !== undefined ? { version: body.version } : {}),
      ...(body.now ? { now: body.now } : {}),
    }),
  );
}

const messageSchema = agentSchema.extend({ session: uuid, text: z.string().trim().min(1).max(1000) });

/** Un mensaje del cliente simulado: vuelve el turno del agente y la agenda como queda. */
export async function sendPlaygroundAction(raw: unknown): Promise<ActionResult<PlaygroundReply>> {
  const body = messageSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).sendPlaygroundMessage(body.ref, body.agent, body.session, body.text));
}

const timeSchema = agentSchema.extend({ session: uuid, now: localTime });

/** Cambiar la hora simulada (20.2). */
export async function setPlaygroundTimeAction(raw: unknown): Promise<ActionResult<PlaygroundSession>> {
  const body = timeSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).setPlaygroundTime(body.ref, body.agent, body.session, body.now));
}

const sessionSchema = agentSchema.extend({ session: uuid });

/** Cerrar la conversación simulada: se borra. */
export async function closePlaygroundAction(raw: unknown): Promise<ActionResult<null>> {
  const body = sessionSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).closePlaygroundSession(body.ref, body.agent, body.session));
}

// ── las pruebas (requisito 21) ──────────────────────────────────────────────

export async function testsAction(raw: unknown): Promise<ActionResult<TestSuite>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentTests(body.ref, body.agent));
}

const criterion = z.object({ key: z.string().regex(/^[a-z0-9_]{1,40}$/), text: z.string().trim().min(1).max(300) });
const addTestSchema = agentSchema.extend({
  test: z.object({
    name: z.string().trim().min(1).max(120),
    persona: z.string().trim().max(500).optional(),
    first_message: z.string().trim().min(1).max(2000),
    plan: z.string().trim().max(1000).optional(),
    criteria: z.array(criterion).max(6).optional(),
    critical: z.boolean().optional(),
  }),
});

/** Una prueba añadida por una persona (21.1). */
export async function addTestAction(raw: unknown): Promise<ActionResult<TestSuite>> {
  const body = addTestSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).addAgentTest(body.ref, body.agent, body.test));
}

const notApplicableSchema = agentSchema.extend({ test: uuid, reason: z.string().max(500) });

/** «No aplica» con su razón, o `""` para que vuelva a contar (21.6). */
export async function setNotApplicableAction(raw: unknown): Promise<ActionResult<TestSuite>> {
  const body = notApplicableSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).editAgentTest(body.ref, body.agent, body.test, { not_applicable_reason: body.reason.trim() }));
}

const runSchema = agentSchema
  .extend({ scope: z.enum(["all", "affected", "one"]), test: uuid.optional() })
  .refine((b) => b.scope !== "one" || b.test !== undefined, { message: "test_required", path: ["test"] });

/** Una pasada (3 repeticiones por prueba, 21.4) → `202 {job_id}`. */
export async function runTestsAction(raw: unknown): Promise<ActionResult<TestRunAccepted>> {
  const body = runSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).runAgentTests(body.ref, body.agent, body.scope, body.scope === "one" ? body.test : undefined));
}

const jobSchema = z.object({ ref, job: uuid });

/** Un trabajo de pruebas o de «Guardar», para la espera creciente. */
export async function qualityJobAction(raw: unknown): Promise<ActionResult<QualityJob>> {
  const body = jobSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).getConsoleJob(body.job));
  // Una versión publicada cambia el estado del agente en todo el cliente.
  if (res.ok && res.data.kind === "publish" && res.data.status === "done") refresh(body.ref);
  return res;
}

// ── la revisión (requisito 22) ──────────────────────────────────────────────

export async function reviewAction(raw: unknown): Promise<ActionResult<AgentReview>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentReview(body.ref, body.agent));
}

// ── «Guardar», deshacer, historial y restaurar (requisitos 23 y 24) ─────────

export async function publishPreviewAction(raw: unknown): Promise<ActionResult<PublishPreview>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getPublishPreview(body.ref, body.agent));
}

const publishSchema = agentSchema.extend({
  note: z.string().trim().max(500).optional(),
  accept_normal_failures: z.boolean().optional(),
  override_reason: z.string().trim().min(3).max(500).optional(),
});

/** «Guardar» → `202 {job_id}`: el worker prueba, revisa, decide y publica (23.1). */
export async function publishAction(raw: unknown): Promise<ActionResult<{ job_id: string }>> {
  const body = publishSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() =>
    backendFor(principal).publishAgent(body.ref, body.agent, {
      ...(body.note ? { note: body.note } : {}),
      ...(body.accept_normal_failures ? { accept_normal_failures: true } : {}),
      ...(body.override_reason ? { override_reason: body.override_reason } : {}),
    }),
  );
}

/** «Deshacer», durante 10 minutos (24.1). */
export async function undoPublishAction(raw: unknown): Promise<ActionResult<{ number: number }>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).undoPublish(body.ref, body.agent));
  if (res.ok) refresh(body.ref);
  return res;
}

export async function historyAction(raw: unknown): Promise<ActionResult<HistoryEntry[]>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentHistory(body.ref, body.agent));
}

const restoreSchema = agentSchema.extend({ number: z.number().int().positive() });

/** «Restaurar» crea un borrador con esa versión, que pasa la puerta antes de publicarse (24.3). */
export async function restoreVersionAction(raw: unknown): Promise<ActionResult<RestoreResult>> {
  const body = restoreSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).restoreAgentVersion(body.ref, body.agent, body.number));
  if (res.ok) refresh(body.ref);
  return res;
}
