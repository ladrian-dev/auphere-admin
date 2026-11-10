import type * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { capacitySettings, offer, servicesSettings } from "@/components/reservas/model/__tests__/fixtures";
import type { ReservasInitial } from "@/components/reservas/reservas-view";

/**
 * Spec 043 (T023, T026): what the page reads for the URL. The agenda of
 * Servicios reads the offers running now (to hold their slots on the grid)
 * only when the waitlist is on, and a `booking` on the URL — the Panel's link
 * — reaches the screen to open that booking.
 */
const api = vi.hoisted(() => ({
  reservasSettings: vi.fn(),
  reservasStaff: vi.fn(),
  reservasServices: vi.fn(),
  reservasBookings: vi.fn(),
  reservasOccupancy: vi.fn(),
  reservasBlocks: vi.fn(),
  reservasWaitlist: vi.fn(),
  reservasOffers: vi.fn(),
}));

vi.mock("@/lib/principal", () => ({
  requireClientPrincipal: async () => ({ kind: "client", modules: ["panel", "inbox", "reservas"], locale: "es" }),
}));
vi.mock("@/lib/backend", () => ({ backendFor: () => api }));
vi.mock("@/i18n/metadata", () => ({ pageTitle: async () => ({}) }));
vi.mock("@/components/reservas/reservas-view", () => ({ ReservasView: () => null }));

const ReservasPage = (await import("../page")).default;

const BOOKING = "00000000-0000-4000-8000-00000000f00d";

async function initial(sp: Record<string, string> = {}): Promise<ReservasInitial> {
  const el = (await ReservasPage({ searchParams: Promise.resolve(sp) })) as React.ReactElement<{ initial: ReservasInitial }>;
  return el.props.initial;
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
  api.reservasSettings.mockResolvedValue(servicesSettings());
  api.reservasStaff.mockResolvedValue({ items: [] });
  api.reservasServices.mockResolvedValue({ items: [] });
  api.reservasBookings.mockResolvedValue({ items: [], closed_days: [], truncated: false });
  api.reservasBlocks.mockResolvedValue({ items: [] });
  api.reservasWaitlist.mockResolvedValue({ enabled: true, items: [] });
  api.reservasOffers.mockResolvedValue({ items: [offer()] });
});

describe("Reservas · what the page reads", () => {
  it("Servicios, agenda grid, waitlist on: the running offers, to hold their slots", async () => {
    const init = await initial();
    expect(api.reservasOffers).toHaveBeenCalledTimes(1);
    expect(api.reservasOffers).toHaveBeenCalledWith("running");
    expect(init.data?.offers?.running).toHaveLength(1);
    expect(init.data?.offers?.recent).toEqual([]);
    expect(init.errors).toEqual([]);
  });

  it("the waitlist off, a list, a month or Aforo: no offers to hold, so none are read", async () => {
    api.reservasSettings.mockResolvedValue(servicesSettings({ waitlist: { enabled: false, lead_minutes: 120 } }));
    expect((await initial()).data?.offers).toBeNull();
    api.reservasSettings.mockResolvedValue(servicesSettings());
    expect((await initial({ view: "list" })).data?.offers).toBeNull();
    expect((await initial({ period: "month" })).data?.offers).toBeNull();
    api.reservasSettings.mockResolvedValue(capacitySettings());
    api.reservasOccupancy.mockResolvedValue({ seats: 64, walkin_hold: 6, stay_minutes: 90, days: [] });
    expect((await initial()).data?.offers).toBeNull();
    expect(api.reservasOffers).not.toHaveBeenCalled();
  });

  it("offers that did not load are a partial read, not an error", async () => {
    api.reservasOffers.mockRejectedValue(new Error("down"));
    const init = await initial();
    expect(init.data?.offers).toBeNull();
    expect(init.errors).toEqual(["offers"]);
    expect(init.data?.bookings).not.toBeNull();
  });

  it("the waitlist tab still reads the running and the recent ones", async () => {
    await initial({ tab: "waitlist" });
    expect(api.reservasOffers.mock.calls.map((c) => c[0])).toEqual(["running", "recent"]);
  });

  it("a booking on the URL reaches the screen; anything else is ignored", async () => {
    expect((await initial({ booking: BOOKING })).booking).toBe(BOOKING);
    expect((await initial({ booking: "lucia" })).booking).toBeNull();
    expect((await initial()).booking).toBeNull();
  });
});
