import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import type { ReservasData } from "../context";
import { BARBA, MARCOS, NOW_ISO, TODAY, booking, service, servicesSettings, staff } from "../model/__tests__/fixtures";
import type { ReservasInitial } from "../reservas-view";
import { ViewRef, a, renderView, resetMocks, screenRead, url } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("@/app/(console)/reservas/templates-actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

const STALE = "Puede que esto no esté al día.";

function data(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez", position: 2 })],
    services: [service(), service({ id: BARBA, name: "Barba", duration_minutes: 30, price: { kind: "none" } })],
    bookings: {
      items: [booking({ local: { date: TODAY, start: "10:00", end: "10:45" }, contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: null } })],
      closed_days: [],
      truncated: false,
    },
    occupancy: null,
    blocks: null,
    waitlist: { enabled: true, items: [] },
    offers: null,
    ...o,
  };
}

function again(view: ReturnType<typeof renderView>, initial: Partial<ReservasInitial>) {
  const View = ViewRef.current!;
  view.rerender(
    <LocaleProvider locale="es">
      <View initial={{ url: url(), nowIso: NOW_ISO, data: data(), errors: [], hasInbox: true, booking: null, ...initial }} />
    </LocaleProvider>,
  );
}

function visibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  fireEvent(document, new Event("visibilitychange"));
}

beforeEach(() => {
  resetMocks();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
});
afterEach(() => vi.useRealTimers());

/** Spec 064 (2.6 a 2.9): the open agenda reads again on its own, and says when it could not. */
describe("Reservas · la agenda se pone al día sola (spec 064)", () => {
  // Revisión antes de producción (UI-2): a tab opened on Monday without a date
  // on its URL is today's agenda, and on Tuesday it must read Tuesday's.
  it("without a date on the URL, a re-read the next day asks for the business's today, not the first paint's day", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-23T12:00:00Z"));
    const tomorrow = { date: "2026-10-23" };
    a.reservasScreenAction.mockResolvedValue(screenRead(data(), "2026-10-23T12:00:45Z", { url: tomorrow, followsToday: true }));
    renderView(data(), { followsToday: true });
    await act(async () => void (await vi.advanceTimersByTimeAsync(45_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
    expect(a.reservasScreenAction).toHaveBeenCalledWith({ ...url(), date: null });
    // The day it brought does not pin the next re-read either.
    await act(async () => void (await vi.advanceTimersByTimeAsync(45_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(2);
    expect(a.reservasScreenAction).toHaveBeenLastCalledWith({ ...url(), date: null });
  });

  it("with a date on the URL, a re-read the next day stays on that day", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-23T12:00:00Z"));
    a.reservasScreenAction.mockResolvedValue(screenRead(data(), "2026-10-23T12:00:45Z", { url: { date: "2026-10-21" } }));
    renderView(data(), { url: { date: "2026-10-21" }, followsToday: false });
    await act(async () => void (await vi.advanceTimersByTimeAsync(45_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledWith(url({ date: "2026-10-21" }));
  });

  it("reads again every 45 s while the tab is visible, without dimming the screen", async () => {
    vi.useFakeTimers();
    // Spec 082: each pass is a re-read through the action, in the background.
    a.reservasScreenAction.mockResolvedValue(screenRead(data(), "2026-10-22T19:41:00Z"));
    const view = renderView(data());
    await act(async () => void (await vi.advanceTimersByTimeAsync(44_000)));
    expect(a.reservasScreenAction).not.toHaveBeenCalled();
    await act(async () => void (await vi.advanceTimersByTimeAsync(1_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
    expect(a.reservasScreenAction).toHaveBeenCalledWith(url());
    expect(view.container.querySelector("[aria-busy]")).toBeNull();
    await act(async () => void (await vi.advanceTimersByTimeAsync(45_000)));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(2);
  });

  it("does not read while the tab is hidden, and reads at once when it is seen again", () => {
    vi.useFakeTimers();
    renderView(data());
    act(() => visibility("hidden"));
    act(() => void vi.advanceTimersByTime(120_000));
    expect(a.reservasScreenAction).not.toHaveBeenCalled();
    act(() => visibility("visible"));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
  });

  it("spec 082 (1.9): the connection coming back reads again, unless the read is recent", () => {
    vi.useFakeTimers();
    renderView(data());
    act(() => void window.dispatchEvent(new Event("online")));
    expect(a.reservasScreenAction).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(20_000));
    act(() => void window.dispatchEvent(new Event("online")));
    expect(a.reservasScreenAction).toHaveBeenCalledTimes(1);
  });

  it("coming back to a tab that has just been read does not read again", () => {
    vi.useFakeTimers();
    renderView(data());
    act(() => void vi.advanceTimersByTime(5_000));
    act(() => visibility("hidden"));
    act(() => visibility("visible"));
    expect(a.reservasScreenAction).not.toHaveBeenCalled();
  });

  it("a new read keeps an open dialog and what was typed in it", async () => {
    a.serviceSlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [] } });
    const view = renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Nueva reserva" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Cliente/), "Rita Mora");
    again(view, { nowIso: "2026-10-22T19:41:00Z" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByLabelText(/Cliente/)).toHaveValue("Rita Mora");
  });

  it("a read that comes back empty keeps the last good one and says it may be out of date", async () => {
    const view = renderView(data());
    expect(screen.queryByText(STALE)).toBeNull();
    // The live region is there before the notice, so a screen reader hears it appear (WCAG 4.1.3).
    const live = document.querySelector('[data-slot="reservas-stale-live"]');
    expect(live).toHaveAttribute("role", "status");
    expect(live).toBeEmptyDOMElement();
    again(view, { nowIso: "2026-10-22T19:41:00Z", data: null });
    expect(screen.getByRole("button", { name: /Ana Pérez · Corte y barba · Confirmada/ })).toBeInTheDocument();
    expect(document.querySelector('[data-slot="reservas-stale-live"]')).toBe(live);
    expect(live).toHaveTextContent(STALE);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(a.reservasScreenAction).toHaveBeenCalled();
    // The next good read takes the notice away.
    again(view, { nowIso: "2026-10-22T19:42:00Z" });
    expect(screen.queryByText(STALE)).toBeNull();
  });

  it("a read with a part that failed keeps the last good one too", () => {
    const view = renderView(data());
    again(view, { nowIso: "2026-10-22T19:41:00Z", data: data({ bookings: null }), errors: ["bookings"] });
    expect(screen.getByRole("button", { name: /Ana Pérez · Corte y barba · Confirmada/ })).toBeInTheDocument();
    expect(screen.getAllByText(STALE)).toHaveLength(2); // what is seen, and what is heard
  });

  it("another period has no last good read to keep: it says what failed, as before", () => {
    const view = renderView(data());
    again(view, { url: url({ period: "week" }), data: data({ bookings: null }), errors: ["bookings"] });
    expect(screen.queryByText(STALE)).toBeNull();
    expect(screen.getByText(/Parte de la información no se pudo cargar/)).toBeInTheDocument();
  });

  it("with no new read for more than 150 s it says it may be out of date", () => {
    vi.useFakeTimers();
    renderView(data());
    // The reads are asked for (the spy does nothing), and none arrives.
    act(() => void vi.advanceTimersByTime(135_000));
    expect(screen.queryByText(STALE)).toBeNull();
    act(() => void vi.advanceTimersByTime(45_000));
    expect(screen.getAllByText(STALE)).toHaveLength(2); // what is seen, and what is heard
  });

  it("the first read that fails is still an error, not a stale screen", () => {
    renderView(null);
    expect(screen.queryByText(STALE)).toBeNull();
  });
});
