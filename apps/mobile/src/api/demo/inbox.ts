import type { Conversation, Detail } from "../endpoints";
import type { components } from "../schema.gen";

import { AGENT, CHANNELS, CONVERSATION_IDS, SUGGESTED_TAGS, USER, daysBefore, localDate, uuid, type ChannelKind, type DemoKey, type EventKind, type Seed, type Who } from "./data";
import { DemoHttpError, refuse } from "./http";

type S = components["schemas"];

/**
 * The example Bandeja, in memory, with the API's rules where the screens
 * depend on them (`api/console/lite/inbox.py`, `services/inbox_view.py`,
 * `services/inbox_lifecycle.py`):
 *
 * - the state is `resolved` · `waiting` · `person` · `agent`, in that order;
 * - «Todas» leaves the resolved out; the counts are of what is not resolved;
 * - taking over and giving back carry the control version (`If-Match`): a
 *   stale one is a 412 with the conversation as it is now;
 * - only who answers can send, and only while the contact's window is open;
 * - resolving and reopening hand it back to the agent; archiving takes it out
 *   of the Bandeja (404 from then on); clearing empties the thread.
 *
 * Every view is computed on each read, so Inicio, the counts and the lists
 * always agree with what was done.
 */
export type ItemOut = S["ConversationItemOut"] & Conversation;
export type DetailOut = S["ConversationDetailOut"] & Detail;
export type Filter = "all" | "unread" | "waiting" | "resolved";

const ME: S["AuthorOut"] = { kind: "member", is_me: true, name: USER.name };
const AVA: S["AuthorOut"] = { kind: "agent", is_me: false, name: AGENT.name };
const SYSTEM: S["AuthorOut"] = { kind: "system", is_me: false, name: null };

const DAY = 24 * 3600_000;
/** How long a person can still write after the contact's last message (spec 049: a week on Instagram and Messenger). */
const PERSON_WINDOW: Record<ChannelKind, number> = { whatsapp: DAY, instagram: 7 * DAY, messenger: 7 * DAY };
/** A message of this phone reads «Enviado» for a moment, then «Entregado». */
const SETTLE_MS = 1500;

type Status = "open" | "escalated" | "closed";

type Conv = {
  id: string;
  key: DemoKey;
  name: string;
  handle: string;
  channel: ChannelKind;
  firstMessageAt: string;
  conversations: number;
  status: Status;
  agentActive: boolean;
  mine: boolean;
  version: number;
  unread: boolean;
  tags: string[];
  note: S["NoteOut"];
  summary: string | null;
  waiting: { code: string; reason: string | null; since: string } | null;
  items: S["ThreadItemOut"][];
  activity: S["ActivityOut"][];
  posts: Map<string, S["CommentPostOut"]>;
  lastAt: number;
  lastInboundAt: number | null;
  archived: boolean;
  /** Sends by `Idempotency-Key`: a retry is the same message (R6.4). */
  sent: Map<string, S["SentOut"]>;
  settle: Map<string, number>;
};

const iso = (ms: number) => new Date(ms).toISOString();

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "·";
}

/** Lower case without accents, so «sena» finds «seña» (a runtime without `normalize` still compares in lower case). */
function fold(s: string): string {
  try {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  } catch {
    return s.toLowerCase();
  }
}

function blank(): Pick<S["ThreadItemOut"], "comment" | "unsent" | "opted_out" | "delivery" | "failure_reason" | "kind" | "detail" | "media" | "text" | "direction"> {
  return { comment: false, unsent: false, opted_out: false, delivery: null, failure_reason: null, kind: null, detail: null, media: null, text: null, direction: null };
}

export class Inbox {
  private convs: Conv[] = [];
  private seq = 0;

  constructor(seeds: readonly Seed[], now: number) {
    for (const s of seeds) this.add(s, now);
  }

  private nextId(): string {
    this.seq += 1;
    return uuid("a", this.seq);
  }

  private author(who: Who, contact: string): S["AuthorOut"] {
    if (who === "contact") return { kind: "contact", is_me: false, name: contact };
    if (who === "agent") return AVA;
    if (who === "me") return ME;
    return SYSTEM;
  }

  /** A conversation from its seed; `false` when it is already here (an arrival is told once). */
  add(seed: Seed, now: number): boolean {
    const id = CONVERSATION_IDS[seed.key];
    if (this.convs.some((c) => c.id === id)) return false;
    const items: S["ThreadItemOut"][] = [];
    const activity: S["ActivityOut"][] = [];
    const posts = new Map<string, S["CommentPostOut"]>();
    let lastInboundAt: number | null = null;
    let since: string | null = null;
    for (const line of seed.lines) {
      const itemId = this.nextId();
      if ("event" in line) {
        const actor = this.author(line.by, seed.name);
        items.push({ ...blank(), type: "event", id: itemId, at: iso(line.at), kind: line.event, author: actor, detail: line.detail ?? null });
        activity.push({ kind: line.event, at: iso(line.at), actor, detail: line.detail ?? null });
        if (line.event === "escalated") since = iso(line.at);
        continue;
      }
      const out = line.from !== "contact";
      if (!out) lastInboundAt = Math.max(lastInboundAt ?? 0, line.at);
      items.push({
        ...blank(),
        type: "message",
        id: itemId,
        at: iso(line.at),
        direction: out ? "outbound" : "inbound",
        author: this.author(line.from, seed.name),
        text: line.text ?? null,
        media: line.media ? { kind: line.media.kind, filename: line.media.filename, transcript: line.media.transcript } : null,
        delivery: out ? (line.delivery ?? "read") : null,
        failure_reason: line.failure ?? null,
        comment: line.comment ?? false,
      });
      if (line.post) posts.set(itemId, line.post);
    }
    const first = seed.lines[0]?.at ?? now;
    const status: Status = seed.state === "resolved" ? "closed" : seed.state === "waiting" ? "escalated" : "open";
    this.convs.push({
      id,
      key: seed.key,
      name: seed.name,
      handle: seed.handle,
      channel: seed.channel,
      firstMessageAt: iso(seed.history.firstDaysAgo > 0 ? daysBefore(now, seed.history.firstDaysAgo) : first),
      conversations: seed.history.conversations,
      status,
      agentActive: seed.state !== "person",
      mine: seed.state === "person",
      version: 1,
      unread: seed.unread ?? false,
      tags: [...(seed.tags ?? [])],
      note: { body: seed.note ?? "", updated_at: seed.note ? iso(daysBefore(now, 1)) : null },
      summary: seed.summary ?? null,
      waiting: seed.waiting ? { code: seed.waiting.code, reason: seed.waiting.reason, since: since ?? iso(now) } : null,
      items,
      activity,
      posts,
      lastAt: seed.lines.reduce((a, l) => Math.max(a, l.at), first),
      lastInboundAt,
      archived: false,
      sent: new Map(),
      settle: new Map(),
    });
    return true;
  }

  private find(id: string): Conv {
    const c = this.convs.find((x) => x.id === id && !x.archived);
    // The API's own 404 for a conversation it does not show (`_not_found`).
    if (!c) throw new DemoHttpError(404, { detail: "Unknown conversation" });
    return c;
  }

  private stateOf(c: Conv): ItemOut["state"] {
    if (c.status === "closed") return "resolved";
    if (c.status === "escalated") return "waiting";
    if (!c.agentActive) return "person";
    return "agent";
  }

  private window(c: Conv, now: number): S["WindowOut"] {
    if (c.lastInboundAt == null) return { open: false, agent_open: false, closes_at: null };
    const closes = c.lastInboundAt + PERSON_WINDOW[c.channel];
    return { open: closes > now, agent_open: c.lastInboundAt + DAY > now, closes_at: iso(closes) };
  }

  private settled(c: Conv, now: number): void {
    for (const [id, at] of c.settle) {
      if (at > now) continue;
      const item = c.items.find((i) => i.id === id);
      if (item && item.delivery === "sent") item.delivery = "delivered";
      c.settle.delete(id);
    }
  }

  private record(c: Conv, kind: EventKind, actor: S["AuthorOut"], now: number, detail: string | null = null): void {
    c.items.push({ ...blank(), type: "event", id: this.nextId(), at: iso(now), kind, author: actor, detail });
    c.activity.push({ kind, at: iso(now), actor, detail });
    c.lastAt = now;
  }

  // ── reads ───────────────────────────────────────────────────────────

  private visible(): Conv[] {
    return this.convs.filter((c) => !c.archived);
  }

  counts(): S["CountsOut"] {
    const open = this.visible().filter((c) => c.status !== "closed");
    return { unread: open.filter((c) => c.unread).length, waiting: this.visible().filter((c) => c.status === "escalated").length };
  }

  /** The one «Atender» opens first: the waiting one whose contact wrote last. */
  firstWaiting(): string | null {
    const waiting = this.visible()
      .filter((c) => c.status === "escalated")
      .sort((a, b) => (b.lastInboundAt ?? 0) - (a.lastInboundAt ?? 0));
    return waiting[0]?.id ?? null;
  }

  /** Conversations per day over the last seven, by their last activity (Inicio's bars). */
  daily(now: number): S["DayCountOut"][] {
    const out: S["DayCountOut"][] = [];
    for (let ago = 6; ago >= 0; ago--) {
      const day = localDate(daysBefore(now, ago));
      out.push({ day, count: this.visible().filter((c) => localDate(c.lastAt) === day).length });
    }
    return out;
  }

  private item(c: Conv): ItemOut {
    const state = this.stateOf(c);
    const last = [...c.items].reverse().find((i) => i.type === "message") ?? null;
    return {
      id: c.id,
      contact: { name: c.name, handle: c.handle, initials: initials(c.name), has_avatar: false },
      channel: { kind: c.channel },
      agent: { id: AGENT.id, name: AGENT.name },
      handled_by_agent: { id: AGENT.id, name: AGENT.name },
      state,
      assignee: c.mine ? ME : null,
      last_message: last
        ? { at: last.at, author: last.author ?? SYSTEM, has_media: last.media != null, preview: last.text ?? "" }
        : null,
      unread: c.unread,
      tags: [...c.tags],
      waiting: state === "waiting" && c.waiting ? { reason: c.waiting.reason, since: c.waiting.since } : null,
      // In the list the reason is the code; the agent's words ride in `waiting.reason` (`inbox.py`).
      waiting_reason: state === "waiting" ? (c.waiting?.code ?? null) : null,
    };
  }

  list(q: { filter: Filter; q?: string; channel?: string; agent?: string; cursor?: string; limit?: number }): S["nexus_api__api__console__lite__inbox__ConversationPageOut"] & { items: ItemOut[] } {
    const visible = this.visible();
    let rows = visible.filter((c) =>
      q.filter === "resolved" ? c.status === "closed" : q.filter === "waiting" ? c.status === "escalated" : c.status !== "closed" && (q.filter !== "unread" || c.unread),
    );
    if (q.channel) rows = rows.filter((c) => c.channel === q.channel);
    if (q.agent && q.agent !== AGENT.id) rows = [];
    const needle = q.q ? fold(q.q.trim()) : "";
    if (needle) {
      rows = rows.filter((c) => [c.name, c.handle, ...c.items.map((i) => i.text ?? "")].some((s) => fold(s).includes(needle)));
    }
    rows.sort((a, b) => b.lastAt - a.lastAt);
    const limit = Math.min(50, Math.max(1, q.limit ?? 50));
    const start = Math.max(0, Number(q.cursor) || 0);
    const page = rows.slice(start, start + limit);
    const hasAny = visible.length > 0;
    const plain = q.filter === "all" && !needle && !q.agent && !q.channel && !q.cursor;
    return {
      items: page.map((c) => this.item(c)),
      next_cursor: start + limit < rows.length ? String(start + limit) : null,
      counts: this.counts(),
      has_any: hasAny,
      channel_kinds: [...CHANNELS].sort(),
      resolved: plain && page.length === 0 && hasAny ? visible.filter((c) => c.status === "closed").length : 0,
    };
  }

  detail(id: string, now: number): DetailOut {
    const c = this.find(id);
    const state = this.stateOf(c);
    const waiting = state === "waiting" ? c.waiting : null;
    return {
      id: c.id,
      state,
      assignee: c.mine ? ME : null,
      agent: { id: AGENT.id, name: AGENT.name },
      handled_by_agent: { id: AGENT.id, name: AGENT.name },
      control_version: c.version,
      window: this.window(c, now),
      channel: { kind: c.channel, connected: true },
      contact: {
        name: c.name,
        handle: c.handle,
        has_avatar: false,
        first_message_at: c.firstMessageAt,
        conversations: c.conversations,
        next_booking: null,
      },
      summary: c.summary,
      // In the detail the reason is the agent's words and the code rides apart (`_detail_out`).
      waiting_reason: waiting?.reason ?? null,
      waiting_code: waiting?.code ?? null,
      waiting_since: waiting?.since ?? null,
      tags: [...c.tags],
      note: { ...c.note },
      activity: c.activity.map((a) => ({ ...a })),
    };
  }

  /** Oldest first, a page of `limit` ending before `before` (an index), as the API pages it. */
  thread(id: string, now: number, before?: string, limit = 100): S["nexus_api__api__console__lite__inbox__ThreadOut"] {
    const c = this.find(id);
    this.settled(c, now);
    const end = before !== undefined && before !== "" ? Math.max(0, Math.min(c.items.length, Number(before) || 0)) : c.items.length;
    const start = Math.max(0, end - Math.min(100, Math.max(1, limit)));
    return { items: c.items.slice(start, end).map((i) => ({ ...i, media: i.media ? { ...i.media } : null })), next_before: start > 0 ? String(start) : null };
  }

  contactName(id: string): string {
    return this.find(id).name;
  }

  /** The post a comment is under (Instagram), or `null` for a message that is not a comment. */
  post(conversationId: string, messageId: string): S["CommentPostOut"] | null {
    const c = this.find(conversationId);
    if (!c.items.some((i) => i.id === messageId)) throw new DemoHttpError(404, { detail: "Unknown message" });
    const post = c.posts.get(messageId);
    return post ? { ...post } : null;
  }

  /** An answer of the agent and what the contact had asked just before (for «Corregir»). */
  agentReply(conversationId: string, messageId: string): { text: string; asked: string | null; contact: string } {
    const c = this.find(conversationId);
    const at = c.items.findIndex((i) => i.id === messageId);
    const item = c.items[at];
    if (!item) throw new DemoHttpError(404, { detail: "Unknown message" });
    if (item.type !== "message" || item.author?.kind !== "agent") throw refuse(422, "not_an_agent_reply");
    const asked = [...c.items.slice(0, at)].reverse().find((i) => i.type === "message" && i.direction === "inbound" && i.text)?.text ?? null;
    return { text: item.text ?? "", asked, contact: c.name };
  }

  suggestedTags(): S["TagsOut"] {
    const all = [...SUGGESTED_TAGS, ...this.visible().flatMap((c) => c.tags)];
    return { tags: all.filter((t, i) => all.findIndex((x) => fold(x) === fold(t)) === i) };
  }

  // ── writes ──────────────────────────────────────────────────────────

  markRead(id: string, unread: boolean): void {
    this.find(id).unread = unread;
  }

  private checkVersion(c: Conv, version: number | null, now: number): void {
    if (version === null || version === c.version) return;
    throw new DemoHttpError(412, {
      detail: { error: "version_mismatch", expected: version, actual: c.version, conversation: this.detail(c.id, now) },
    });
  }

  /** The person comes in: the agent goes quiet in this conversation (R9.2). */
  takeOver(id: string, version: number | null, now: number): DetailOut {
    const c = this.find(id);
    if (!c.agentActive && c.mine) return this.detail(id, now);
    this.checkVersion(c, version, now);
    c.agentActive = false;
    c.mine = true;
    c.version += 1;
    c.status = "open";
    c.waiting = null;
    this.record(c, "takeover", ME, now);
    return this.detail(id, now);
  }

  /** Back to the agent (R9.3). A waiting one nobody took can be given back too. */
  giveBack(id: string, version: number | null, now: number): DetailOut {
    const c = this.find(id);
    const waitingUnattended = c.status === "escalated" && !c.mine;
    if (c.agentActive && !waitingUnattended) return this.detail(id, now);
    this.checkVersion(c, version, now);
    c.agentActive = true;
    c.mine = false;
    c.version += 1;
    if (c.status === "escalated") c.status = "open";
    c.waiting = null;
    this.record(c, "released", ME, now);
    return this.detail(id, now);
  }

  resolve(id: string, now: number): DetailOut {
    const c = this.find(id);
    if (c.status !== "closed") {
      c.status = "closed";
      c.mine = false;
      c.waiting = null;
      if (!c.agentActive) {
        c.agentActive = true;
        c.version += 1;
      }
      this.record(c, "resolved", ME, now);
    }
    return this.detail(id, now);
  }

  reopen(id: string, now: number): DetailOut {
    const c = this.find(id);
    if (c.status === "closed") {
      c.status = "open";
      c.mine = false;
      c.waiting = null;
      if (!c.agentActive) {
        c.agentActive = true;
        c.version += 1;
      }
      this.record(c, "reopened", ME, now);
    }
    return this.detail(id, now);
  }

  /** «Vaciar el chat»: empty for the Bandeja and the agent; the contact's window stays. */
  clear(id: string, now: number): DetailOut {
    const c = this.find(id);
    c.items = [];
    c.posts.clear();
    c.settle.clear();
    return this.detail(id, now);
  }

  /** «Eliminar el chat»: resolved and out of the Bandeja. */
  archive(id: string, now: number): void {
    this.resolve(id, now);
    this.find(id).archived = true;
  }

  private canSend(c: Conv, now: number): void {
    if (c.agentActive || !c.mine) throw refuse(409, "not_assigned_to_you");
    if (!this.window(c, now).open) throw refuse(409, "window_closed");
  }

  private push(c: Conv, now: number, fields: Partial<S["ThreadItemOut"]>, key: string | null): { sent: S["SentOut"]; replay: boolean } {
    const seen = key ? c.sent.get(key) : undefined;
    if (seen) return { sent: seen, replay: true };
    this.canSend(c, now);
    const id = this.nextId();
    c.items.push({ ...blank(), type: "message", id, at: iso(now), direction: "outbound", author: ME, delivery: "sent", ...fields });
    c.settle.set(id, now + SETTLE_MS);
    c.lastAt = now;
    c.unread = false;
    const sent: S["SentOut"] = { id, at: iso(now), delivery: "pending" };
    if (key) c.sent.set(key, sent);
    return { sent, replay: false };
  }

  send(id: string, text: string, key: string | null, now: number): { sent: S["SentOut"]; replay: boolean } {
    const c = this.find(id);
    if (!text.trim()) {
      throw new DemoHttpError(422, { detail: [{ loc: ["body", "text"], msg: "Value error, empty", type: "value_error" }] });
    }
    return this.push(c, now, { text }, key);
  }

  /** An image or a PDF (R6.3): it goes as a message with its file. */
  attach(id: string, file: { name: string | null; type: string | null }, key: string | null, now: number): { sent: S["SentOut"]; replay: boolean } {
    const c = this.find(id);
    const kind = file.type === "application/pdf" ? "document" : "image";
    const filename = file.name ?? (kind === "image" ? "foto.jpg" : "documento.pdf");
    return this.push(c, now, { media: { kind, filename, transcript: null } }, key);
  }

  setTags(id: string, tags: readonly string[]): S["TagsOut"] {
    const c = this.find(id);
    const clean: string[] = [];
    for (const raw of tags) {
      const t = raw.trim().slice(0, 32);
      if (t && !clean.some((x) => fold(x) === fold(t))) clean.push(t);
    }
    c.tags = clean.slice(0, 10);
    return { tags: [...c.tags] };
  }

  setNote(id: string, body: string, now: number): S["NoteOut"] {
    const c = this.find(id);
    c.note = { body: body.slice(0, 4000), updated_at: iso(now) };
    return { ...c.note };
  }
}
