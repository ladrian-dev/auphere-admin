"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import {
  clientsV2Api,
  type ClientRead,
  type LinkDetection,
  type NewClientCreated,
  type NicheSuggestion,
} from "@/lib/backend/clients-v2";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T050) — las acciones del modal «Nuevo cliente» y de la tarjeta de
 * lectura. Cada entrada se valida aquí con Zod; la API vuelve a validar y es
 * la que decide (el permiso, los límites, la zona IANA). El navegador nunca
 * tiene credenciales: cada llamada lleva un token de 60 s recién emitido.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const NETWORKS = ["web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads"] as const;

const detectSchema = z.object({
  info: z.string().max(2000),
  browser_timezone: z.string().max(64).nullish(),
  browser_locale: z.string().max(35).nullish(),
});
/** Los chips y «Más ajustes» mientras se escribe la información. */
export async function detectClientLinksAction(raw: unknown): Promise<ActionResult<LinkDetection>> {
  const body = detectSchema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "clients:write")) return forbidden;
  return run(() => clientsV2Api(callFor(principal)).detectClientLinks(body));
}

const nicheSchema = z.object({ q: z.string().max(80).default("") });
/** Las sugerencias de nicho: plantillas y los más usados del partner. */
export async function nicheSuggestionsAction(raw: unknown): Promise<ActionResult<NicheSuggestion[]>> {
  const { q } = nicheSchema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "clients:read")) return forbidden;
  return run(async () => (await clientsV2Api(callFor(principal)).nicheSuggestions(q.trim())).items);
}

const createSchema = z.object({
  name: z.string().trim().min(1).max(60),
  niche: z.string().trim().min(2).max(80),
  info: z.string().max(2000).nullish(),
  country: z.string().regex(/^[A-Z]{2}$/).nullish(),
  timezone: z.string().min(1).max(64).nullish(),
  price_currency: z.string().regex(/^[A-Z]{3}$/).nullish(),
  wallet_currency: z.enum(["EUR", "USD"]).nullish(),
  eu_only: z.boolean().nullish(),
  links: z
    .array(z.object({ network: z.enum(NETWORKS), url: z.string().max(300).nullish(), handle: z.string().max(31).nullish() }))
    .max(20)
    .nullish(),
  idempotency_key: z.string().min(8).max(120),
});
/** El alta en tres datos (requisito 4). Nunca crea un agente. */
export async function createClientV2Action(raw: unknown): Promise<ActionResult<NewClientCreated>> {
  const { idempotency_key, ...body } = createSchema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "clients:write")) return forbidden;
  const res = await run(() => clientsV2Api(callFor(principal)).createClientV2(body, idempotency_key));
  if (res.ok) revalidatePath("/clients");
  return res;
}

const refSchema = z.object({ ref });
/** La tarjeta de lectura: el último trabajo `client_read` y qué hay que leer. */
export async function getClientReadAction(raw: unknown): Promise<ActionResult<ClientRead>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "clients:read")) return forbidden;
  return run(() => clientsV2Api(callFor(principal)).getClientRead(r));
}

/** «Reintentar» / «Volver a leer». Una lectura en marcha no se lanza dos veces. */
export async function startClientReadAction(raw: unknown): Promise<ActionResult<{ job_id: string }>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "clients:write")) return forbidden;
  return run(() => clientsV2Api(callFor(principal)).startClientRead(r));
}
