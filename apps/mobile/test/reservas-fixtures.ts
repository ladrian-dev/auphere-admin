import type { ResConfig, Reservation } from "@/api/reservas";

/**
 * Fixed data for Reservas' tests (spec 044): «Barbería Norte» (Servicios) and
 * «Casa Lucía» (Aforo) on Thursday 22 October 2026, at the design's hours.
 */
export const TODAY = "2026-10-22";

export const servicesConfig: ResConfig = {
  mode: "services",
  timezone: "America/Santiago",
  currency: "CLP",
  hours: [
    ...([1, 2, 3, 4, 5] as const).map((weekday) => ({ weekday, open: 540, close: 1140 })),
    { weekday: 6, open: 540, close: 840 },
  ],
  hoursLabel: "lunes a viernes 9:00–19:00, sábado 9:00–14:00",
  hoursMissing: false,
  version: 3,
  waitlist: { enabled: true, leadHours: 2, editable: true },
  confirmation: { enabled: true, when: "24h", editable: true },
  services: {
    stepMin: 30,
    team: [
      { id: "p-javiera", name: "Javiera Muñoz", calendar: "google" },
      { id: "p-marcos", name: "Marcos Soto", calendar: "google" },
    ],
    catalog: [
      { id: "s-corte", name: "Corte", durationMin: 30, price: 12000, proIds: null },
      { id: "s-peinado", name: "Corte y peinado", durationMin: 45, price: 18000, proIds: null },
    ],
  },
  capacity: null,
};

export const capacityConfig: ResConfig = {
  mode: "capacity",
  timezone: "America/Santiago",
  currency: "CLP",
  hours: ([1, 2, 3, 4, 5, 6, 7] as const).map((weekday) => ({ weekday, open: 780, close: 1410 })),
  hoursLabel: null,
  hoursMissing: false,
  version: 3,
  waitlist: { enabled: true, leadHours: 2, editable: true },
  confirmation: { enabled: true, when: "24h", editable: false },
  services: null,
  capacity: {
    unit: "comensales",
    capacity: 64,
    stayMin: 90,
    maxParty: 10,
    walkinReserved: 6,
    shifts: [
      { name: "Comida", from: 780, to: 900, everyMin: 30 },
      { name: "Cena", from: 1200, to: 1320, everyMin: 30 },
    ],
    closed: [{ weekday: 7, shift: "Cena" }],
    blocks: [],
    editable: true,
  },
};

let n = 0;
export function res(over: Partial<Reservation>): Reservation {
  n += 1;
  return {
    id: `r${n}`,
    date: TODAY,
    start: 600,
    end: 645,
    state: "confirmed",
    customer: { name: `Cliente ${n}`, phone: "+56 9 1234 5678" },
    origin: "agent",
    channel: "whatsapp",
    by: null,
    createdAt: "2026-10-21T10:00:00-03:00",
    arrivedAt: null,
    service: null,
    pro: null,
    partySize: null,
    conflict: null,
    events: [{ kind: "created", at: "2026-10-21T10:00:00-03:00", actor: null, data: { channel: "whatsapp", origin: "agent" } }],
    actions: [],
    version: 1,
    arrivedLocal: null,
    lateMinutes: null,
    ...over,
  };
}

export const marcos = { id: "p-marcos", name: "Marcos Soto" };
export const javiera = { id: "p-javiera", name: "Javiera Muñoz" };
export const corte = { id: "s-corte", name: "Corte", durationMin: 30, price: 12000 };
export const peinado = { id: "s-peinado", name: "Corte y peinado", durationMin: 45, price: 18000 };
