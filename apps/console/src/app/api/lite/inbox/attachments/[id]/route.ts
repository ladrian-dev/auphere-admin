import { z } from "zod";

import { checkAttachment } from "@/components/inbox/inbox-model";
import { tokenFor } from "@/lib/backend";
import { inboxAttachmentPath } from "@/lib/backend/inbox";
import { env } from "@/lib/env";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

/**
 * Spec 030 (R10.3): a person of the client sends an image or a PDF. A route
 * handler and not a Server Action because the body is a file: the file is
 * checked here against the same rules as the API (type and size, refused
 * before the upload with the limit said) and forwarded as multipart. The API
 * checks again and decides — same 409s as a text.
 */
export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, { detail: "Not signed in" });
  const principal = res.principal;
  if (principal.kind !== "client" || !principal.modules.includes("inbox")) return json(403, { detail: "Missing module inbox" });

  const p = params.safeParse(await ctx.params);
  if (!p.success) return json(422, { detail: "Invalid id" });

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return json(422, { detail: "Invalid form" });
  }
  const file = form.get("file");
  if (!(file instanceof File)) return json(422, { detail: "Missing file" });
  const check = checkAttachment(file);
  if (!check.ok) {
    return check.reason === "type"
      ? json(415, { detail: { code: "type_not_allowed" } })
      : json(413, { detail: { code: "too_large", limit_bytes: check.maxMb * 1024 * 1024 } });
  }
  const caption = form.get("caption");

  const out = new FormData();
  out.set("file", file, file.name);
  if (typeof caption === "string" && caption.trim()) out.set("caption", caption.trim().slice(0, 1024));

  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}${inboxAttachmentPath(p.data.id)}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await tokenFor(principal)}`, Accept: "application/json" },
    body: out,
    cache: "no-store",
    signal: request.signal,
  });
  const text = await upstream.text();
  return new Response(text || "{}", {
    status: upstream.status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
