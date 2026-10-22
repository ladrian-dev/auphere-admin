import { describe, expect, it } from "vitest";

import { messages, t, type MessageKey } from "@/i18n/messages";
import type { BookingAction, BookingEvent, BookingEventKind, BookingStatus } from "@/lib/backend/reservas";

import { eventLine, originLine } from "../events";
import { keyFor } from "../idempotency";
import { formatPrice, parsePrice, priceInput } from "../money";
import {
  CAPACITY_KINDS,
  actionButtons,
  channelKey,
  failureMessage,
  firstName,
  initialsOf,
  stayKey,
  stayOptions,
  stayTitleKey,
  statusKey,
  statusTone,
  unitKey,
} from "../vocab";
import { canOffer, countdown, isListed, minutesLeft, offerState } from "../waitlist";
import { offer, waitlistEntry } from "./fixtures";

const has = (key: string) => key in messages;

/** Spec 043: the agreed vocabulary — every built key exists, in both languages. */
describe("the words of Reservas", () => {
  it("every status has its word in each mode; done and noshow differ by mode", () => {
    const statuses: BookingStatus[] = ["pending", "confirmed", "arrived", "done", "noshow", "cancelled"];
    for (const mode of ["services", "capacity"] as const) for (const s of statuses) expect(has(statusKey(mode, s)), `${mode}.${s}`).toBe(true);
    expect(t("es", statusKey("services", "pending"))).toBe("Sin confirmar");
    expect(t("es", statusKey("services", "done"))).toBe("Atendida");
    expect(t("es", statusKey("capacity", "done"))).toBe("Vino");
    expect(t("es", statusKey("services", "noshow"))).toBe("No asistió");
    expect(t("es", statusKey("capacity", "noshow"))).toBe("No vino");
    expect(t("es", statusKey("capacity", "arrived"))).toBe("Llegó");
    expect(statusTone("pending")).toBe("info");
    expect(statusTone("noshow")).toBe("danger");
  });

  it("each kind of Aforo business brings its words", () => {
    for (const k of CAPACITY_KINDS) {
      expect(has(unitKey(k)) && has(stayKey(k)) && has(stayTitleKey(k)), k).toBe(true);
    }
    expect(t("es", unitKey("restaurant"))).toBe("comensales");
    expect(t("es", stayKey("restaurant"))).toBe("tiempo máximo de mesa");
    expect(t("es", stayKey("classes"))).toBe("duración de la sesión");
    expect(t("es", unitKey("spa"))).toBe("plazas");
    expect(stayOptions("restaurant", 90)).toEqual([60, 90, 120, 150]);
    expect(stayOptions("restaurant", 105)).toEqual([60, 90, 105, 120, 150]);
  });

  it("only WhatsApp, phone and in person exist as channels", () => {
    expect(t("es", channelKey("whatsapp"))).toBe("WhatsApp");
    expect(t("es", channelKey("phone"))).toBe("Teléfono");
    expect(t("es", channelKey("in_person"))).toBe("En el local");
    const all = Object.entries(messages).filter(([k]) => k.startsWith("reservas."));
    const forbidden = all.filter(([, v]) => /instagram|messenger|reserve with google/i.test(`${v.es} ${v.en}`));
    expect(forbidden.map(([k]) => k)).toEqual([]);
  });

  it("buttons come only from `allowed`, in a fixed order, with each mode's words", () => {
    const allowed: BookingAction[] = ["cancel", "move", "confirm", "request_confirmation"];
    const b = actionButtons(allowed, "services");
    expect(b.map((x) => x.action)).toEqual(["confirm", "request_confirmation", "move", "cancel"]);
    expect(b.map((x) => t("es", x.labelKey))).toEqual(["Marcar confirmada", "Pedir confirmación", "Mover", "Cancelar"]);
    expect(b.find((x) => x.action === "cancel")?.destructive).toBe(true);
    const aforo = actionButtons(["arrive", "noshow", "undo", "move", "cancel"], "capacity", ["arrive", "noshow", "undo", "request_confirmation"]);
    expect(aforo.map((x) => t("es", x.labelKey))).toEqual(["Llegó", "No vino", "Deshacer"]);
    expect(actionButtons(["noshow", "move"], "services").map((x) => t("es", x.labelKey))).toEqual(["No asistió", "Mover"]);
    expect(actionButtons(["move"], "capacity").map((x) => t("es", x.labelKey))).toEqual(["Cambiar"]);
    expect(actionButtons([], "services")).toEqual([]);
  });

  it("a refusal says what happened, never the API's text", () => {
    expect(failureMessage({ status: 412, code: "stale" }).key).toBe("reservas.error.stale");
    expect(failureMessage({ status: 409, code: "slot_taken", info: { first_fit: { date: "2026-10-23", time: "21:30" } } })).toEqual({
      key: "reservas.error.slotTaken.fit",
      vars: { time: "21:30" },
    });
    expect(failureMessage({ status: 409, code: "slot_taken", info: { first_fit: null } }).key).toBe("reservas.error.slotTaken");
    expect(failureMessage({ status: 409, code: "live_reservations", info: { count: 3 } })).toEqual({
      key: "reservas.error.liveReservations",
      vars: { count: 3 },
    });
    expect(failureMessage({ status: 403 }).key).toBe("common.forbidden");
    expect(failureMessage({ status: 500 }).key).toBe("common.error.backend");
    for (const code of ["invalid_transition", "hours_missing", "wrong_mode"]) {
      expect(has(failureMessage({ status: 409, code }).key)).toBe(true);
    }
  });

  it("initials and first names for avatars and sentences", () => {
    expect(initialsOf("Ana Pérez Soto")).toBe("AS");
    expect(initialsOf("Lucía")).toBe("L");
    expect(initialsOf(null)).toBe("·");
    expect(firstName("Ana Pérez")).toBe("Ana");
  });
});

describe("a booking's history, in words", () => {
  const ctx = {
    mode: "services" as const,
    contact: "Ana",
    agent: "el agente",
    system: "Auphere",
    when: (x: { date?: unknown; start?: unknown }) => `${String(x.date)} ${String(x.start)}`,
    why: (w: string) => w,
    channel: (c: string) => (c === "phone" ? "Teléfono" : "WhatsApp"),
  };
  const ev = (kind: BookingEventKind, o: Partial<BookingEvent> = {}): BookingEvent => ({
    kind,
    at: "2026-10-22T11:00:00Z",
    actor: { kind: "person", name: "Valeria Ríos" },
    data: {},
    ...o,
  });

  it("every kind of the contract has a sentence, and the sentence exists", () => {
    const kinds: BookingEventKind[] = [
      "created",
      "confirmed",
      "confirmation_requested",
      "reminder_sent",
      "replied_yes",
      "replied_no",
      "moved",
      "cancelled",
      "arrived",
      "noshow",
      "undone",
      "done",
      "waitlist_joined",
      "waitlist_accepted",
      "notified",
      "notify_failed",
      "released",
    ];
    for (const kind of kinds) {
      for (const mode of ["services", "capacity"] as const) {
        const line = eventLine(ev(kind), { ...ctx, mode });
        expect(has(line.key), `${kind} → ${line.key}`).toBe(true);
        expect(line.key).not.toBe("reservas.event.unknown");
      }
    }
    expect(eventLine(ev("mystery" as BookingEventKind), ctx).key).toBe("reservas.event.unknown");
  });

  it("moved says who, from, to, and whether WhatsApp went out", () => {
    const line = eventLine(
      ev("moved", { data: { from: { date: "2026-10-22", start: "16:00" }, to: { date: "2026-10-22", start: "16:30" }, notified: true } }),
      ctx,
    );
    expect(t("es", line.key as MessageKey, line.vars)).toBe(
      "Movida por Valeria Ríos: de 2026-10-22 16:00 a 2026-10-22 16:30. Se le avisó por WhatsApp.",
    );
    const failed = eventLine(ev("notify_failed", { data: { why: "no_template" } }), ctx);
    expect(t("es", failed.key as MessageKey, failed.vars)).toContain("No se pudo avisar por WhatsApp");
  });

  it("the origin: the agent by WhatsApp, a person by phone, the waitlist, a walk-in", () => {
    const o = { agent: "el agente", when: "ayer 22:14", channel: ctx.channel };
    const agent = originLine({ origin: "agent", channel: "whatsapp", created_by: { kind: "agent", name: null } }, o);
    expect(t("es", agent.key, agent.vars)).toBe("La reservó el agente · por WhatsApp · ayer 22:14");
    const person = originLine({ origin: "person", channel: "phone", created_by: { kind: "person", name: "Valeria" } }, o);
    expect(t("es", person.key, person.vars)).toBe("La creó Valeria · Teléfono · ayer 22:14");
    expect(has(originLine({ origin: "waitlist", channel: "whatsapp", created_by: { kind: "system", name: null } }, o).key)).toBe(true);
    expect(has(originLine({ origin: "walkin", channel: "in_person", created_by: { kind: "person", name: null } }, o).key)).toBe(true);
  });
});

describe("prices, keys and offers", () => {
  it("CLP has no decimals; an empty price is «no cost», not zero", () => {
    expect(formatPrice({ amount_minor: 15000, currency: "CLP" }, "es")).toMatch(/15\.000/);
    expect(formatPrice(null, "es")).toBeNull();
    expect(parsePrice("15.000", "CLP")).toEqual({ kind: "ok", minor: 15000 });
    expect(parsePrice("15000", "CLP")).toEqual({ kind: "ok", minor: 15000 });
    expect(parsePrice("", "CLP")).toEqual({ kind: "empty" });
    expect(parsePrice("15,5", "CLP")).toEqual({ kind: "invalid" });
    expect(parsePrice("12,50", "EUR")).toEqual({ kind: "ok", minor: 1250 });
    expect(priceInput(15000, "CLP")).toBe("15000");
    expect(priceInput(null, "CLP")).toBe("");
  });

  it("the same submit keeps its Idempotency-Key, a different one gets a new key", () => {
    let n = 0;
    const fresh = () => `k${++n}`;
    const first = keyFor(null, "a", fresh);
    expect(keyFor(first, "a", fresh)).toBe(first);
    expect(keyFor(first, "b", fresh).key).toBe("k2");
  });

  it("an offer says who has the turn and how long is left", () => {
    const now = new Date("2026-10-22T19:40:00Z");
    const running = offerState(offer());
    expect(running).toMatchObject({ kind: "running", index: 2, total: 3 });
    expect(running.kind === "running" && running.current?.name).toBe("Pedro Soto");
    expect(countdown("2026-10-22T19:44:59Z", now)).toBe("4:59");
    expect(countdown("2026-10-22T19:39:00Z", now)).toBeNull();
    expect(minutesLeft("2026-10-22T19:52:30Z", now)).toBe(13);
    expect(offerState(offer({ status: "closed", filled_booking_id: "x" })).kind).toBe("filled");
    const stopped = offer({ status: "closed" });
    stopped.candidates[1]!.status = "stopped";
    expect(offerState(stopped).kind).toBe("stopped");
    const nobody = offer({ status: "closed" });
    nobody.candidates.forEach((c) => (c.status = "noreply"));
    expect(offerState(nobody).kind).toBe("nobody");
  });

  it("«Ofrecer» only to who waits, fits and has no open offer", () => {
    expect(canOffer(waitlistEntry())).toBe(true);
    expect(canOffer(waitlistEntry({ fits_now: false }))).toBe(false);
    expect(canOffer(waitlistEntry({ offer: { id: "o", deadline_at: "2026-10-22T20:00:00Z" } }))).toBe(false);
    expect(isListed({ status: "removed" })).toBe(false);
    expect(isListed({ status: "waiting" })).toBe(true);
  });
});
