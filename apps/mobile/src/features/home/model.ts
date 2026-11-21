import { useEffect, useRef, useState } from "react";

import type { Conversation, Home, Me } from "@/api/endpoints";
import type { MessageKey, T } from "@/i18n/t";
import { creditRunway } from "@/lib/panel-model";
import type { ChannelKind } from "@/ui/brand-icons";

/**
 * Inicio's pure rules (spec 069, R8): what each tile says, which conversations
 * are «lo último», who waits first, and when the calm card may say «todo en
 * orden». Every figure and name comes from the API; nothing is written here.
 */

/** «Clínica Brisa · Ava atiende» — the agents from `/me`, never a fixed name (R21.2). */
export function bizLine(business: string, agents: readonly { name: string }[] | undefined, t: T): string {
  const list = agents ?? [];
  if (list.length === 1 && list[0]) return t("v13.home.biz.agent", { business, agent: list[0].name });
  if (list.length > 1) return t("v13.home.biz.agents", { business, n: list.length });
  return business;
}

/**
 * How long the balance lasts at the 7-day pace (R8.1, R18.1), from the API's
 * `days_left`: whole days below two months, whole months from there on.
 */
export type Lasting = { kind: "months" | "days"; n: number } | { kind: "day" } | { kind: "lessThanDay" };

export function lasting(daysLeft: number): Lasting {
  if (daysLeft < 1) return { kind: "lessThanDay" };
  const days = Math.floor(daysLeft);
  if (days === 1) return { kind: "day" };
  if (days >= 60) return { kind: "months", n: Math.floor(days / 30) };
  return { kind: "days", n: days };
}

/** The keys of each way of saying it, so Inicio and Consumo each pick their own sentence. */
export function lastingText(l: Lasting, keys: Record<Lasting["kind"], MessageKey>, t: T, n: (v: number) => string): string {
  return l.kind === "months" || l.kind === "days" ? t(keys[l.kind], { n: n(l.n) }) : t(keys[l.kind]);
}

/** A conversation waiting for a person, as the Bandeja pins it (spec 044, R10.1). */
export function isWaiting(c: Pick<Conversation, "state" | "assignee">): boolean {
  return c.state === "waiting" && !c.assignee;
}

/** «Lo último en la Bandeja» (R8.3): the open ones nobody waits on, 2 when someone waits and 4 when not. */
export function latestOf(items: readonly Conversation[], someoneWaits: boolean): Conversation[] {
  return items.filter((c) => c.state !== "resolved" && !isWaiting(c)).slice(0, someoneWaits ? 2 : 4);
}

/** Who waits first: the API's own first one (`home.waiting.first_conversation_id`), else the list's first. */
export function firstWaiting(items: readonly Conversation[], firstId: string | null | undefined): Conversation | null {
  const waiting = items.filter(isWaiting);
  return waiting.find((c) => c.id === firstId) ?? waiting[0] ?? null;
}

/** The channel badge, only for the marks the app draws (R1.3); any other kind has none. */
export function channelOf(c: Pick<Conversation, "channel">): ChannelKind | null {
  const kind = c.channel?.kind;
  return kind === "whatsapp" || kind === "instagram" || kind === "messenger" ? kind : null;
}

/** «Ava: …», «Tú: …» or the contact's own words — the agent's name from the data (R21.2). */
export function previewLine(c: Pick<Conversation, "last_message" | "handled_by_agent" | "agent">, agents: readonly { name: string }[] | undefined, t: T): string {
  const m = c.last_message;
  if (!m) return "";
  const text = m.preview || (m.has_media ? t("inbox.row.media") : "");
  if (m.author.kind === "member" && m.author.is_me) return t("inbox.row.you", { text });
  if (m.author.kind === "agent") {
    const agent = c.handled_by_agent?.name ?? c.agent?.name ?? (agents?.length === 1 ? agents[0]?.name : null) ?? t("inbox.who.agent");
    return t("v13.home.preview.agent", { agent, text });
  }
  if (m.author.kind === "member" && m.author.name) return t("v13.home.preview.person", { name: m.author.name, text });
  return text;
}

/** «Atender a Lucía»: the first word of a name; a contact known only by a number keeps it whole. */
export function callName(name: string): string {
  const first = name.trim().split(/\s+/)[0] ?? "";
  return /\p{L}/u.test(first) ? first : name.trim();
}

/** A balance item in «attention» (`balance_low`, `balance_out`): the calm card never says «todo en orden» over it. */
export function balanceAttention(home: Pick<Home, "attention">): "balance_low" | "balance_out" | null {
  const item = home.attention.find((a) => a.kind !== "waiting");
  return item ? (item.kind as "balance_low" | "balance_out") : null;
}

/**
 * Whether the calm card may add «y el saldo alcanza para el mes» (R21): an
 * assigned balance, something left, and the 7-day pace reaching the month's
 * end (no spend at all reaches it too).
 */
export function balanceLastsMonth(balance: Home["balance"], now: Date): boolean {
  if (!balance?.assigned || (balance.remaining_cents ?? 0) <= 0) return false;
  const runway = creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now);
  return runway === null || runway.days >= runway.monthLeft;
}

/** Micro 8 stays on screen this long, with or without «Reducir movimiento» (R2.5: a wait, not an animation). */
export const CALM_MS = 3200;

/**
 * The calm card (R8.5): once, when Inicio sees nobody waiting after it saw
 * someone waiting — also when the last one was attended while Inicio was in
 * the background (it compares on focus). A cold start with nobody waiting
 * shows nothing, an unknown count is not a zero, and a balance in trouble
 * blocks it. It leaves on its own after `CALM_MS`, or at once if someone waits again.
 */
export function useCalmOnce(waiting: number | null, focused: boolean, blocked: boolean): boolean {
  const seen = useRef(0);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!focused || waiting === null) return;
    if (seen.current > 0 && waiting === 0 && !blocked) setOn(true);
    seen.current = waiting;
  }, [waiting, focused, blocked]);
  useEffect(() => {
    if (!on) return;
    const id = setTimeout(() => setOn(false), CALM_MS);
    return () => clearTimeout(id);
  }, [on]);
  return on && waiting === 0 && !blocked;
}

/** `/me` as Inicio reads it: `agents` and `channels` guarded, an older `/me` may not carry them. */
export type HomeMe = Pick<Me, "client" | "nav" | "balance_contact"> & { agents?: Me["agents"] };
