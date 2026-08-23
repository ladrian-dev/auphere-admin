"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { KNOWLEDGE_MAX_UPLOAD_BYTES, uploadPlaybookFile, type KnowledgeDocumentOut } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

const docId = z.string().uuid();

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}

export async function uploadPlaybookAction(formData: FormData): Promise<ActionResult<KnowledgeDocumentOut>> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, status: 422, message: "file required" };
  if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return { ok: false, status: 413, message: "file exceeds 10 MB" };
  const title = z.string().max(255).optional().parse(formData.get("title")?.toString().trim() || undefined);
  const principal = await requirePrincipal();
  if (!can(principal.role, "playbook:write")) return forbidden();
  const upstream = new FormData();
  upstream.set("file", file, file.name);
  if (title) upstream.set("title", title);
  const res = await run(() => uploadPlaybookFile(principal, upstream));
  if (res.ok) revalidatePath("/knowledge");
  return res;
}

export async function addPlaybookUrlAction(raw: unknown): Promise<ActionResult<KnowledgeDocumentOut>> {
  const body = z
    .object({ url: z.string().min(8).max(2048).regex(/^https?:\/\//), title: z.string().max(255).optional() })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "playbook:write")) return forbidden();
  const res = await run(() => backendFor(principal).addPlaybookUrl({ url: body.url, title: body.title || undefined }));
  if (res.ok) revalidatePath("/knowledge");
  return res;
}

export async function deletePlaybookAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ id: docId }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "playbook:write")) return forbidden();
  const res = await run(() => backendFor(principal).deletePlaybook(body.id));
  if (res.ok) revalidatePath("/knowledge");
  return res;
}

export async function reindexPlaybookAction(raw: unknown): Promise<ActionResult<KnowledgeDocumentOut>> {
  const body = z.object({ id: docId }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "playbook:write")) return forbidden();
  const res = await run(() => backendFor(principal).reindexPlaybook(body.id));
  if (res.ok) revalidatePath("/knowledge");
  return res;
}
