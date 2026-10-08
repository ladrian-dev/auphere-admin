import type { InboxConversation, InboxDetail, InboxPage, InboxThreadItem } from "@/lib/backend/inbox";

/** Spec 030: what the API answers, shaped like the contract, for the Inbox tests. */
export const NOW = new Date("2026-10-08T12:00:00Z");

export function conversation(o: Partial<InboxConversation> = {}): InboxConversation {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    contact: { name: "Ana Torres", handle: "+5491100000001", initials: "AT" },
    channel: { kind: "whatsapp" },
    agent: null,
    state: "agent",
    assignee: null,
    last_message: {
      at: "2026-10-08T11:30:00Z",
      author: { kind: "contact", name: null, is_me: false },
      preview: "¿Tienen turno para el sábado?",
      has_media: false,
    },
    unread: false,
    tags: [],
    ...o,
  };
}

export function page(items: InboxConversation[], o: Partial<InboxPage> = {}): InboxPage {
  return {
    items,
    next_cursor: null,
    counts: { unread: items.filter((c) => c.unread).length, waiting: items.filter((c) => c.state === "waiting").length },
    has_any: items.length > 0,
    channel_kinds: ["whatsapp"],
    ...o,
  };
}

export function detail(o: Partial<InboxDetail> = {}): InboxDetail {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    state: "agent",
    assignee: null,
    agent: null,
    control_version: 3,
    window: { open: true, closes_at: "2026-10-09T11:30:00Z" },
    channel: { kind: "whatsapp", connected: true },
    contact: { name: "Ana Torres", handle: "+5491100000001", first_message_at: "2026-09-01T10:00:00Z", conversations: 2 },
    summary: null,
    waiting_reason: null,
    tags: [],
    note: { body: "", updated_at: null },
    activity: [],
    ...o,
  };
}

export function message(o: Partial<InboxThreadItem> = {}): InboxThreadItem {
  return {
    type: "message",
    id: `m-${Math.random().toString(36).slice(2, 8)}`,
    at: "2026-10-08T11:30:00Z",
    direction: "inbound",
    author: { kind: "contact", name: null, is_me: false },
    text: "Hola",
    media: null,
    delivery: null,
    failure_reason: null,
    kind: null,
    detail: null,
    ...o,
  };
}

export const ME = { kind: "member" as const, name: "Valeria Ríos", is_me: true };
