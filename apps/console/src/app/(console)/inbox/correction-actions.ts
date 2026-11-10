"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { CORRECTION_LIMITS, type Correction } from "@/lib/backend/inbox-corrections";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T176; requisitos 52.1 a 52.6) — «Corregir esta respuesta» desde la
 * Bandeja. El borrador no aplica nada: dice de qué tipo es y lo que hay que
 * quitar. Enviar aplica un dato al momento o lleva un comportamiento al partner
 * como propuesta; con datos de un cliente final dentro, la API responde 422
 * `pii_present` y no guarda nada. Solo la persona de un cliente con la Bandeja.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const id = z.string().uuid();
const revision = z.number().int().min(0);

async function inboxPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("inbox") ? res.principal : null;
}

async function act<T>(fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => fn(backendFor(principal)));
}

const createSchema = z.object({
  conversation: id,
  message: id,
  text: z.string().trim().min(1).max(CORRECTION_LIMITS.lesson),
  scope: z.enum(["business", "agent"]),
  key: z.string().min(8).max(80).optional(),
});

export async function createCorrectionAction(raw: unknown): Promise<ActionResult<Correction>> {
  const p = createSchema.parse(raw);
  return act((api) => api.createCorrection(p.conversation, p.message, { text: p.text, scope: p.scope }, p.key));
}

const editSchema = z.object({
  id,
  revision,
  lesson: z.string().trim().min(1).max(CORRECTION_LIMITS.lesson).optional(),
  paraphrase: z.string().max(CORRECTION_LIMITS.paraphrase).optional(),
});

export async function editCorrectionAction(raw: unknown): Promise<ActionResult<Correction>> {
  const p = editSchema.parse(raw);
  const body: { lesson?: string; paraphrase?: string } = {};
  if (p.lesson !== undefined) body.lesson = p.lesson;
  if (p.paraphrase !== undefined) body.paraphrase = p.paraphrase;
  return act((api) => api.editCorrection(p.id, p.revision, body));
}

export async function sendCorrectionAction(raw: unknown): Promise<ActionResult<Correction>> {
  const p = z.object({ id, revision }).parse(raw);
  return act((api) => api.sendCorrection(p.id, p.revision));
}

export async function undoCorrectionAction(raw: unknown): Promise<ActionResult<Correction>> {
  const p = z.object({ id }).parse(raw);
  return act((api) => api.undoCorrection(p.id));
}
