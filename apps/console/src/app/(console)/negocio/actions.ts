"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Hours, Locations, Services, SpecialDates } from "@/lib/backend/business-sections";
import type { LiteBusiness, LiteUndo } from "@/lib/backend/lite-agents";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T168; requisitos 50.1, 50.4, 9, 10, 11 y 13) — «Negocio» de la
 * persona del cliente: el horario, las fechas especiales, los servicios (precio,
 * duración, descripción y si es reservable) y las sedes, con deshacer. Cada
 * escritura lleva la revisión que leyó la pantalla (`If-Match`; 412 con lo que
 * cambió) y una `Idempotency-Key` que la pantalla genera una vez por intento.
 * La API guarda su nombre y «desde la web», y avisa al partner.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const uuid = z.string().uuid();
const revision = z.number().int().min(0);
const key = z.string().min(8).max(80).optional();
const hhmm = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/);
const close = z.string().regex(/^(([01]\d|2[0-3]):[0-5]\d|24:00)$/);
const shift = z.object({ open: hhmm, close });
const day = z.enum(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const price = z.object({ kind: z.enum(["none", "free", "amount"]), amount_minor: z.number().int().min(0).optional() });

async function businessPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("business") ? res.principal : null;
}

async function write<T>(fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await businessPrincipal();
  if (!principal) return forbidden;
  const res = await run(() => fn(backendFor(principal)));
  if (res.ok) revalidatePath("/negocio");
  return res;
}

/** Leer otra vez la ficha entera: «Reintentar», el aviso de conflicto y después de deshacer. */
export async function reloadBusinessAction(): Promise<ActionResult<LiteBusiness>> {
  const principal = await businessPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteBusiness());
}

// ── horario (del negocio o de una sede) ────────────────────────────────────

const hoursSchema = z.object({
  revision,
  key,
  location_id: uuid.nullable().optional(),
  body: z.union([
    z.object({ layout: z.enum(["blocks", "daily"]), days: z.record(day, z.array(shift).max(6)), confirm_loss: z.boolean().optional() }),
    z.object({ inherit: z.literal(true) }),
    z.object({ clear: z.literal(true) }),
  ]),
});

/** El horario de una sede (el suyo o el que hereda) o, sin sede, el del negocio. */
export async function loadLiteHoursAction(raw: unknown): Promise<ActionResult<Hours>> {
  const p = z.object({ location_id: uuid.nullable() }).parse(raw);
  const principal = await businessPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteHours(p.location_id));
}

export async function saveLiteHoursAction(raw: unknown): Promise<ActionResult<Hours>> {
  const p = hoursSchema.parse(raw);
  return write((api) => api.litePutHours(p.body, p.revision, p.key, p.location_id));
}

// ── fechas especiales ──────────────────────────────────────────────────────

const specialBody = z.object({
  name: z.string().max(80).nullable().optional(),
  location_id: uuid.nullable().optional(),
  from: date,
  to: date,
  closed: z.boolean(),
  shifts: z.array(shift).max(6).optional(),
});

export async function createLiteSpecialDateAction(raw: unknown): Promise<ActionResult<SpecialDates>> {
  const p = z.object({ revision, key, body: specialBody }).parse(raw);
  return write((api) => api.liteCreateSpecialDate(p.body, p.revision, p.key));
}

export async function archiveLiteSpecialDateAction(raw: unknown): Promise<ActionResult<SpecialDates>> {
  const p = z.object({ revision, key, id: uuid }).parse(raw);
  return write((api) => api.liteArchiveSpecialDate(p.id, p.revision, p.key));
}

// ── servicios ──────────────────────────────────────────────────────────────

const serviceFields = {
  description: z.string().max(1000).nullable().optional(),
  bookable: z.boolean().optional(),
  duration_min: z.number().int().min(5).max(480).nullable().optional(),
  price: price.optional(),
};

export async function createLiteServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const p = z.object({ revision, key, body: z.object({ name: z.string().trim().min(1).max(120), ...serviceFields }) }).parse(raw);
  return write((api) => api.liteCreateService(p.body, p.revision, p.key));
}

/** El nombre no viaja: en la lite se cambia el precio, la duración, la descripción y si es reservable. */
export async function updateLiteServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const p = z.object({ revision, key, id: uuid, body: z.object(serviceFields) }).parse(raw);
  return write((api) => api.liteUpdateService(p.id, p.body, p.revision, p.key));
}

export async function archiveLiteServiceAction(raw: unknown): Promise<ActionResult<Services>> {
  const p = z.object({ revision, key, id: uuid }).parse(raw);
  return write((api) => api.liteArchiveService(p.id, p.revision, p.key));
}

// ── sedes ──────────────────────────────────────────────────────────────────

const locationBody = z.object({
  name: z.string().trim().min(1).max(80).optional(),
  address: z.string().max(300).nullable().optional(),
  phone_e164: z.string().max(20).nullable().optional(),
});

export async function createLiteLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const p = z.object({ revision, key, body: locationBody }).parse(raw);
  return write((api) => api.liteCreateLocation(p.body, p.revision, p.key));
}

export async function updateLiteLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const p = z.object({ revision, key, id: uuid, body: locationBody }).parse(raw);
  return write((api) => api.liteUpdateLocation(p.id, p.body, p.revision, p.key));
}

export async function archiveLiteLocationAction(raw: unknown): Promise<ActionResult<Locations>> {
  const p = z.object({ revision, key, id: uuid, restore: z.boolean() }).parse(raw);
  return write((api) => api.liteArchiveLocation(p.id, p.revision, p.restore, p.key));
}

// ── deshacer ───────────────────────────────────────────────────────────────

export async function undoLiteChangeAction(raw: unknown): Promise<ActionResult<LiteUndo>> {
  const p = z.object({ id: uuid, key }).parse(raw);
  return write((api) => api.liteUndoChange(p.id, p.key));
}
