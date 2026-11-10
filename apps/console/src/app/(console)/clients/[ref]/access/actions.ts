"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { ACCESS_MODULES, CAPACITY_KINDS, type ClientAccess, type ClientAccessMember, type ClientInvitation } from "@/lib/backend/client-access";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 056 (Requisito 3, D3, D4) — las acciones de la pestaña «Acceso» de un
 * cliente. Todas piden `client_access:manage` (owner y admin), el mismo permiso
 * que la API: el resto de roles y la persona de un cliente reciben la negativa
 * aquí, antes de ningún viaje. Cada entrada se valida con Zod en modo estricto
 * (ni `partner_id` ni `tenant_id` pasan) y la API vuelve a decidir con las reglas
 * del panel.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const member = z.string().uuid();

async function manager() {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "client_access:manage")) return null;
  return principal;
}

const accessPath = (r: string) => `/clients/${encodeURIComponent(r)}/access`;

const readSchema = z.object({ ref }).strict();

/** Leer el acceso otra vez (Reintentar). */
export async function reloadClientAccessAction(raw: unknown): Promise<ActionResult<ClientAccess>> {
  const body = readSchema.parse(raw);
  const principal = await manager();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).clientAccess(body.ref));
}

const setSchema = z
  .object({
    ref,
    enabled: z.boolean(),
    modules: z.array(z.enum(ACCESS_MODULES)).max(ACCESS_MODULES.length),
    reservas: z
      .object({
        mode: z.enum(["services", "capacity"]),
        capacity_kind: z.enum(CAPACITY_KINDS).optional(),
        on_live: z.literal("cancel_and_notify").optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

/** Encender, apagar o cambiar los módulos (y el modo de Reservas). */
export async function setClientAccessAction(raw: unknown): Promise<ActionResult<ClientAccess>> {
  const { ref: r, ...body } = setSchema.parse(raw);
  const principal = await manager();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).setClientAccess(r, body));
  if (res.ok) revalidatePath(accessPath(r));
  return res;
}

const inviteSchema = z
  .object({
    ref,
    email: z.string().trim().min(3).max(254).email(),
    name: z.string().trim().max(120).nullish(),
  })
  .strict();

/** Invitar a una persona del cliente: el enlace vuelve una sola vez. */
export async function inviteClientMemberAction(raw: unknown): Promise<ActionResult<ClientInvitation>> {
  const { ref: r, email, name } = inviteSchema.parse(raw);
  const principal = await manager();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).inviteClientMember(r, { email, name: name || null }));
  if (res.ok) revalidatePath(accessPath(r));
  return res;
}

const memberSchema = z.object({ ref, member }).strict();

/** Otro enlace para una invitación: el anterior deja de servir. */
export async function resendClientMemberAction(raw: unknown): Promise<ActionResult<ClientInvitation>> {
  const body = memberSchema.parse(raw);
  const principal = await manager();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).resendClientMember(body.ref, body.member));
  if (res.ok) revalidatePath(accessPath(body.ref));
  return res;
}

/** Retirar el acceso a una persona (cierra sus sesiones y teléfonos) o una invitación. */
export async function revokeClientMemberAction(raw: unknown): Promise<ActionResult<{ member: ClientAccessMember }>> {
  const body = memberSchema.parse(raw);
  const principal = await manager();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).revokeClientMember(body.ref, body.member));
  if (res.ok) revalidatePath(accessPath(body.ref));
  return res;
}
