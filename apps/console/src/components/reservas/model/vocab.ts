import type { MessageKey } from "@/i18n/messages";
import type {
  BookingAction,
  BookingChannel,
  BookingStatus,
  CapacityKind,
  ReservasMode,
  ReservasSettings,
} from "@/lib/backend/reservas";

/**
 * The words of Reservas (spec 043): the agreed status vocabulary, what each
 * Aforo business calls its people and its stay, which buttons a booking gets
 * (only from `allowed` — the screen never recomputes the rules) and what to
 * say when the API says no.
 */

export const CAPACITY_KINDS: readonly CapacityKind[] = ["restaurant", "bar", "classes", "tours", "rooms", "spa"];

export function kindOf(settings: Pick<ReservasSettings, "capacity_kind">): CapacityKind {
  return settings.capacity_kind ?? "restaurant";
}

/** «comensales», «personas», «plazas». */
export function unitKey(kind: CapacityKind): MessageKey {
  return `reservas.kind.${kind}.unit` as MessageKey;
}

/** «tiempo máximo de mesa», «duración de la sesión»… (lower case, inside a sentence). */
export function stayKey(kind: CapacityKind): MessageKey {
  return `reservas.kind.${kind}.stay` as MessageKey;
}

/** The same, as a field's label. */
export function stayTitleKey(kind: CapacityKind): MessageKey {
  return `reservas.kind.${kind}.stayTitle` as MessageKey;
}

/** «Tiempo máximo» options per kind (minutes, 30–480 in steps of 15). */
export const STAY_OPTIONS: Record<CapacityKind, readonly number[]> = {
  restaurant: [60, 90, 120, 150],
  bar: [60, 90, 120, 180],
  classes: [45, 60, 90],
  tours: [60, 120, 180, 240],
  rooms: [60, 120, 180, 240],
  spa: [60, 90, 120],
};

export function stayOptions(kind: CapacityKind, current: number): number[] {
  const base = STAY_OPTIONS[kind];
  return base.includes(current) ? [...base] : [...base, current].sort((a, b) => a - b);
}

/** Pending «Sin confirmar» … done «Atendida» (Servicios) / «Vino» (Aforo) … */
export function statusKey(mode: ReservasMode, status: BookingStatus): MessageKey {
  return `reservas.status.${mode}.${status}` as MessageKey;
}

export type Tone = "positive" | "warning" | "danger" | "info" | "muted";

/** One tone per meaning (Bloque C): info = not yet, positive = on, danger = did not happen. */
export function statusTone(status: BookingStatus): Tone {
  switch (status) {
    case "pending":
      return "info";
    case "confirmed":
    case "arrived":
      return "positive";
    case "noshow":
      return "danger";
    default:
      return "muted";
  }
}

export function channelKey(channel: BookingChannel): MessageKey {
  return `reservas.channel.${channel}` as MessageKey;
}

/** The order buttons are painted in, whatever order `allowed` comes in. */
export const ACTION_ORDER: readonly BookingAction[] = ["arrive", "confirm", "noshow", "request_confirmation", "undo", "move", "cancel"];

export type ActionButton = { action: BookingAction; labelKey: MessageKey; destructive: boolean };

/**
 * The buttons of a booking, **only** from `allowed`: what the API accepts
 * right now. `only` narrows them (the inline actions of the Aforo list).
 */
export function actionButtons(allowed: readonly BookingAction[], mode: ReservasMode, only?: readonly BookingAction[]): ActionButton[] {
  return ACTION_ORDER.filter((a) => allowed.includes(a) && (!only || only.includes(a))).map((action) => ({
    action,
    labelKey: (action === "noshow" || action === "move"
      ? `reservas.action.${action}.${mode}`
      : `reservas.action.${action}`) as MessageKey,
    destructive: action === "cancel",
  }));
}

export type Failure = { status: number; code?: string | null; info?: Record<string, unknown> };

/** What to tell the person when a Reservas write is refused. Never the API's raw text. */
export function failureMessage(res: Failure): { key: MessageKey; vars?: Record<string, string | number> } {
  if (res.status === 401 || res.status === 403) return { key: "common.forbidden" };
  if (res.status === 412) return { key: "reservas.error.stale" };
  if (res.status === 409) {
    switch (res.code) {
      case "slot_taken": {
        const fit = res.info?.first_fit as { time?: string } | string | null | undefined;
        const time = typeof fit === "string" ? fit : fit?.time;
        return time ? { key: "reservas.error.slotTaken.fit", vars: { time } } : { key: "reservas.error.slotTaken" };
      }
      case "invalid_transition":
        return { key: "reservas.error.invalidTransition" };
      case "live_reservations":
        return { key: "reservas.error.liveReservations", vars: { count: Number(res.info?.count ?? 0) } };
      case "hours_missing":
        return { key: "reservas.error.hoursMissing" };
      case "wrong_mode":
        return { key: "reservas.error.wrongMode" };
    }
  }
  if (res.status === 422) return { key: "reservas.error.invalid" };
  return { key: "common.error.backend" };
}

/** «Ana Pérez» → «AP». */
export function initialsOf(name: string | null | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "·";
  return ((words[0]![0] ?? "") + (words.length > 1 ? (words[words.length - 1]![0] ?? "") : "")).toLocaleUpperCase();
}

/** «Ana» from «Ana Pérez», for «Avisar a Ana por WhatsApp». */
export function firstName(name: string | null | undefined): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}
