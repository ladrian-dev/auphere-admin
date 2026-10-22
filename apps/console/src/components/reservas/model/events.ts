import type { MessageKey } from "@/i18n/messages";
import type { Booking, BookingEvent, ReservasMode } from "@/lib/backend/reservas";

/**
 * A booking's history in words (spec 043, Requisito 5.5). The API sends a
 * closed vocabulary — `kind`, `actor`, `data` — and never a sentence; the
 * screen writes it here, in the person's language. An unknown kind says «a
 * change» instead of leaking its code.
 */

export type Line = { key: MessageKey; vars: Record<string, string | number> };

type Ctx = {
  mode: ReservasMode;
  /** The client's name, for «Ana confirmó la asistencia». */
  contact: string;
  /** «el agente», «Auphere» — the words for nameless actors. */
  agent: string;
  system: string;
  /** A local day and hour as the screen says it: «jue 8 a las 12:00». */
  when: (at: { date?: unknown; start?: unknown; time?: unknown }) => string;
  /** `notify_failed.data.why` in words. */
  why: (why: string) => string;
  channel: (channel: string) => string;
};

function who(ev: BookingEvent, ctx: Ctx): string {
  if (ev.actor.kind === "agent") return ev.actor.name || ctx.agent;
  if (ev.actor.kind === "system") return ctx.system;
  return ev.actor.name || ctx.system;
}

export function eventLine(ev: BookingEvent, ctx: Ctx): Line {
  const name = who(ev, ctx);
  const d = ev.data ?? {};
  switch (ev.kind) {
    case "created":
      if (ev.actor.kind === "agent") return { key: "reservas.event.created.agent", vars: { name } };
      if (ev.actor.kind === "system") return { key: "reservas.event.created.system", vars: {} };
      return {
        key: "reservas.event.created.person",
        vars: { name, channel: typeof d.channel === "string" ? ctx.channel(d.channel) : ctx.channel("phone") },
      };
    case "confirmed":
      return ev.actor.kind === "person"
        ? { key: "reservas.event.confirmed.person", vars: { name } }
        : { key: "reservas.event.confirmed.contact", vars: { name: ctx.contact } };
    case "confirmation_requested":
      return { key: "reservas.event.confirmationRequested", vars: {} };
    case "reminder_sent":
      return { key: "reservas.event.reminderSent", vars: {} };
    case "replied_yes":
      return { key: "reservas.event.repliedYes", vars: { name: ctx.contact } };
    case "replied_no":
      return { key: "reservas.event.repliedNo", vars: { name: ctx.contact } };
    case "moved": {
      const from = (d.from ?? {}) as Record<string, unknown>;
      const to = (d.to ?? {}) as Record<string, unknown>;
      const key = d.notified === true ? "reservas.event.moved.notified" : "reservas.event.moved";
      return { key, vars: { name, from: ctx.when(from), to: ctx.when(to) } };
    }
    case "cancelled":
      if (d.cause === "release_unconfirmed") return { key: "reservas.event.cancelled.released", vars: {} };
      if (d.cause === "mode_change") return { key: "reservas.event.cancelled.modeChange", vars: {} };
      if (d.by === "customer") return { key: "reservas.event.cancelled.customer", vars: { name: ctx.contact } };
      return ev.actor.kind === "system"
        ? { key: "reservas.event.cancelled.system", vars: {} }
        : { key: "reservas.event.cancelled.by", vars: { name } };
    case "arrived":
      return { key: "reservas.event.arrived", vars: {} };
    case "noshow":
      return { key: `reservas.event.noshow.${ctx.mode}` as MessageKey, vars: { name } };
    case "undone":
      return { key: "reservas.event.undone", vars: { name } };
    case "done":
      return { key: `reservas.event.done.${ctx.mode}` as MessageKey, vars: {} };
    case "waitlist_joined":
      return { key: "reservas.event.waitlistJoined", vars: {} };
    case "waitlist_accepted": {
      const from = d.from as Record<string, unknown> | undefined;
      const to = d.to as Record<string, unknown> | undefined;
      return from && to
        ? { key: "reservas.event.waitlistAccepted.moved", vars: { from: ctx.when(from), to: ctx.when(to) } }
        : { key: "reservas.event.waitlistAccepted", vars: {} };
    }
    case "notified":
      return { key: "reservas.event.notified", vars: {} };
    case "notify_failed":
      return { key: "reservas.event.notifyFailed", vars: { why: ctx.why(typeof d.why === "string" ? d.why : "send_failed") } };
    case "released":
      return { key: "reservas.event.released", vars: {} };
    default:
      return { key: "reservas.event.unknown", vars: {} };
  }
}

export type OriginLine = { key: MessageKey; vars: Record<string, string | number> };

/**
 * Where a booking came from: «La reservó el agente · por WhatsApp · ayer
 * 22:14», «La creó Valeria · Teléfono», «Llegó desde la lista de espera»,
 * «Llegó sin reserva». Only the four origins that exist (spec §Clarifications).
 */
export function originLine(
  b: Pick<Booking, "origin" | "channel" | "created_by">,
  ctx: { agent: string; when: string; channel: (c: string) => string },
): OriginLine {
  switch (b.origin) {
    case "agent":
      return {
        key: "reservas.origin.agent",
        vars: { name: b.created_by.name || ctx.agent, channel: ctx.channel(b.channel), when: ctx.when },
      };
    case "waitlist":
      return { key: "reservas.origin.waitlist", vars: { when: ctx.when } };
    case "walkin":
      return { key: "reservas.origin.walkin", vars: { when: ctx.when } };
    default:
      return b.created_by.name
        ? { key: "reservas.origin.person", vars: { name: b.created_by.name, channel: ctx.channel(b.channel), when: ctx.when } }
        : { key: "reservas.origin.personNameless", vars: { channel: ctx.channel(b.channel), when: ctx.when } };
  }
}
