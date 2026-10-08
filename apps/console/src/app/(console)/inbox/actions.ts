"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  InboxCounts,
  InboxDetail,
  InboxPage,
  InboxSent,
  InboxThread,
  SavedReply,
} from "@/lib/backend/inbox";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Server Actions of the Inbox (spec 030, US5–US10). Zod on the server, a
 * fresh 60 s token per call; the API decides and its answer travels back as
 * `{ok:false,status,code,info}` — a 409 names the case (`window_closed`…),
 * a 412 carries the conversation as it really is now.
 *
 * Only the person of a client with the `inbox` module may call these; the
 * API answers 403 to anyone else, and the console says it first.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

async function inboxPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("inbox") ? res.principal : null;
}

const id = z.string().uuid();
const cursor = z.string().min(1).max(200);

const listSchema = z.object({
  filter: z.enum(["all", "unread", "waiting", "resolved"]).default("all"),
  q: z.string().trim().max(120).optional(),
  agent: id.optional(),
  cursor: cursor.optional(),
});
export async function listConversationsAction(raw: unknown): Promise<ActionResult<InboxPage>> {
  const p = listSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxList({ filter: p.filter, q: p.q || undefined, agent: p.agent, cursor: p.cursor }));
}

export async function inboxCountsAction(): Promise<ActionResult<InboxCounts>> {
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxCounts());
}

/** Opening a conversation reads it: detail, the latest page of the thread, and «read» for this person. */
const openSchema = z.object({ id, markRead: z.boolean().default(true) });
export async function openConversationAction(
  raw: unknown,
): Promise<ActionResult<{ detail: InboxDetail; thread: InboxThread }>> {
  const p = openSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  const api = backendFor(principal);
  return run(async () => {
    const [detail, thread] = await Promise.all([api.inboxDetail(p.id), api.inboxThread(p.id)]);
    if (p.markRead) await api.inboxMarkRead(p.id);
    return { detail, thread };
  });
}

const olderSchema = z.object({ id, before: cursor });
export async function loadOlderAction(raw: unknown): Promise<ActionResult<InboxThread>> {
  const p = olderSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxThread(p.id, { before: p.before }));
}

const idSchema = z.object({ id });
export async function markUnreadAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxMarkUnread(p.id));
}

const controlSchema = z.object({ id, version: z.number().int().min(0).optional() });
export async function takeOverAction(raw: unknown): Promise<ActionResult<InboxDetail>> {
  const p = controlSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxTakeOver(p.id, p.version));
}

export async function giveBackAction(raw: unknown): Promise<ActionResult<InboxDetail>> {
  const p = controlSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxGiveBack(p.id, p.version));
}

const sendSchema = z.object({ id, text: z.string().max(4096).refine((v) => v.trim().length > 0) });
export async function sendMessageAction(raw: unknown): Promise<ActionResult<InboxSent>> {
  const p = sendSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxSend(p.id, p.text));
}

export async function resolveAction(raw: unknown): Promise<ActionResult<InboxDetail>> {
  const p = idSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxResolve(p.id));
}

export async function reopenAction(raw: unknown): Promise<ActionResult<InboxDetail>> {
  const p = idSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxReopen(p.id));
}

const tagsSchema = z.object({ id, tags: z.array(z.string().max(80)).max(20) });
export async function setTagsAction(raw: unknown): Promise<ActionResult<{ tags: string[] }>> {
  const p = tagsSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxSetTags(p.id, p.tags));
}

export async function suggestedTagsAction(): Promise<ActionResult<{ tags: string[] }>> {
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxSuggestedTags());
}

const noteSchema = z.object({ id, body: z.string().max(4000) });
export async function setNoteAction(raw: unknown): Promise<ActionResult<{ body: string; updated_at: string | null }>> {
  const p = noteSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxSetNote(p.id, p.body));
}

export async function repliesAction(): Promise<ActionResult<SavedReply[]>> {
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxReplies());
}

const replySchema = z.object({ title: z.string().trim().min(1).max(80), body: z.string().trim().min(1).max(1000) });
export async function createReplyAction(raw: unknown): Promise<ActionResult<SavedReply>> {
  const p = replySchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxCreateReply(p));
}

const editReplySchema = replySchema.partial().extend({ id });
export async function editReplyAction(raw: unknown): Promise<ActionResult<SavedReply>> {
  const { id: replyId, ...body } = editReplySchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxEditReply(replyId, body));
}

/** «Borrar» archives (constitution §IV): the reply stops being listed. */
export async function archiveReplyAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await inboxPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).inboxArchiveReply(p.id));
}
