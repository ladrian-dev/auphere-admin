"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  CatalogList,
  ChannelDetail,
  MetaSocialConnectResult,
  TemplateCreated,
  TemplateList,
  TestSendResult,
  WhatsAppSignupResult,
} from "@/lib/backend/channels";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `channels` (CP-17..19). Zod on the server, `run()`
 *  so backend errors come back as messages, `can()` before every write. */

const ref = z.string().min(1).max(255);

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}

export async function whatsappSignupAction(raw: unknown): Promise<ActionResult<WhatsAppSignupResult>> {
  const body = z
    .object({
      ref,
      code: z.string().min(1).max(512),
      waba_id: z.string().min(1).max(64),
      phone_number_id: z.string().max(64).optional(),
      business_id: z.string().max(64).optional(),
      mode: z.enum(["cloud_api", "coexistence"]),
    })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const { ref: r, ...signup } = body;
  const res = await run(() => backendFor(principal).whatsappSignup(r, signup));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
  return res;
}

export async function setChannelRoleAction(raw: unknown): Promise<ActionResult<ChannelDetail>> {
  const body = z.object({ ref, channelId: z.string().uuid(), role: z.enum(["agent", "notifications"]).nullable() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).setChannelRole(body.ref, body.channelId, body.role));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/channels`);
  return res;
}

/**
 * Soltar un número (spec 019, revisión del 2026-09-29).
 *
 * Conectar era autoservicio y desconectar no existía en ninguna parte —ni en la
 * API—, así que el partner que se equivocaba de número tenía que escribirnos.
 * Un producto donde se entra y no se sale da más miedo al entrar del que
 * debería.
 */
export async function disconnectChannelAction(raw: unknown): Promise<ActionResult<ChannelDetail>> {
  const body = z.object({ ref, channelId: z.string().uuid() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).disconnectChannel(body.ref, body.channelId));
  // `layout`: el estado del canal decide la tarjeta de puesta en marcha y la
  // insignia de la cabecera, no solo esta pantalla.
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

// ── el catálogo del número (spec 022) ────────────────────────────────

export async function listCatalogsAction(raw: unknown): Promise<ActionResult<CatalogList>> {
  const body = z.object({ ref, channelId: z.string().uuid() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:read")) return forbidden();
  return run(() => backendFor(principal).listCatalogs(body.ref, body.channelId));
}

export async function setCatalogAction(raw: unknown): Promise<ActionResult<ChannelDetail>> {
  const body = z
    .object({
      ref,
      channelId: z.string().uuid(),
      catalogId: z.string().min(1).max(64),
      // Solo en coexistencia, cuando Meta no lista los catálogos: el nombre que escribió quien declara.
      catalogName: z.string().trim().min(1).max(120).optional(),
    })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).setCatalog(body.ref, body.channelId, body.catalogId, body.catalogName));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

export async function clearCatalogAction(raw: unknown): Promise<ActionResult<ChannelDetail>> {
  const body = z.object({ ref, channelId: z.string().uuid() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).clearCatalog(body.ref, body.channelId));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

const button = z.object({
  type: z.enum(["QUICK_REPLY", "URL", "PHONE_NUMBER"]),
  label: z.string().min(1).max(25),
  url: z.string().url().max(2000).optional(),
  phone_number: z.string().max(20).optional(),
});

/**
 * The client's templates, for the number's page (QA 2026-10-30: they only
 * lived on a page no tab of the v2 console leads to). `null` = WhatsApp is
 * not connected (409 upstream), as on the client's channels page.
 */
export async function listTemplatesAction(raw: unknown): Promise<ActionResult<TemplateList | null>> {
  const body = z.object({ ref }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:read")) return forbidden();
  const res = await run(() => backendFor(principal).listTemplates(body.ref));
  if (!res.ok && res.status === 409) return { ok: true, data: null };
  return res;
}

export async function createTemplateAction(raw: unknown): Promise<ActionResult<TemplateCreated>> {
  const body = z
    .object({
      ref,
      name: z.string().regex(/^[a-z0-9_]{1,512}$/),
      language: z.string().min(2).max(15),
      category: z.enum(["MARKETING", "UTILITY", "AUTHENTICATION"]),
      header_text: z.string().max(60).optional(),
      body_text: z.string().min(1).max(1024),
      footer_text: z.string().max(60).optional(),
      buttons: z.array(button).max(3).default([]),
      examples: z.record(z.string().regex(/^[a-z0-9_]{1,40}$/), z.string().min(1).max(200)).default({}),
    })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const { ref: r, ...tpl } = body;
  const res = await run(() =>
    backendFor(principal).createTemplate(r, {
      ...tpl,
      header_text: tpl.header_text || undefined,
      footer_text: tpl.footer_text || undefined,
    }),
  );
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
  return res;
}

export async function deleteTemplateAction(raw: unknown): Promise<ActionResult<{ name: string; deleted: boolean }>> {
  const body = z.object({ ref, name: z.string().regex(/^[a-z0-9_]{1,512}$/) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).deleteTemplate(body.ref, body.name));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

export async function testSendAction(raw: unknown): Promise<ActionResult<TestSendResult>> {
  const body = z.object({ ref, to: z.string().regex(/^\+?[0-9]{5,20}$/) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  return run(() => backendFor(principal).channelTestSend(body.ref, body.to));
}

/** Spec 040: a link for the business owner to connect WhatsApp themselves. */
export async function whatsappSignupLinkAction(
  raw: unknown,
): Promise<ActionResult<{ url: string; mode: string; expires_at: string }>> {
  const body = z.object({ ref, mode: z.enum(["cloud_api", "coexistence"]) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  return run(() => backendFor(principal).whatsappSignupLink(body.ref, body.mode));
}

/** Revoke a WhatsApp link the owner has not used (owner, 2026-10-20). */
export async function revokeWhatsappSignupLinkAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ ref, id: z.string().uuid() }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).revokeWhatsappSignupLink(body.ref, body.id));
  if (res.ok) revalidatePath(`/clients/${body.ref}/channels`);
  return res;
}

// ── Instagram y Messenger (spec 049) ─────────────────────────────────

const metaSocialKind = z.enum(["instagram", "messenger"]);

/** The single-use code from Facebook Login for Business. The server reads
 *  what the business granted; with several accounts it answers «choose». */
export async function metaSocialConnectAction(raw: unknown): Promise<ActionResult<MetaSocialConnectResult>> {
  const body = z.object({ ref, kind: metaSocialKind, code: z.string().min(1).max(2048) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).metaSocialConnect(body.ref, body.kind, body.code));
  if (res.ok && res.data.status === "connected") revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

export async function metaSocialCompleteAction(raw: unknown): Promise<ActionResult<MetaSocialConnectResult>> {
  const body = z
    .object({ ref, kind: metaSocialKind, nonce: z.string().min(8).max(64), accountId: z.string().min(1).max(64) })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).metaSocialComplete(body.ref, body.kind, body.nonce, body.accountId));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}
