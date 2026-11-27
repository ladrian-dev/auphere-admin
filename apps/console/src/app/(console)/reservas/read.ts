import "server-only";

import type { ReservasData } from "@/components/reservas/context";
import { addDays, localClock, periodRange } from "@/components/reservas/model/dates";
import { parseBookingParam, parseReservasUrl, type SearchParams } from "@/components/reservas/model/url-state";
import type { ReservasInitial } from "@/components/reservas/reservas-view";
import { backendFor } from "@/lib/backend";
import type { ClientPrincipal } from "@/lib/principal";

/** How far ahead Ajustes lists the blocks of Aforo. */
const BLOCKS_AHEAD_DAYS = 90;

/**
 * What Reservas shows for a URL (spec 043, T022), read on the server. Spec 082
 * moved it out of the page so the page (the first paint) and
 * `reservasScreenAction` (each re-read of React Query) read **exactly** the
 * same thing: two copies of a read drift apart.
 *
 * The settings say the mode (Servicios or Aforo) and the business's time zone
 * — «today» is the business's, not the server's. Then only what the tab and
 * the period need; each part degrades on its own (`null` → that part says it
 * could not load, and the screen says the rest is up to date).
 */
export async function readReservas(principal: ClientPrincipal, sp: SearchParams, nowIso: string): Promise<ReservasInitial> {
  const api = backendFor(principal);
  const hasInbox = principal.modules.includes("inbox");
  const booking = parseBookingParam(sp);

  const settings = await api.reservasSettings().catch(() => null);
  if (!settings) {
    const today = localClock(new Date(nowIso), "UTC").date;
    return { url: parseReservasUrl(sp, { today, mode: "services" }), nowIso, data: null, errors: [], hasInbox, booking };
  }

  const today = localClock(new Date(nowIso), settings.timezone).date;
  const url = parseReservasUrl(sp, { today, mode: settings.mode });
  const range = periodRange(url.period, url.date);
  const errors: string[] = [];
  const part = <T,>(name: string, read: () => Promise<T>): Promise<T | null> =>
    read().catch(() => {
      errors.push(name);
      return null;
    });
  const none = Promise.resolve(null);
  const services = settings.mode === "services";
  const agenda = url.tab === "agenda";
  // The day and week grids of Servicios hold the slots being offered to the waitlist (design §3.1).
  const holdsOffers = services && agenda && settings.waitlist.enabled && url.view === "grid" && url.period !== "month";

  const [staff, catalog, bookings, occupancy, blocks, waitlist, offers] = await Promise.all([
    // Servicios: the team and the catalog are needed everywhere — «Nueva reserva» lives in the header.
    services ? part("staff", () => api.reservasStaff().then((r) => r.items)) : none,
    services ? part("services", () => api.reservasServices().then((r) => r.items)) : none,
    agenda ? part("bookings", () => api.reservasBookings({ from: range.from, to: range.to })) : none,
    !services && agenda ? part("occupancy", () => api.reservasOccupancy(range.from, range.to)) : none,
    !services
      ? part("blocks", () =>
          (agenda ? api.reservasBlocks(range.from, range.to) : api.reservasBlocks(today, addDays(today, BLOCKS_AHEAD_DAYS))).then((r) => r.items),
        )
      : none,
    // The waitlist names the tab («Lista de espera (3)») and fills the hour panel and the rail.
    part("waitlist", () => api.reservasWaitlist()),
    services && url.tab === "waitlist"
      ? part("offers", () =>
          Promise.all([api.reservasOffers("running"), api.reservasOffers("recent")]).then(([running, recent]) => ({
            running: running.items,
            recent: recent.items,
          })),
        )
      : holdsOffers
        ? part("offers", () => api.reservasOffers("running").then((r) => ({ running: r.items, recent: [] })))
        : none,
  ]);

  const data: ReservasData = { settings, staff, services: catalog, bookings, occupancy, blocks, waitlist, offers };
  return { url, nowIso, data, errors, hasInbox, booking };
}
