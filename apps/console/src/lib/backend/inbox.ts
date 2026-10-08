import type { Call } from "../backend";
import { q } from "../backend";

/**
 * Lane `inbox` (spec 030, US5–US10): the client's Bandeja de entrada, all
 * under `/console/lite/inbox/*`. The only console calls that carry message
 * bodies (C8 exception, ADR-041) — and only a client person with the
 * `inbox` module reaches them. No client reference travels: the API takes
 * the client from the verified person and runs every read under its RLS.
 */
export type InboxFilter = "all" | "unread" | "waiting" | "resolved";
export type InboxState = "agent" | "waiting" | "person" | "resolved";
export type InboxAuthorKind = "contact" | "agent" | "member" | "operator" | "system";

export type InboxAuthor = { kind: InboxAuthorKind; name: string | null; is_me: boolean };

export type InboxConversation = {
  id: string;
  contact: { name: string; handle: string; initials: string };
  channel: { kind: string };
  agent: { id: string; name: string } | null;
  state: InboxState;
  assignee: InboxAuthor | null;
  last_message: { at: string; author: InboxAuthor; preview: string; has_media: boolean } | null;
  unread: boolean;
  tags: string[];
};

export type InboxCounts = { unread: number; waiting: number };

export type InboxPage = {
  items: InboxConversation[];
  next_cursor: string | null;
  counts: InboxCounts;
  /** Whether the client has any conversation at all — tells an empty inbox from an empty filter. */
  has_any: boolean;
  channel_kinds: string[];
};

export type InboxActivity = { kind: string; at: string; actor: InboxAuthor; detail: string | null };

export type InboxDetail = {
  id: string;
  state: InboxState;
  assignee: InboxAuthor | null;
  agent: { id: string; name: string } | null;
  /** `If-Match` for take over / give back: who answers changed since you looked → 412. */
  control_version: number;
  window: { open: boolean; closes_at: string | null };
  channel: { kind: string; connected: boolean };
  contact: { name: string; handle: string; first_message_at: string | null; conversations: number };
  summary: string | null;
  waiting_reason: string | null;
  tags: string[];
  note: { body: string; updated_at: string | null };
  activity: InboxActivity[];
};

export type InboxMedia = { kind: string | null; filename: string | null; transcript: string | null };

export type InboxThreadItem = {
  type: "message" | "event";
  id: string;
  at: string;
  direction: "inbound" | "outbound" | null;
  author: InboxAuthor | null;
  text: string | null;
  media: InboxMedia | null;
  delivery: "pending" | "sent" | "delivered" | "read" | "failed" | null;
  failure_reason: string | null;
  kind: string | null;
  detail: string | null;
};

export type InboxThread = { items: InboxThreadItem[]; next_before: string | null };
export type InboxSent = { id: string; at: string; delivery: string };
export type SavedReply = { id: string; title: string; body: string };

/** Backend paths the BFF route handlers proxy. */
export const inboxStreamPath = "/console/lite/inbox/stream";
export const inboxMediaPath = (messageId: string) => `/console/lite/inbox/messages/${encodeURIComponent(messageId)}/media`;
export const inboxAttachmentPath = (conversationId: string) =>
  `/console/lite/inbox/conversations/${encodeURIComponent(conversationId)}/attachments`;

const C = "/console/lite/inbox/conversations";

export function inboxApi(call: Call) {
  const enc = encodeURIComponent;
  const ifMatch = (version?: number) => (version === undefined ? undefined : { "If-Match": String(version) });
  return {
    inboxList: (p: { filter?: InboxFilter; q?: string; agent?: string; cursor?: string; limit?: number } = {}) =>
      call<InboxPage>(`${C}${q(p)}`),
    inboxCounts: () => call<InboxCounts>("/console/lite/inbox/counts"),
    inboxDetail: (id: string) => call<InboxDetail>(`${C}/${enc(id)}`),
    inboxThread: (id: string, p: { before?: string; limit?: number } = {}) =>
      call<InboxThread>(`${C}/${enc(id)}/messages${q(p)}`),
    inboxMarkRead: (id: string) => call<null>(`${C}/${enc(id)}/read`, { method: "POST" }),
    inboxMarkUnread: (id: string) => call<null>(`${C}/${enc(id)}/unread`, { method: "POST" }),
    inboxTakeOver: (id: string, version?: number) =>
      call<InboxDetail>(`${C}/${enc(id)}/takeover`, { method: "POST", headers: ifMatch(version) }),
    inboxGiveBack: (id: string, version?: number) =>
      call<InboxDetail>(`${C}/${enc(id)}/release`, { method: "POST", headers: ifMatch(version) }),
    inboxSend: (id: string, text: string) =>
      call<InboxSent>(`${C}/${enc(id)}/messages`, { method: "POST", body: { text } }),
    inboxResolve: (id: string) => call<InboxDetail>(`${C}/${enc(id)}/resolve`, { method: "POST" }),
    inboxReopen: (id: string) => call<InboxDetail>(`${C}/${enc(id)}/reopen`, { method: "POST" }),
    inboxSetTags: (id: string, tags: string[]) =>
      call<{ tags: string[] }>(`${C}/${enc(id)}/tags`, { method: "PUT", body: { tags } }),
    inboxSuggestedTags: () => call<{ tags: string[] }>("/console/lite/inbox/tags"),
    inboxSetNote: (id: string, body: string) =>
      call<{ body: string; updated_at: string | null }>(`${C}/${enc(id)}/note`, { method: "PUT", body: { body } }),
    inboxReplies: () => call<SavedReply[]>("/console/lite/inbox/replies"),
    inboxCreateReply: (body: { title: string; body: string }) =>
      call<SavedReply>("/console/lite/inbox/replies", { method: "POST", body }),
    inboxEditReply: (id: string, body: { title?: string; body?: string }) =>
      call<SavedReply>(`/console/lite/inbox/replies/${enc(id)}`, { method: "PATCH", body }),
    inboxArchiveReply: (id: string) => call<null>(`/console/lite/inbox/replies/${enc(id)}`, { method: "DELETE" }),
  };
}
