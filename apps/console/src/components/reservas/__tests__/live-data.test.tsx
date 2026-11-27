/**
 * Spec 082 (Historia 1): la agenda y la ficha leen de una sola fuente (React
 * Query), que se relee tras cada escritura y con cada aviso
 * `reservations.changed` de la línea en vivo.
 *
 * - 1.1: tras una escritura, la agenda relee por `reservasScreenAction` y pinta
 *   lo que trae.
 * - 1.7: un aviso relee la agenda; una ráfaga es una sola relectura.
 * - 1.2 y 1.3: la ficha y la agenda leen de la misma raíz; mientras se guarda
 *   «No asistió», los botones están ocupados y un segundo clic no manda otra orden.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource } from "@/components/inbox/__tests__/view-harness";

import type { ReservasData } from "../context";
import { BARBA, MARCOS, TODAY, booking, detail, service, servicesSettings, staff } from "../model/__tests__/fixtures";
import { ViewRef, a, renderView, resetMocks, screenRead, url } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("@/app/(console)/reservas/templates-actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

const LATER = "2026-10-22T19:41:00Z";
const ANA = booking({ local: { date: TODAY, start: "10:00", end: "10:45" }, contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: null } });
const PEDRO = booking({
  id: "00000000-0000-4000-8000-00000000b002",
  local: { date: TODAY, start: "17:30", end: "18:15" },
  status: "pending",
  contact: { name: "Pedro Soto", phone: null, conversation_id: null },
});
/** What the agent booked meanwhile: only a re-read brings it. */
const RITA = booking({
  id: "00000000-0000-4000-8000-00000000b003",
  local: { date: TODAY, start: "18:30", end: "19:15" },
  origin: "agent",
  contact: { name: "Rita Mora", phone: "+56933334444", conversation_id: null },
});

function data(items = [ANA, PEDRO]): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez", position: 2 })],
    services: [service(), service({ id: BARBA, name: "Barba", duration_minutes: 30, price: { kind: "none" } })],
    bookings: { items, closed_days: [], truncated: false },
    occupancy: null,
    blocks: null,
    waitlist: { enabled: true, items: [] },
    offers: null,
  };
}

/** `hidden`: with a booking's panel open (modal), the agenda behind it is still painted. */
const rita = () => screen.queryByRole("button", { name: /Rita Mora · Corte y barba/, hidden: true });

beforeEach(() => {
  resetMocks();
  FakeEventSource.last = null;
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Reservas · una sola fuente que se relee (spec 082)", () => {
  it("tras una escritura, la agenda relee por la acción y pinta lo que trae (1.1)", async () => {
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ ...PEDRO, allowed: ["confirm"] }) });
    a.bookingTransitionAction.mockResolvedValue({ ok: true, data: { ...PEDRO, status: "confirmed" } });
    a.reservasScreenAction.mockResolvedValue(screenRead(data([ANA, { ...PEDRO, status: "confirmed" }, RITA]), LATER));
    renderView(data());
    expect(rita()).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Pedro Soto · Corte y barba · Sin confirmar/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Pedro Soto" });
    await userEvent.click(await within(sheet).findByRole("button", { name: "Marcar confirmada" }));
    await waitFor(() => expect(a.reservasScreenAction).toHaveBeenCalledWith(url()));
    await waitFor(() => expect(rita()).toBeInTheDocument());
  });

  it("un reservations.changed relee la agenda sin esperar al sondeo (1.7)", async () => {
    a.reservasScreenAction.mockResolvedValue(screenRead(data([ANA, PEDRO, RITA]), LATER));
    renderView(data(), { live: true });
    expect(a.reservasScreenAction).not.toHaveBeenCalled();
    act(() => FakeEventSource.last!.emit("reservations.changed", { event: "reservations.changed", at: LATER }));
    await waitFor(() => expect(rita()).toBeInTheDocument());
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
  });

  it("una ráfaga de avisos es una sola relectura (1.7)", async () => {
    vi.useFakeTimers();
    a.reservasScreenAction.mockResolvedValue(screenRead(data([ANA, PEDRO, RITA]), LATER));
    renderView(data(), { live: true });
    act(() => {
      for (let i = 0; i < 5; i++) FakeEventSource.last!.emit("reservations.changed", { event: "reservations.changed", at: LATER });
    });
    await act(async () => void (await vi.advanceTimersByTimeAsync(2_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
    expect(rita()).toBeInTheDocument();
  });

  it("la ficha relee con la agenda: un aviso la pone al día también (1.2)", async () => {
    a.bookingDetailAction
      .mockResolvedValueOnce({ ok: true, data: detail({ ...PEDRO, allowed: ["confirm"] }) })
      .mockResolvedValue({ ok: true, data: detail({ ...PEDRO, status: "cancelled", allowed: [] }) });
    a.reservasScreenAction.mockResolvedValue(screenRead(data([ANA]), LATER));
    renderView(data(), { live: true });
    await userEvent.click(screen.getByRole("button", { name: /Pedro Soto · Corte y barba · Sin confirmar/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Pedro Soto" });
    expect(await within(sheet).findByRole("button", { name: "Marcar confirmada" })).toBeInTheDocument();
    act(() => FakeEventSource.last!.emit("reservations.changed", { event: "reservations.changed", at: LATER }));
    await waitFor(() => expect(within(sheet).queryByRole("button", { name: "Marcar confirmada" })).toBeNull());
    expect(a.bookingDetailAction).toHaveBeenCalledTimes(2);
  });

  it("mientras se guarda «No asistió», los botones están ocupados y un segundo clic no manda otra orden (1.3)", async () => {
    const past = { ...ANA, status: "confirmed" as const };
    a.bookingDetailAction
      .mockResolvedValueOnce({ ok: true, data: detail({ ...past, allowed: ["arrive", "noshow"] }) })
      .mockResolvedValue({ ok: true, data: detail({ ...past, status: "noshow", allowed: ["undo"] }) });
    let answer: (v: unknown) => void = () => undefined;
    a.bookingTransitionAction.mockImplementation(() => new Promise((r) => (answer = r)));
    renderView(data([past]));
    await userEvent.click(screen.getByRole("button", { name: /Ana Pérez · Corte y barba/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Ana Pérez" });
    const noshow = await within(sheet).findByRole("button", { name: "No asistió" });
    fireEvent.click(noshow);
    fireEvent.click(noshow);
    expect(a.bookingTransitionAction).toHaveBeenCalledTimes(1);
    expect(noshow).toHaveAttribute("aria-busy", "true");
    expect(noshow).toBeDisabled();
    expect(within(sheet).getByRole("button", { name: "Llegó" })).toBeDisabled();
    // The answer comes, and the panel stays busy until the booking is read again.
    await act(async () => answer({ ok: true, data: { ...past, status: "noshow" } }));
    await waitFor(() => expect(within(sheet).getByRole("button", { name: "Deshacer" })).toBeEnabled());
    expect(a.bookingTransitionAction).toHaveBeenCalledTimes(1);
  });
});
