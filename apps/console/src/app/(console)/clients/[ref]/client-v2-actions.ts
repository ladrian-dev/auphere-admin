"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import {
  clientRecordsApi,
  uploadBusinessSource,
  type BusinessRecord,
  type Change,
  type ClientDetailV2,
  type ClientLifecycleResult,
  type LinkItem,
  type Source,
  type Sources,
} from "@/lib/backend/client-records";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T063, T069, T071) — las acciones del cliente con la consola nueva:
 * editar (con `If-Match`), archivar con «Deshacer», restaurar y eliminar; y las
 * de su ficha: procedencia, historial y deshacer, propuestas, documentos y webs
 * y redes. Cada entrada se valida aquí con Zod; la API vuelve a validar y es la
 * que decide. El navegador nunca tiene credenciales.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const SECTIONS = ["basics", "locations", "hours", "special_dates", "services", "policies", "faqs", "sources", "links"] as const;
const NETWORKS = ["web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads"] as const;

async function partner(permission: Parameters<typeof can>[1]) {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

function refresh(r: string) {
  revalidatePath(`/clients/${r}`, "layout");
  revalidatePath("/clients");
}

// ── el cliente ──────────────────────────────────────────────────────────────

const editSchema = z.object({
  ref,
  revision: z.number().int().min(0),
  body: z
    .object({
      name: z.string().trim().min(1).max(60).optional(),
      niche: z.string().trim().min(2).max(80).optional(),
      info: z.string().max(2000).nullish(),
      country: z.string().regex(/^[A-Z]{2}$/).nullish(),
      timezone: z.string().min(1).max(64).optional(),
      price_currency: z.string().regex(/^[A-Z]{3}$/).nullish(),
      wallet_currency: z.enum(["EUR", "USD"]).optional(),
      eu_only: z.boolean().optional(),
    })
    .strict(),
});
/** «Editar cliente» (requisito 6.1): la zona IANA la valida la API. */
export async function updateClientV2Action(raw: unknown): Promise<ActionResult<ClientDetailV2>> {
  const { ref: r, revision, body } = editSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).updateClientV2(r, body, revision));
  if (res.ok) refresh(r);
  return res;
}

const refSchema = z.object({ ref });
/** Lo que el modal «Editar cliente» enseña, con su revisión para `If-Match`. */
export async function getClientV2Action(raw: unknown): Promise<ActionResult<ClientDetailV2>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  return run(() => clientRecordsApi(callFor(principal)).getClientV2(r));
}

/** Archivar (6.4): sus agentes en pausa; el aviso trae «Deshacer» (restaurar). */
export async function archiveClientAction(raw: unknown): Promise<ActionResult<ClientLifecycleResult>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).archiveClient(r));
  if (res.ok) refresh(r);
  return res;
}

/** Restaurar (6.5): cada agente vuelve a su estado. */
export async function restoreClientAction(raw: unknown): Promise<ActionResult<ClientLifecycleResult>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).restoreClient(r));
  if (res.ok) refresh(r);
  return res;
}

const deleteSchema = z.object({ ref, confirm_name: z.string().min(1).max(255) });
/** Eliminar (6.6): `clients:delete`, archivado antes y el nombre tecleado. */
export async function deleteClientV2Action(raw: unknown): Promise<ActionResult<null>> {
  const { ref: r, confirm_name } = deleteSchema.parse(raw);
  const principal = await partner("clients:delete");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).deleteClientV2(r, confirm_name));
  if (res.ok) revalidatePath("/clients");
  return res;
}

// ── la ficha ───────────────────────────────────────────────────────────────

/** La ficha entera: ClientSpec, secciones, procedencia y propuestas. */
export async function getBusinessAction(raw: unknown): Promise<ActionResult<BusinessRecord>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  return run(() => clientRecordsApi(callFor(principal)).getBusiness(r));
}

const sectionSchema = z.object({ ref, section: z.enum(SECTIONS) });
/** «Es correcto» (13.2): lo leído pasa a escrito por quien confirma. */
export async function confirmSectionAction(raw: unknown): Promise<ActionResult<{ confirmed: number }>> {
  const { ref: r, section } = sectionSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).confirmSection(r, section));
  if (res.ok) refresh(r);
  return res;
}

const historySchema = z.object({ ref, section: z.enum(SECTIONS).optional() });
export async function getHistoryAction(raw: unknown): Promise<ActionResult<Change[]>> {
  const { ref: r, section } = historySchema.parse(raw);
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  return run(async () => (await clientRecordsApi(callFor(principal)).getHistory(r, section)).items);
}

const undoSchema = z.object({ ref, change_id: uuid });
/** Deshacer el último cambio de una sección (13.3); `412` si alguien escribió después. */
export async function undoChangeAction(raw: unknown): Promise<ActionResult<{ revision: number | null }>> {
  const { ref: r, change_id } = undoSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).undoChange(r, change_id));
  if (res.ok) refresh(r);
  return res;
}

const decideSchema = z.object({
  ref,
  id: uuid,
  decision: z.enum(["accept", "edit", "discard"]),
  value: z.unknown().optional(),
});
export async function decideSuggestionAction(raw: unknown): Promise<ActionResult<{ decision: string }>> {
  const { ref: r, id, decision, value } = decideSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).decideSuggestion(r, id, decision, value));
  if (res.ok) refresh(r);
  return res;
}

const linksSchema = z.object({
  ref,
  revision: z.number().int().min(0),
  links: z
    .array(z.object({ network: z.enum(NETWORKS), url: z.string().max(300).nullish(), handle: z.string().max(31).nullish() }))
    .max(20),
});
/** Redes y web (12.4), con `If-Match` de la sección. */
export async function putLinksAction(raw: unknown): Promise<ActionResult<{ links: LinkItem[]; revision: number }>> {
  const { ref: r, revision, links } = linksSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).putLinks(r, links, revision));
  if (res.ok) refresh(r);
  return res;
}

// ── documentos y webs ──────────────────────────────────────────────────────

export async function listSourcesAction(raw: unknown): Promise<ActionResult<Sources>> {
  const { ref: r } = refSchema.parse(raw);
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  return run(() => clientRecordsApi(callFor(principal)).listSources(r));
}

/** 10 MB, la misma cifra que comprueba la API (413). */
const SOURCE_MAX_BYTES = 10 * 1024 * 1024;

/** Multipart: `ref`, `file`. Se lee en segundo plano: vuelve «Leyendo». */
export async function uploadSourceAction(formData: FormData): Promise<ActionResult<{ source: Source; job_id: string }>> {
  const r = ref.parse(formData.get("ref"));
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, status: 422, message: "file required", code: "file_required" };
  if (file.size > SOURCE_MAX_BYTES) return { ok: false, status: 413, message: "too large", code: "too_large" };
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const upstream = new FormData();
  upstream.set("file", file, file.name);
  const res = await run(() => uploadBusinessSource(principal, r, upstream));
  if (res.ok) refresh(r);
  return res;
}

const urlSchema = z.object({ ref, url: z.string().min(8).max(2048).regex(/^https?:\/\//i), title: z.string().max(255).optional() });
export async function addSourceUrlAction(raw: unknown): Promise<ActionResult<{ source: Source; job_id: string }>> {
  const { ref: r, url, title } = urlSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).addSourceUrl(r, url, title));
  if (res.ok) refresh(r);
  return res;
}

const sourceSchema = z.object({ ref, id: uuid });
export async function rereadSourceAction(raw: unknown): Promise<ActionResult<{ source: Source; job_id: string }>> {
  const { ref: r, id } = sourceSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  return run(() => clientRecordsApi(callFor(principal)).rereadSource(r, id));
}

/** Quitar (12.2): deja de usarse ya; 10 minutos para deshacer. */
export async function removeSourceAction(raw: unknown): Promise<ActionResult<{ id: string; restore_until: string }>> {
  const { ref: r, id } = sourceSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).removeSource(r, id));
  if (res.ok) refresh(r);
  return res;
}

export async function restoreSourceAction(raw: unknown): Promise<ActionResult<Source>> {
  const { ref: r, id } = sourceSchema.parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  const res = await run(() => clientRecordsApi(callFor(principal)).restoreSource(r, id));
  if (res.ok) refresh(r);
  return res;
}
