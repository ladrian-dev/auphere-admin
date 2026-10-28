"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  AgentSpec,
  AnswersResult,
  BuilderDraft,
  DraftJob,
  DraftJobAccepted,
  Proposal,
  ProposalDecision,
} from "@/lib/backend/builder-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historia 7, T081) — las acciones del constructor de agentes: «Generar
 * borrador» (o empezar desde una plantilla o en blanco), consultar el trabajo,
 * responder sus preguntas, guardar un bloque del AgentSpec con la revisión que
 * leyó la pantalla y decidir una propuesta.
 *
 * Zod aquí con los mismos límites que la pantalla (nombre de 1 a 40, «¿Qué tiene
 * que hacer?» de 20 a 1.024) y `can()` antes de cualquier llamada. La API vuelve
 * a validar y es la que decide: sus códigos vuelven en `ActionResult.code` para
 * que la pantalla los diga con palabras. El navegador nunca tiene credenciales.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();

async function partner(permission: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

/** La pestaña Agentes y la pantalla del agente cuelgan del marco del cliente. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

// ── «Nuevo agente» ──────────────────────────────────────────────────────────

const startSchema = z
  .object({
    ref,
    name: z.string().trim().min(1).max(40),
    description: z.string().trim().max(1024).optional(),
    start: z.enum(["describe", "template", "blank"]),
    template_id: z.string().min(1).max(80).optional(),
  })
  .refine((b) => b.start !== "describe" || (b.description !== undefined && b.description.length >= 20), {
    message: "description_length",
    path: ["description"],
  })
  .refine((b) => b.start !== "template" || b.template_id !== undefined, { message: "template_required", path: ["template_id"] });

/**
 * «Generar borrador» → `202 {job_id}` (el agente nace al terminar, 17.2); «Desde
 * una plantilla» y «En blanco» → el trabajo ya terminado, con el agente.
 */
export async function startDraftJobAction(raw: unknown): Promise<ActionResult<DraftJobAccepted>> {
  const body = startSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const description = body.description && body.description.length >= 20 ? body.description : undefined;
  const res = await run(() =>
    backendFor(principal).startDraftJob(body.ref, {
      name: body.name,
      start: body.start,
      ...(description ? { description } : {}),
      ...(body.start === "template" && body.template_id ? { template_id: body.template_id } : {}),
    }),
  );
  if (res.ok && res.data.agent_id) refresh(body.ref);
  return res;
}

const jobSchema = z.object({ ref, job: uuid });

/** El trabajo, para la espera creciente de la pantalla. Leer es leer. */
export async function draftJobAction(raw: unknown): Promise<ActionResult<DraftJob>> {
  const body = jobSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).getDraftJob(body.job));
  // El agente ya existe: la pestaña Agentes tiene que verlo como borrador.
  if (res.ok && res.data.status === "done") refresh(body.ref);
  return res;
}

const answersSchema = z.object({
  ref,
  job: uuid,
  answers: z
    .array(
      z.object({
        question_id: z.string().min(1).max(40),
        value: z.string().trim().min(1).max(1000),
        scope: z.enum(["business", "agent"]).optional(),
      }),
    )
    .min(1)
    .max(5),
});

/** Las respuestas, cada una donde la persona dijo: la ficha o «Solo este agente» (17.5). */
export async function answerDraftJobAction(raw: unknown): Promise<ActionResult<AnswersResult>> {
  const body = answersSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).answerDraftJob(body.job, body.answers));
  if (res.ok) {
    refresh(body.ref);
    // Una respuesta de negocio cambia la ficha.
    if (res.data.applied.some((a) => a.scope === "business")) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/business`);
  }
  return res;
}

// ── el borrador del agente ──────────────────────────────────────────────────

const agentSchema = z.object({ ref, agent: uuid });

/** El borrador otra vez (tras aplicar una propuesta o al elegir «los suyos»). */
export async function builderDraftAction(raw: unknown): Promise<ActionResult<{ draft: BuilderDraft; proposals: Proposal[] | null }>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  const api = backendFor(principal);
  const [draft, proposals] = await Promise.all([
    run(() => api.getBuilderDraft(body.ref, body.agent)),
    run(() => api.listProposals(body.ref, body.agent)),
  ]);
  if (!draft.ok) return draft;
  return { ok: true, data: { draft: draft.data, proposals: proposals.ok ? proposals.data : null } };
}

const specSchema = z
  .object({ schema_version: z.literal("1"), mode: z.enum(["instructions", "structured"]), identity: z.object({}).passthrough() })
  .passthrough();
const saveSpecSchema = z.object({
  ref,
  agent: uuid,
  revision: z.number().int().min(0),
  spec: specSchema,
  note: z.string().max(500).optional(),
});

/**
 * Un bloque editado en línea: el AgentSpec entero con la revisión que leyó la
 * pantalla. El validador sin modelo de la API responde `spec_invalid` con sus
 * `problems`; otra escritura entre medias, 412 con `current` y `changes`. Las
 * pruebas del agente quedan sin ejecutar (17.7): la respuesta lo cuenta.
 */
export async function saveAgentSpecAction(raw: unknown): Promise<ActionResult<BuilderDraft>> {
  const body = saveSpecSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() =>
    backendFor(principal).saveAgentSpec(body.ref, body.agent, body.revision, body.spec as AgentSpec, body.note),
  );
  if (res.ok) refresh(body.ref);
  return res;
}

const proposalSchema = z.object({ ref, agent: uuid, proposal: uuid, decision: z.enum(["apply", "reject"]) });

/** Aplicar o rechazar una propuesta: siempre una persona con permiso (15.2). */
export async function decideProposalAction(raw: unknown): Promise<ActionResult<ProposalDecision>> {
  const body = proposalSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const api = backendFor(principal);
  const res = await run(() =>
    body.decision === "apply"
      ? api.applyProposal(body.ref, body.agent, body.proposal)
      : api.rejectProposal(body.ref, body.agent, body.proposal),
  );
  if (res.ok && body.decision === "apply") refresh(body.ref);
  return res;
}
