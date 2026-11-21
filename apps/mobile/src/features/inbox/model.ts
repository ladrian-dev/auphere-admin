import type { Author, Conversation, Detail, ThreadItem } from "@/api/endpoints";
import type { Locale, MessageKey, T } from "@/i18n/t";

/**
 * The Bandeja's pure decisions (spec 031, R5, R6), the same as the console's
 * (`apps/console/src/components/inbox/inbox-model.ts`, `event-text.ts`): what
 * the composer offers, how a time reads, who did what. Tested without rendering.
 */

// ── composer ──────────────────────────────────────────────────────────

/**
 * What the foot offers. Spec 044 (R11) adds, when known, the agent's name and —
 * while it waits — since when (`waiting_since` from the API, or the last
 * «escalated» of the activity).
 */
export type ComposerMode =
  | { kind: "resolved" }
  | { kind: "waiting"; reason: string | null; since?: string | null; agent?: string | null; code?: string }
  /**
   * The agent answers. Spec 049 (7.3) and spec 069 (R11.5): when it no longer
   * can — `windowClosed`, the contact's window closed for everybody, or
   * `personUntil`, Instagram / Messenger past the agent's 24 h, when a person
   * still can until then — the foot says so instead of «responde el agente».
   */
  | { kind: "agent"; agent?: string | null; windowClosed?: true; personUntil?: string }
  | { kind: "other"; name: string | null }
  | { kind: "mine"; blocked: "window_closed" | "channel_disconnected" | null; agent?: string | null };

export function composerMode(
  d: Pick<Detail, "state" | "assignee" | "waiting_reason" | "window" | "channel"> & Partial<Pick<Detail, "agent" | "waiting_since" | "activity" | "waiting_code">>,
): ComposerMode {
  const agent = d.agent?.name ?? null;
  if (d.state === "resolved") return { kind: "resolved" };
  if (d.state === "waiting" && !d.assignee) {
    // Spec 047 (50.7): the code of why it waits (`events.md` §2) next to the agent's own words (045).
    const code = d.waiting_code ?? undefined;
    return { kind: "waiting", reason: d.waiting_reason ?? null, since: d.waiting_since ?? lastEscalatedAt(d.activity ?? []), agent, ...(code ? { code } : {}) };
  }
  if (d.state === "agent") {
    // The console's rule (`inbox-model.ts`): closed for everybody first, then the agent's own 24 h.
    if (!d.window.open) return { kind: "agent", agent, windowClosed: true };
    if (d.window.agent_open === false && d.window.closes_at) return { kind: "agent", agent, personUntil: d.window.closes_at };
    return { kind: "agent", agent };
  }
  if (d.assignee && !d.assignee.is_me) return { kind: "other", name: d.assignee.name ?? null };
  if (!d.channel.connected) return { kind: "mine", blocked: "channel_disconnected", agent };
  if (!d.window.open) return { kind: "mine", blocked: "window_closed", agent };
  return { kind: "mine", blocked: null, agent };
}

/** When the agent last asked for a person, from the activity (spec 044, R11.1). */
export function lastEscalatedAt(activity: readonly { kind: string; at: string }[]): string | null {
  const last = activity.filter((a) => a.kind === "escalated").sort((a, b) => a.at.localeCompare(b.at)).at(-1);
  return last?.at ?? null;
}

/** «12 min», «3 h», «2 d»: how long since a moment (spec 044, R10.1, R11.1). */
export function agoText(since: string, now: number, t: T): string {
  const min = Math.max(0, Math.floor((now - Date.parse(since)) / 60_000));
  if (min < 60) return t("app.inbox.ago.min", { n: min });
  if (min < 24 * 60) return t("app.inbox.ago.h", { n: Math.floor(min / 60) });
  return t("app.inbox.ago.d", { n: Math.floor(min / (24 * 60)) });
}

/** The API's 409 codes on a send, as the composer says them. */
export const SEND_ERRORS = ["not_assigned_to_you", "window_closed", "channel_disconnected"] as const;
export type SendError = (typeof SEND_ERRORS)[number] | "generic" | "offline";

export function sendErrorOf(code: string | null | undefined, offline = false): SendError {
  if (offline) return "offline";
  return (SEND_ERRORS as readonly string[]).includes(code ?? "") ? (code as SendError) : "generic";
}

// ── attachments (R6.3: the web's types and sizes) ─────────────────────

const MB = 1024 * 1024;
export const ATTACH_RULES: Record<string, { kind: "image" | "document"; maxBytes: number }> = {
  "image/jpeg": { kind: "image", maxBytes: 5 * MB },
  "image/png": { kind: "image", maxBytes: 5 * MB },
  "application/pdf": { kind: "document", maxBytes: 16 * MB },
};

export type AttachSource = "camera" | "library" | "document";

/** What «Adjuntar» offers, in order (spec 031 R6.3, kept by spec 069 R20.1): a photo, the gallery, a PDF. */
export function attachChoices(t: T): { label: string; source: AttachSource }[] {
  return [
    { label: t("app.inbox.attach.photo"), source: "camera" },
    { label: t("app.inbox.attach.library"), source: "library" },
    { label: t("app.inbox.attach.document"), source: "document" },
  ];
}

export type AttachCheck = { ok: true } | { ok: false; reason: "type" } | { ok: false; reason: "size"; maxMb: number };

export function checkAttachment(file: { type: string | null | undefined; size: number | null | undefined }): AttachCheck {
  const rule = ATTACH_RULES[file.type ?? ""];
  if (!rule) return { ok: false, reason: "type" };
  if ((file.size ?? 0) > rule.maxBytes) return { ok: false, reason: "size", maxMb: rule.maxBytes / MB };
  return { ok: true };
}

// ── time ──────────────────────────────────────────────────────────────

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function dayLabel(at: string, now: Date, locale: Locale, t: T): string {
  const d = new Date(at);
  if (sameDay(d, now)) return t("inbox.time.today");
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  if (sameDay(d, y)) return t("inbox.time.yesterday");
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString(locale, { day: "numeric", month: "long", ...(sameYear ? {} : { year: "numeric" }) });
}

export function listTime(at: string, now: Date, locale: Locale, t: T): string {
  const d = new Date(at);
  if (sameDay(d, now)) return d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  return dayLabel(at, now, locale, t);
}

export type ThreadRow = { kind: "day"; key: string; at: string } | { kind: "item"; key: string; item: ThreadItem };

/** Thread items (oldest first) with a separator wherever the day changes. */
export function withDaySeparators(items: ThreadItem[]): ThreadRow[] {
  const rows: ThreadRow[] = [];
  let last: Date | null = null;
  for (const item of items) {
    const d = new Date(item.at);
    if (!last || !sameDay(last, d)) rows.push({ kind: "day", key: `day-${item.at}`, at: item.at });
    rows.push({ kind: "item", key: item.id, item });
    last = d;
  }
  return rows;
}

// ── who ───────────────────────────────────────────────────────────────

export function initialsOf(name: string | null | undefined): string {
  const parts = (name ?? "").split(/\s+/).filter((p) => /^\p{L}/u.test(p));
  if (!parts.length) return "·";
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function isMe(a: Author | null | undefined): boolean {
  return Boolean(a && a.kind === "member" && a.is_me);
}

export function whoOf(a: Author | null | undefined, t: T): string {
  if (!a) return t("inbox.who.someone");
  if (a.kind === "member") return a.is_me ? t("inbox.who.you") : (a.name ?? t("inbox.who.someone"));
  if (a.kind === "operator") return t("inbox.who.operator");
  if (a.kind === "contact") return t("inbox.who.contact");
  // Spec 069 (R21.2): the agent by its name when the API gives it; «Agente» only when it does not.
  if (a.kind === "agent" && a.name) return a.name;
  return t("inbox.who.agent");
}

/** What happened, as one sentence; «Tú» gets its own verbs («Tomaste el control»). */
export function eventText(kind: string | null | undefined, a: Author | null | undefined, detail: string | null | undefined, t: T): string {
  const me = isMe(a);
  const who = whoOf(a, t);
  switch (kind) {
    case "escalated": {
      // Spec 056 (7.1): a code is the table's words, the agent's own words go after the sentence.
      const raw = (detail ?? "").trim();
      const said = reasonText(raw, t);
      return raw && said === raw ? t("inbox.event.escalated.reason", { reason: raw }) : said;
    }
    case "takeover":
      return me ? t("inbox.event.takeover.you") : t("inbox.event.takeover", { who });
    case "released":
      return me ? t("inbox.event.released.you") : t("inbox.event.released", { who });
    case "resolved":
      // Spec 064 (5.2), spec 069 (R11.7): the system closed it; it says why, not who.
      if (detail === "inactivity") return t("inbox.event.resolved.inactivity");
      return me ? t("inbox.event.resolved.you") : t("inbox.event.resolved", { who });
    case "reopened":
      if (a?.kind === "contact") return t("inbox.event.reopened.contact");
      return me ? t("inbox.event.reopened.you") : t("inbox.event.reopened", { who });
    default:
      return t("inbox.event.agent_changed");
  }
}

/** «Atiende: …» under the contact's name. */
/** Under the name, the state in words (spec 044, R11.2): waits, you, resolved, or the agent that answers. */
export function attendsLine(d: Pick<Detail, "state" | "assignee" | "agent"> & { handled_by_agent?: { name: string } | null }, t: T): string {
  if (d.state === "resolved") return t("app.inbox.attends.resolved");
  if (d.assignee) {
    return d.assignee.is_me ? t("inbox.assigned.you") : t("inbox.assigned", { name: d.assignee.name ?? t("inbox.who.someone") });
  }
  if (d.state === "waiting") return t("app.inbox.attends.waiting");
  // Spec 047 (50.7): the API says who takes it (`handled_by_agent`); the older `agent` stays the fallback.
  const agent = d.handled_by_agent ?? d.agent;
  return agent ? t("app.inbox.attends.agent", { agent: agent.name }) : t("app.inbox.attends.agent.noName");
}

/**
 * Spec 047 (50.7, `events.md` §2) and spec 056 (requisito 7): why a conversation
 * waits, in words. The same list as the console's (`lib/waiting-reasons.ts`).
 */
const WAITING_REASONS = [
  "no_balance",
  "agent_cap",
  "paused_agent",
  "paused_channel",
  "paused_client",
  "archived_client",
  "channel_problem",
  "agent_unpublished",
  "no_model",
  "provider_failure",
  "turn_limit",
  "escalated",
  "human_takeover",
  "reception_loop",
  "out_of_audience",
  "booking_unbacked",
  "agenda_not_ready",
] as const;

/** What has the shape of a code (`snake_case`), not of a sentence of the agent. */
const CODE = /^[a-z][a-z0-9_]*$/;

/** The badge of a waiting row, from the column's code: its words, or the generic sentence for one this version does not know (7.2). */
export function waitingReasonText(code: string | null | undefined, t: T): string | null {
  if (!code) return null;
  return (WAITING_REASONS as readonly string[]).includes(code) ? t(`bandeja.reason.${code}` as MessageKey) : t("inbox.event.escalated");
}

/**
 * A reason as the Bandeja reads it (spec 056, 7.1, 7.2): a code of the table is
 * its words, `escalated` or a code it does not know is «El agente pidió ayuda»,
 * and what the agent wrote when it asked for help goes as it is. Never a code.
 */
export function reasonText(raw: string | null | undefined, t: T): string {
  const text = (raw ?? "").trim();
  if (text && text !== "escalated" && (WAITING_REASONS as readonly string[]).includes(text)) return t(`bandeja.reason.${text}` as MessageKey);
  if (!text || CODE.test(text)) return t("inbox.event.escalated");
  return text;
}

/**
 * A list row's preview: who wrote it, and the text or «Archivo». Spec 069
 * (R9.1, R21.2): the agent's line goes after its name, from the data — the
 * author's, or the agent that takes the conversation — never a fixed one.
 */
export function previewOf(c: Pick<Conversation, "last_message"> & Partial<Pick<Conversation, "agent" | "handled_by_agent">>, t: T): string {
  const m = c.last_message;
  if (!m) return "";
  const text = m.preview || (m.has_media ? t("inbox.row.media") : "");
  if (isMe(m.author)) return t("inbox.row.you", { text });
  if (m.author.kind === "agent") {
    const agent = m.author.name ?? c.handled_by_agent?.name ?? c.agent?.name ?? null;
    return agent ? t("v13.inbox.row.agent", { agent, text }) : t("inbox.row.agent", { text });
  }
  return text;
}

/** The state badge of a row, in words. */
export function badgeOf(c: Pick<Conversation, "state" | "assignee">, t: T): { label: string; tone: "danger" | "positive" | "info" | "neutral" } | null {
  if (c.state === "waiting" && !c.assignee) return { label: t("inbox.badge.waiting"), tone: "danger" };
  if (c.state === "resolved") return { label: t("inbox.badge.resolved"), tone: "neutral" };
  if (c.assignee?.is_me) return { label: t("inbox.badge.mine"), tone: "positive" };
  if (c.assignee) return { label: t("inbox.badge.person", { name: c.assignee.name ?? t("inbox.who.someone") }), tone: "info" };
  return null;
}

// ── channels (spec 069, R9.1, R12.1, R21.2) ───────────────────────────

/** The channels with their own mark and name in the app; the API's enum has more kinds. */
export type KnownChannel = "whatsapp" | "instagram" | "messenger";
export const KNOWN_CHANNELS: readonly KnownChannel[] = ["whatsapp", "instagram", "messenger"];

export function channelOf(kind: string | null | undefined): KnownChannel | null {
  return (KNOWN_CHANNELS as readonly string[]).includes(kind ?? "") ? (kind as KnownChannel) : null;
}

/** The channel's name, from the data: a kind the app does not know reads as the API says it. */
export function channelName(kind: string | null | undefined, t: T): string {
  const known = channelOf(kind);
  if (known) return t(`inbox.channel.${known}`);
  const raw = (kind ?? "").trim();
  return raw ? raw[0]!.toUpperCase() + raw.slice(1) : t("inbox.filter.channel");
}

/** What the contact's identifier is (the console's `contact-panel.tsx`): a phone on WhatsApp, an account elsewhere. */
export function handleLabel(kind: string | null | undefined, t: T): string {
  return kind === "whatsapp" ? t("inbox.panel.phone") : t("inbox.panel.account");
}

// ── who answers, in the header and the contact (spec 069, R11.1) ──────

/** `paused`: the agent would answer, but its window expired (R11.5): the foot says until when a person can. */
export type ModeKind = "waiting" | "mine" | "other" | "agent" | "paused" | "resolved";

/** «Atiende {agente}», «Respondes tú», «Espera a una persona», «Resuelta»: who answers now, and its tone. */
export function modeLine(
  d: Pick<Detail, "state" | "assignee"> & {
    agent?: { name: string } | null;
    handled_by_agent?: { name: string } | null;
    /** Only the conversation knows it; the list doesn't, and says who answers. */
    window?: Pick<Detail["window"], "open" | "agent_open" | "closes_at"> | null;
  },
  t: T,
): { kind: ModeKind; text: string } {
  if (d.state === "resolved") return { kind: "resolved", text: t("app.inbox.attends.resolved") };
  if (d.state === "waiting" && !d.assignee) return { kind: "waiting", text: t("app.inbox.attends.waiting") };
  if (d.assignee?.is_me) return { kind: "mine", text: t("v13.conv.mode.you") };
  if (d.assignee) return { kind: "other", text: t("inbox.badge.person", { name: d.assignee.name ?? t("inbox.who.someone") }) };
  const agent = d.handled_by_agent ?? d.agent;
  // R11.5: the same rule as the foot (`composerMode`), never «Atiende {agente}» when it can't.
  if (d.window && (!d.window.open || (d.window.agent_open === false && d.window.closes_at))) {
    return { kind: "paused", text: agent ? t("v13.conv.mode.paused", { agent: agent.name }) : t("v13.conv.mode.paused.noName") };
  }
  return { kind: "agent", text: agent ? t("app.inbox.attends.agent", { agent: agent.name }) : t("app.inbox.attends.agent.noName") };
}

// ── the list by day (spec 069, R9.1, R9.3) ────────────────────────────

export type DayGroup = "today" | "yesterday" | "week" | "older";
export const DAY_GROUPS: readonly DayGroup[] = ["today", "yesterday", "week", "older"];

/** Whole calendar days between two moments, in the phone's zone. */
function daysBetween(at: Date, now: Date): number {
  const a = new Date(at.getFullYear(), at.getMonth(), at.getDate()).getTime();
  const b = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((b - a) / 86_400_000);
}

/**
 * Hoy, Ayer, Esta semana or Anteriores, from the last message. «Esta semana»
 * is the calendar week, Monday on, as the design reads it (demo: Wednesday 18
 * → Monday 16 is this week, Thursday 12 is earlier).
 */
export function dayGroupOf(at: string | null | undefined, now: Date): DayGroup {
  if (!at) return "older";
  const days = daysBetween(new Date(at), now);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  const sinceMonday = (now.getDay() + 6) % 7;
  if (days <= sinceMonday) return "week";
  return "older";
}

/** A row's time (design §3.8): «10:42» today, «Ayer», «lun» this week, «12 nov» before. */
export function rowTime(at: string, now: Date, locale: Locale, t: T): string {
  const d = new Date(at);
  const group = dayGroupOf(at, now);
  if (group === "today") return d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  if (group === "yesterday") return t("inbox.time.yesterday");
  if (group === "week") return d.toLocaleDateString(locale, { weekday: "short" }).replace(/\.$/, "");
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) }).replace(/\.$/, "");
}

export function isWaitingRow(c: Pick<Conversation, "state" | "assignee">): boolean {
  return c.state === "waiting" && !c.assignee;
}

export type InboxSection = "waiting" | DayGroup | "resolved";

export type InboxEntry =
  | { kind: "header"; key: string; section: InboxSection; count: number }
  | { kind: "row"; key: string; c: Conversation; first: boolean; last: boolean; pinned: boolean };

function push(out: InboxEntry[], section: InboxSection, rows: Conversation[], pinned: boolean, keyPrefix = ""): void {
  if (rows.length === 0) return;
  out.push({ kind: "header", key: `${keyPrefix}h-${section}`, section, count: rows.length });
  rows.forEach((c, i) => out.push({ kind: "row", key: `${keyPrefix}${c.id}`, c, first: i === 0, last: i === rows.length - 1, pinned }));
}

/**
 * The rows as the list draws them (R9.1, R9.3): who waits for a person first,
 * apart (spec 044 R10.1), then the rest by day, each group under its heading,
 * in the order the API sends them. `pinWaiting` only for «Abiertas» without a
 * search; any other view is already one kind.
 */
export function inboxEntries(items: readonly Conversation[], now: Date, opts: { pinWaiting: boolean; keyPrefix?: string } = { pinWaiting: false }): InboxEntry[] {
  const out: InboxEntry[] = [];
  const prefix = opts.keyPrefix ?? "";
  const pinned = opts.pinWaiting ? items.filter(isWaitingRow) : [];
  const rest = opts.pinWaiting ? items.filter((c) => !isWaitingRow(c)) : [...items];
  push(out, "waiting", pinned, true, prefix);
  const byDay = new Map<DayGroup, Conversation[]>(DAY_GROUPS.map((g) => [g, []]));
  for (const c of rest) byDay.get(dayGroupOf(c.last_message?.at, now))!.push(c);
  for (const g of DAY_GROUPS) push(out, g, byDay.get(g)!, false, prefix);
  return out;
}

/** The search's own section: the resolved ones that match, after the open ones (R10.2). */
export function resolvedEntries(items: readonly Conversation[]): InboxEntry[] {
  const out: InboxEntry[] = [];
  push(out, "resolved", [...items], false, "r-");
  return out;
}
