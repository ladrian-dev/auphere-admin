import type { Author, Conversation, Detail, ThreadItem } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";

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
  | { kind: "waiting"; reason: string | null; since?: string | null; agent?: string | null }
  | { kind: "agent"; agent?: string | null }
  | { kind: "other"; name: string | null }
  | { kind: "mine"; blocked: "window_closed" | "channel_disconnected" | null; agent?: string | null };

export function composerMode(
  d: Pick<Detail, "state" | "assignee" | "waiting_reason" | "window" | "channel"> & Partial<Pick<Detail, "agent" | "waiting_since" | "activity">>,
): ComposerMode {
  const agent = d.agent?.name ?? null;
  if (d.state === "resolved") return { kind: "resolved" };
  if (d.state === "waiting" && !d.assignee) return { kind: "waiting", reason: d.waiting_reason ?? null, since: d.waiting_since ?? lastEscalatedAt(d.activity ?? []), agent };
  if (d.state === "agent") return { kind: "agent", agent };
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
  return t("inbox.who.agent");
}

/** What happened, as one sentence; «Tú» gets its own verbs («Tomaste el control»). */
export function eventText(kind: string | null | undefined, a: Author | null | undefined, detail: string | null | undefined, t: T): string {
  const me = isMe(a);
  const who = whoOf(a, t);
  switch (kind) {
    case "escalated":
      return detail ? t("inbox.event.escalated.reason", { reason: detail }) : t("inbox.event.escalated");
    case "takeover":
      return me ? t("inbox.event.takeover.you") : t("inbox.event.takeover", { who });
    case "released":
      return me ? t("inbox.event.released.you") : t("inbox.event.released", { who });
    case "resolved":
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
export function attendsLine(d: Pick<Detail, "state" | "assignee" | "agent">, t: T): string {
  if (d.state === "resolved") return t("app.inbox.attends.resolved");
  if (d.assignee) {
    return d.assignee.is_me ? t("inbox.assigned.you") : t("inbox.assigned", { name: d.assignee.name ?? t("inbox.who.someone") });
  }
  if (d.state === "waiting") return t("app.inbox.attends.waiting");
  return d.agent ? t("app.inbox.attends.agent", { agent: d.agent.name }) : t("app.inbox.attends.agent.noName");
}

/** A list row's preview: who wrote it, and the text or «Archivo». */
export function previewOf(c: Pick<Conversation, "last_message">, t: T): string {
  const m = c.last_message;
  if (!m) return "";
  const text = m.preview || (m.has_media ? t("inbox.row.media") : "");
  if (isMe(m.author)) return t("inbox.row.you", { text });
  if (m.author.kind === "agent") return t("inbox.row.agent", { text });
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
