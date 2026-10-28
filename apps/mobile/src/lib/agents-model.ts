import type { AgentCard, AgentChannel, VisibleState } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import type { Locale, MessageKey, T } from "@/i18n/t";

/**
 * Spec 047 (T169; requirements 25, 27, 50.1, 50.2): an agent and its numbers
 * as the business sees them on the phone. The state comes from the API
 * (`visible_state`, the one calculation of `events.md` §1.3) and is only put
 * into words here, with the console's own words and tones (25.5): the app
 * never works a state out.
 */
export type Tone = "danger" | "warning" | "positive" | "info" | "neutral";

/** The console's tones (`events.md` §1.2–1.3) as the app's badge tones. Unknown: neutral, never a colour that lies. */
export function toneOf(tone: string): Tone {
  switch (tone) {
    case "positive":
      return "positive";
    case "info":
      return "info";
    case "warn":
    case "warning":
      return "warning";
    case "danger":
      return "danger";
    default:
      return "neutral";
  }
}

const AGENT_STATES = ["serving", "testing", "ready_no_channel", "draft", "archived"] as const;
const PAUSE_REASONS = ["manual", "no_balance", "agent_cap", "client_paused", "client_archived"] as const;

/** «Atendiendo», «Pausado · sin saldo»… A code this version does not know says nothing (`null`). */
export function agentStateLabel(v: VisibleState, t: T): string | null {
  if (v.code === "paused") {
    const reason = (PAUSE_REASONS as readonly string[]).includes(v.reason ?? "") ? v.reason! : "manual";
    return t("clients.v2.agent.paused", { reason: t(`clients.v2.pause.${reason}` as MessageKey) });
  }
  return (AGENT_STATES as readonly string[]).includes(v.code) ? t(`clients.v2.agent.${v.code}` as MessageKey) : null;
}

/** The sentence under the state: what it means for the people who write. */
export function agentStateSentence(v: VisibleState, t: T): string | null {
  if (v.code === "paused") return t("builder.life.paused");
  return (AGENT_STATES as readonly string[]).includes(v.code) ? t(`agentes.state.${v.code}` as MessageKey) : null;
}

const CHANNEL_STATES = ["pending_link", "disconnected", "paused", "unconfigured", "team_only", "everyone"] as const;
const PROBLEMS = ["quality", "auth_expired", "coexistence_inactive", "meta_error"] as const;

/** «A todos», «En pausa», «Con problemas · calidad baja»… (`events.md` §1.2). */
export function channelStateLabel(v: VisibleState, t: T): string | null {
  if (v.code === "problem") {
    const reason = (PROBLEMS as readonly string[]).includes(v.reason ?? "") ? v.reason! : "unknown";
    return t("builder.channel.state.problem", { reason: t(`builder.channel.problem.${reason}` as MessageKey) });
  }
  return (CHANNEL_STATES as readonly string[]).includes(v.code) ? t(`builder.channel.state.${v.code}` as MessageKey) : null;
}

/** «WhatsApp · +34 600 111 222»: the kind of number and the business's own number. */
export function channelName(c: Pick<AgentChannel, "type" | "identifier">): string {
  const kind = c.type === "whatsapp" ? "WhatsApp" : c.type.charAt(0).toUpperCase() + c.type.slice(1);
  return c.identifier ? `${kind} · ${c.identifier}` : kind;
}

/**
 * Who paused it and from where (27.6): the person's name (`paused_by_name`),
 * the kind of person and the origin. A pause of the system has no name (it
 * says why, below); a pause without a name says what it knows and never
 * invents one.
 */
export function pausedBy(
  card: Pick<AgentCard, "paused_by_kind" | "paused_origin"> & { paused_by_name?: string | null },
  partner: string,
  t: T,
): string | null {
  const name = card.paused_by_name?.trim() || null;
  switch (card.paused_by_kind) {
    case "client_user":
      if (card.paused_origin === "app") return name ? t("agentes.by.named.app", { name }) : t("agentes.by.client_user.app");
      if (card.paused_origin === "lite_web") return name ? t("agentes.by.named.lite_web", { name }) : t("agentes.by.client_user.lite_web");
      return name ? t("agentes.by.named", { name }) : t("agentes.by.client_user");
    case "partner_member":
      return name ? t("agentes.by.named.partner", { name, partner }) : t("agentes.by.partner_member", { partner });
    case "operator":
      return t("agentes.by.operator");
    default:
      return null;
  }
}

/** Since when it is paused (`paused_at`): minutes or hours under a day, then the date and time. */
export function pausedSince(at: string | null | undefined, now: Date, locale: Locale, t: T): string | null {
  if (!at) return null;
  const then = new Date(at);
  if (Number.isNaN(then.getTime())) return null;
  const mins = Math.max(1, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (mins < 60) return t("agentes.since.min", { n: mins });
  if (mins < 24 * 60) return t("agentes.since.h", { n: Math.round(mins / 60) });
  return t("agentes.since.date", { date: then.toLocaleString(locale, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) });
}

/**
 * Why there is no «Reanudar» (27.4): a pause the system put (no balance, the
 * agent's cap) is lifted by the system, and the client's own pause or archive
 * by the partner. Said in words, with whom to talk to, never a dead button.
 */
export function whyNoResume(reason: string | null | undefined, partner: string, t: T): string {
  switch (reason) {
    case "no_balance":
    case "agent_cap":
    case "client_paused":
    case "client_archived":
      return t(`agentes.why.${reason}` as MessageKey, { partner });
    default:
      return t("agentes.why.other", { partner });
  }
}

/** What the screen offers for an agent: only what the API allows (`allowed`), and a reason when paused without «Reanudar». */
export function agentActions(card: Pick<AgentCard, "allowed" | "visible_state" | "pause_reason">): {
  pause: boolean;
  resume: boolean;
  blocked: string | null;
} {
  const pause = card.allowed.includes("pause");
  const resume = card.allowed.includes("resume");
  const paused = card.visible_state.code === "paused";
  return { pause, resume, blocked: paused && !resume ? (card.pause_reason ?? card.visible_state.reason ?? null) : null };
}

/** A refusal of pause or resume, in words. `confirm_required` is not here: it is a question, not an error. */
export function agentErrorText(e: unknown, partner: string, t: T): string {
  if (e instanceof ApiError) {
    if (e.offline) return t("agentes.offline");
    if (e.code === "system_pause") return whyNoResume(typeof e.info.pause_reason === "string" ? e.info.pause_reason : null, partner, t);
    if (e.code === "channel_disconnected") return t("agentes.error.channel_disconnected", { partner });
    if (e.code === "not_allowed") return t("agentes.error.not_allowed");
    if (e.code === "client_archived") return t("agentes.why.client_archived", { partner });
  }
  return t("agentes.error.generic");
}

/** `409 confirm_required`: how many conversations are in progress, to say before pausing (27.8). */
export function confirmRequired(e: unknown): number | null {
  if (!(e instanceof ApiError) || e.status !== 409 || e.code !== "confirm_required") return null;
  const n = e.info.open_conversations;
  return typeof n === "number" ? n : 0;
}

/** The list with one card replaced by what the API answered. */
export function withCard(list: { items: AgentCard[] } | undefined, card: AgentCard): { items: AgentCard[] } | undefined {
  if (!list) return list;
  return { items: list.items.map((a) => (a.id === card.id ? card : a)) };
}

/** The list with one number replaced by what the API answered, under whichever agent has it. */
export function withChannel(list: { items: AgentCard[] } | undefined, channel: AgentChannel): { items: AgentCard[] } | undefined {
  if (!list) return list;
  return { items: list.items.map((a) => ({ ...a, channels: a.channels.map((c) => (c.id === channel.id ? channel : c)) })) };
}

/** Whom to talk to: the partner's name from `/me.balance_contact`, or Auphere. */
export function partnerOf(contact: { kind: string; name: string } | null | undefined): string {
  if (!contact) return "Auphere";
  return contact.kind === "auphere" ? "Auphere" : contact.name;
}
