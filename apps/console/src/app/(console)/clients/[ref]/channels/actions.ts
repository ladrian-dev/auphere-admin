"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ChannelDetail, TemplateCreated, TestSendResult, WhatsAppSignupResult } from "@/lib/backend/channels";
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

const button = z.object({
  type: z.enum(["QUICK_REPLY", "URL", "PHONE_NUMBER"]),
  label: z.string().min(1).max(25),
  url: z.string().url().max(2000).optional(),
  phone_number: z.string().max(20).optional(),
});

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
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(r)}/channels`);
  return res;
}

export async function deleteTemplateAction(raw: unknown): Promise<ActionResult<{ name: string; deleted: boolean }>> {
  const body = z.object({ ref, name: z.string().regex(/^[a-z0-9_]{1,512}$/) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  const res = await run(() => backendFor(principal).deleteTemplate(body.ref, body.name));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/channels`);
  return res;
}

export async function testSendAction(raw: unknown): Promise<ActionResult<TestSendResult>> {
  const body = z.object({ ref, to: z.string().regex(/^\+?[0-9]{5,20}$/) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden();
  return run(() => backendFor(principal).channelTestSend(body.ref, body.to));
}
