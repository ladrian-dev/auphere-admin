import type { InboxAuthor, InboxDetail, InboxThreadItem } from "@/lib/backend/inbox";

/**
 * The Inbox's pure decisions (spec 030, US5–US10). No React, no requests:
 * what the composer offers, how a time reads in the list, where the day
 * separators go, whether a file may be sent. Everything here is what the
 * screen must not get wrong, so it is tested without rendering.
 */

// ── composer ──────────────────────────────────────────────────────────

export type ComposerMode =
  /** Resolved: the box says so and offers to reopen. */
  | { kind: "resolved" }
  /** The agent asked for help and nobody took it yet. */
  | { kind: "waiting"; reason: string | null }
  /** The agent answers; the person may take over. */
  | { kind: "agent" }
  /** Another person of the business answers. */
  | { kind: "other"; name: string | null }
  /** This person answers; `blocked` says why WhatsApp would refuse a send. */
  | { kind: "mine"; blocked: "window_closed" | "channel_disconnected" | null };

export function composerMode(detail: Pick<InboxDetail, "state" | "assignee" | "waiting_reason" | "window" | "channel">): ComposerMode {
  if (detail.state === "resolved") return { kind: "resolved" };
  if (detail.state === "waiting" && !detail.assignee) return { kind: "waiting", reason: detail.waiting_reason };
  if (detail.state === "agent") return { kind: "agent" };
  if (detail.assignee && !detail.assignee.is_me) return { kind: "other", name: detail.assignee.name };
  if (!detail.channel.connected) return { kind: "mine", blocked: "channel_disconnected" };
  if (!detail.window.open) return { kind: "mine", blocked: "window_closed" };
  return { kind: "mine", blocked: null };
}

/** The API's 409 codes on a send, mapped to the sentence the composer says. */
export const SEND_ERRORS = ["not_assigned_to_you", "window_closed", "channel_disconnected"] as const;
export type SendError = (typeof SEND_ERRORS)[number];
export function sendErrorOf(code: string | null | undefined): SendError | "generic" {
  return (SEND_ERRORS as readonly string[]).includes(code ?? "") ? (code as SendError) : "generic";
}

// ── attachments (R10.3) ───────────────────────────────────────────────

const MB = 1024 * 1024;
/** Same subset the API accepts: checked here first so nobody waits for an upload that will be refused. */
export const ATTACH_RULES: Record<string, { kind: "image" | "document"; maxBytes: number }> = {
  "image/jpeg": { kind: "image", maxBytes: 5 * MB },
  "image/png": { kind: "image", maxBytes: 5 * MB },
  "application/pdf": { kind: "document", maxBytes: 16 * MB },
};
export const ATTACH_ACCEPT = Object.keys(ATTACH_RULES).join(",");

export type AttachCheck = { ok: true } | { ok: false; reason: "type" } | { ok: false; reason: "size"; maxMb: number };

export function checkAttachment(file: { type: string; size: number }): AttachCheck {
  const rule = ATTACH_RULES[file.type];
  if (!rule) return { ok: false, reason: "type" };
  if (file.size > rule.maxBytes) return { ok: false, reason: "size", maxMb: rule.maxBytes / MB };
  return { ok: true };
}

// ── time ──────────────────────────────────────────────────────────────

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function dayBefore(d: Date): Date {
  const out = new Date(d);
  out.setDate(out.getDate() - 1);
  return out;
}

export type DayLabel = { kind: "today" } | { kind: "yesterday" } | { kind: "date"; text: string };

/** The day separator of the thread: «Hoy», «Ayer» or the date. */
export function dayLabel(at: string, now: Date, locale: string): DayLabel {
  const d = new Date(at);
  if (sameDay(d, now)) return { kind: "today" };
  if (sameDay(d, dayBefore(now))) return { kind: "yesterday" };
  const sameYear = d.getFullYear() === now.getFullYear();
  return {
    kind: "date",
    text: d.toLocaleDateString(locale, { day: "numeric", month: "long", ...(sameYear ? {} : { year: "numeric" }) }),
  };
}

/** The time in a row of the list: the hour today, then «Ayer», then the date. */
export function listTime(at: string, now: Date, locale: string): DayLabel | { kind: "time"; text: string } {
  const d = new Date(at);
  if (sameDay(d, now)) return { kind: "time", text: clock(at, locale) };
  return dayLabel(at, now, locale);
}

export function clock(at: string, locale: string): string {
  return new Date(at).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

/** Thread items with a separator wherever the day changes. */
export type ThreadRow = { kind: "day"; key: string; at: string } | { kind: "item"; key: string; item: InboxThreadItem };

export function withDaySeparators(items: InboxThreadItem[]): ThreadRow[] {
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

/** Same person in two readings — a list row and the thread — compares equal. */
export function isMe(author: InboxAuthor | null | undefined): boolean {
  return Boolean(author && author.kind === "member" && author.is_me);
}
