"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { KNOWLEDGE_MAX_UPLOAD_BYTES, uploadKnowledgeFile, type KnowledgeDocumentOut } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `agent-tools` — knowledge (CP-15). Reads need
 *  `knowledge:read`, writes `knowledge:write`. The extracted text never
 *  travels through here: uploads go straight to the API as multipart. */

const ref = z.string().min(1).max(255);
const docId = z.string().uuid();

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}
const path = (r: string) => `/clients/${encodeURIComponent(r)}/knowledge`;

/** Multipart: `ref`, `file`, optional `title`. Size re-checked server-side (413 upstream too). */
export async function uploadKnowledgeAction(formData: FormData): Promise<ActionResult<KnowledgeDocumentOut>> {
  const r = ref.parse(formData.get("ref"));
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, status: 422, message: "file required" };
  if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return { ok: false, status: 413, message: "file exceeds 10 MB" };
  const title = z.string().max(255).optional().parse(formData.get("title")?.toString().trim() || undefined);
  const principal = await requirePrincipal();
  if (!can(principal.role, "knowledge:write")) return forbidden();
  const upstream = new FormData();
  upstream.set("file", file, file.name);
  if (title) upstream.set("title", title);
  const res = await run(() => uploadKnowledgeFile(principal, r, upstream));
  if (res.ok) revalidatePath(path(r));
  return res;
}

export async function addKnowledgeUrlAction(raw: unknown): Promise<ActionResult<KnowledgeDocumentOut>> {
  const body = z
    .object({ ref, url: z.string().min(8).max(2048).regex(/^https?:\/\//), title: z.string().max(255).optional() })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "knowledge:write")) return forbidden();
  const res = await run(() => backendFor(principal).addKnowledgeUrl(body.ref, { url: body.url, title: body.title || undefined }));
  if (res.ok) revalidatePath(path(body.ref));
  return res;
}

export async function deleteKnowledgeAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ ref, id: docId }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "knowledge:write")) return forbidden();
  const res = await run(() => backendFor(principal).deleteKnowledge(body.ref, body.id));
  if (res.ok) revalidatePath(path(body.ref));
  return res;
}

export async function reindexKnowledgeAction(raw: unknown): Promise<ActionResult<KnowledgeDocumentOut>> {
  const body = z.object({ ref, id: docId }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "knowledge:write")) return forbidden();
  const res = await run(() => backendFor(principal).reindexKnowledge(body.ref, body.id));
  if (res.ok) revalidatePath(path(body.ref));
  return res;
}
