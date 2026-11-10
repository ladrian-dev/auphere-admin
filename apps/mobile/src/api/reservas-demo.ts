import {
  addDays,
  currentSlot,
  hhmm,
  isClosed,
  openSpan,
  parseHHMM,
  slotsOfDay,
  sinceMinutes,
  wallClock,
  weekday,
  type BizNow,
  type LocalDate,
  type Minutes,
  type WallTime,
} from "@/lib/reservas-model";

import { ApiError } from "./errors";
import type {
  Block,
  ConfigPatch,
  Demo,
  DayOccupancy,
  FreeSlot,
  Mode,
  NewReservation,
  ResAction,
  ResConfig,
  Reservation,
  Slot,
  WaitEntry,
} from "./reservas";

/**
 * Example data for Reservas (spec 044, research D2, Requisito 18). Loaded only
 * by a development build that asks for it (`EXPO_PUBLIC_RESERVAS_DEMO`), and
 * every screen that shows it says «Datos de ejemplo». Two businesses of the
 * Chilean pilot: «Barbería Norte» (Servicios, CLP, Providencia) and «Casa
 * Lucía» (Aforo, 64 comensales). Its «now» is the design's (11:20 and 13:20 of
 * today, in Santiago), so screenshots read the same any time of the day.
 *
 * It answers with the model the adapter produces from the contract, and keeps
 * the API's rules where the screens depend on them: which actions a
 * reservation allows now, what fits, what is taken. Writes live in memory.
 */
const TZ = "America/Santiago";
const ME = "Valeria";

const FIRST = ["Camila", "Benjamín", "Valentina", "Matías", "Antonia", "Tomás", "Florencia", "Joaquín", "Isidora", "Vicente", "Catalina", "Agustín", "Josefa", "Martín", "Fernanda", "Diego", "Javiera", "Cristóbal", "Constanza", "Felipe"];
const LAST = ["Rojas", "Soto", "Díaz", "González", "Muñoz", "Silva", "Torres", "Contreras", "Morales", "Fuentes", "Herrera", "Castillo", "Reyes", "Vargas", "Pérez", "Araya", "Espinoza", "Sepúlveda"];

const SERVICES_CONFIG: ResConfig = {
  mode: "services",
  timezone: TZ,
  currency: "CLP",
  hours: [
    ...([1, 2, 3, 4, 5] as const).map((weekday) => ({ weekday, open: 9 * 60, close: 19 * 60 })),
    { weekday: 6, open: 9 * 60, close: 14 * 60 },
  ],
  hoursLabel: "lunes a viernes 9:00–19:00, sábado 9:00–14:00",
  hoursMissing: false,
  version: 1,
  waitlist: { enabled: true, leadHours: 2, editable: true },
  confirmation: { enabled: true, when: "24h", editable: true },
  services: {
    stepMin: 30,
    team: [
      { id: "p-javiera", name: "Javiera Muñoz", calendar: "google" },
      { id: "p-marcos", name: "Marcos Soto", calendar: "google" },
      { id: "p-andres", name: "Andrés Pérez", calendar: "none" },
    ],
    catalog: [
      { id: "s-corte", name: "Corte", durationMin: 30, price: 12000, proIds: null },
      { id: "s-peinado", name: "Corte y peinado", durationMin: 45, price: 18000, proIds: null },
      { id: "s-color", name: "Color", durationMin: 90, price: 35000, proIds: ["p-javiera"] },
      { id: "s-barba", name: "Barba", durationMin: 30, price: 8000, proIds: ["p-marcos", "p-andres"] },
      { id: "s-cortebarba", name: "Corte y barba", durationMin: 45, price: 16000, proIds: ["p-marcos", "p-andres"] },
    ],
  },
  capacity: null,
};

const CAPACITY_CONFIG = (today: LocalDate): ResConfig => ({
  mode: "capacity",
  timezone: TZ,
  currency: "CLP",
  hours: ([1, 2, 3, 4, 5, 6, 7] as const).map((weekday) => ({ weekday, open: 13 * 60, close: 23 * 60 + 30 })),
  hoursLabel: "todos los días, comida 13:00–15:00 y cena 20:00–22:00; domingo sin cena",
  hoursMissing: false,
  version: 1,
  waitlist: { enabled: true, leadHours: 2, editable: true },
  confirmation: { enabled: true, when: "24h", editable: true },
  services: null,
  capacity: {
    unit: "comensales",
    kind: "restaurant",
    capacity: 64,
    stayMin: 90,
    maxParty: 10,
    walkinReserved: 6,
    shifts: [
      { name: "Comida", from: 13 * 60, to: 15 * 60, everyMin: 30 },
      { name: "Cena", from: 20 * 60, to: 22 * 60, everyMin: 30 },
    ],
    closed: [{ weekday: 7, shift: "Cena" }],
    blocks: [{ id: "b-evento", date: addDays(today, 2), from: 20 * 60, until: 22 * 60, shift: "Cena", reason: "Evento privado · cena de empresa" }],
    editable: true,
  },
});

/** A small seeded generator: the same day always gets the same bookings. */
function rng(seed: string) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}

const pick = <T,>(r: () => number, list: readonly T[]): T => list[Math.floor(r() * list.length)] as T;
const phone = (r: () => number) => `+56 9 ${Math.floor(1000 + r() * 8999)} ${Math.floor(1000 + r() * 8999)}`;
const at = (date: LocalDate, m: Minutes) => `${date}T${hhmm(m)}:00-03:00`;
/** `when`, or a couple of minutes after `after` if `when` is not later (both in the business's offset). */
const notBefore = (when: string, after: string) => (when > after ? when : at(after.slice(0, 10) as LocalDate, parseHHMM(after.slice(11, 16)) + 2));
/** A deep copy that every runtime has (Hermes may lack `structuredClone`). */
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

export function createDemo(mode: Mode, state: "empty" | "error" | "slow" | null): Demo {
  const born = wallClock(TZ);
  const today = born.date;
  const clock: BizNow = { date: today, minutes: mode === "services" ? 11 * 60 + 20 : 13 * 60 + 20, readAt: Date.now() };
  const now = (): WallTime => sinceMinutes(clock);
  let config: ResConfig = mode === "services" ? clone(SERVICES_CONFIG) : CAPACITY_CONFIG(today);
  const days = new Map<LocalDate, Reservation[]>();
  const keys = new Map<string, Reservation>();
  let seq = 0;
  let notices = {
    kinds: ["inbox.waiting", "inbox.message_for_you", "client.balance", "reservas.agent_change", "reservas.cancelled_today"],
    quiet_outside_hours: true,
  };

  const latency = state === "slow" ? 2500 : 350;
  const wait = () => new Promise<void>((r) => setTimeout(r, latency));
  const read = async <T,>(f: () => T): Promise<T> => {
    await wait();
    if (state === "error") throw new ApiError(503, null);
    return f();
  };
  const write = async <T,>(f: () => T): Promise<T> => {
    await wait();
    return f();
  };

  // ── the bookings of a day ───────────────────────────────────────────

  function stateFor(r: () => number, date: LocalDate, end: Minutes): Reservation["state"] {
    const n = now();
    if (date < n.date || (date === n.date && end <= n.minutes)) return r() < 0.06 ? "noshow" : r() < 0.05 ? "cancelled" : "done";
    if (r() < 0.04) return "cancelled";
    const soon = date <= addDays(n.date, 1);
    return r() < (soon ? 0.35 : 0.12) ? "pending" : "confirmed";
  }

  function origin(r: () => number): Pick<Reservation, "origin" | "channel" | "by"> {
    const x = r();
    if (x < 0.66) return { origin: "agent", channel: "whatsapp", by: null };
    if (x < 0.94) return { origin: "person", channel: "phone", by: ME };
    return { origin: "waitlist", channel: "whatsapp", by: null };
  }

  /** The history the API would keep (043 §4 `events`); the screen puts the words. */
  function events(res: Reservation): Reservation["events"] {
    const out: Reservation["events"] = [];
    const created = res.createdAt;
    out.push({ kind: "created", at: created, actor: res.origin === "person" ? (res.by ?? ME) : null, data: { channel: res.channel, origin: res.origin } });
    if (res.origin === "waitlist") out.push({ kind: "waitlist_accepted", at: created, actor: null, data: {} });
    // The day before at 9:00, or just after it was made when it was made later than that.
    const asked = notBefore(at(addDays(res.date, -1), 9 * 60), created);
    if (res.state === "pending") out.push({ kind: "confirmation_requested", at: asked, actor: null, data: {} });
    if (res.state === "confirmed" && res.origin === "agent") out.push({ kind: "replied_yes", at: notBefore(at(addDays(res.date, -1), 9 * 60 + 12), asked), actor: null, data: {} });
    if (res.state === "cancelled") out.push({ kind: "cancelled", at: at(res.date, 8 * 60), actor: null, data: { by: "customer" } });
    return out;
  }

  function make(r: () => number, date: LocalDate, start: Minutes, end: Minutes, extra: Partial<Reservation>): Reservation {
    const o = origin(r);
    const res: Reservation = {
      id: `r-${date}-${seq++}`,
      date,
      start,
      end,
      state: stateFor(r, date, end),
      customer: { name: `${pick(r, FIRST)} ${pick(r, LAST)}`, phone: o.channel === "whatsapp" || r() < 0.7 ? phone(r) : null },
      ...o,
      createdAt: at(addDays(date, -1 - Math.floor(r() * 5)), 10 * 60 + Math.floor(r() * 600)),
      arrivedAt: null,
      service: null,
      pro: null,
      partySize: null,
      conflict: null,
      lateMinutes: null,
      events: [],
      actions: [],
      version: 1,
      arrivedLocal: null,
      ...extra,
    };
    res.events = events(res);
    return res;
  }

  function generate(date: LocalDate): Reservation[] {
    if (state === "empty" || isClosed(config, date)) return [];
    const r = rng(`${mode}:${date}`);
    const out: Reservation[] = [];
    if (config.mode === "services" && config.services) {
      const span = openSpan(config, date);
      if (!span) return [];
      const busy = weekday(date) === 6 ? 0.62 : 0.48;
      for (const pro of config.services.team) {
        const can = config.services.catalog.filter((s) => s.proIds === null || s.proIds.includes(pro.id));
        let t = span.open;
        while (t < span.close) {
          const svc = pick(r, can);
          if (r() < busy && t + svc.durationMin <= span.close) {
            out.push(make(r, date, t, t + svc.durationMin, { service: { id: svc.id, name: svc.name, durationMin: svc.durationMin, price: svc.price }, pro: { id: pro.id, name: pro.name } }));
            t += Math.ceil(svc.durationMin / 30) * 30;
          } else t += 30;
        }
      }
      // One booking that clashes with a Google Calendar «busy», tomorrow (Servicios only).
      if (date === addDays(today, 1)) {
        const c = out.find((x) => x.pro?.id === "p-marcos" && x.state !== "cancelled");
        if (c) c.conflict = { source: "google", label: "Ocupado" };
      }
    } else if (config.capacity) {
      const cap = config.capacity;
      const limit = cap.capacity - cap.walkinReserved;
      for (const s of slotsOfDay(config, date)) {
        const howMany = 1 + Math.floor(r() * 4);
        for (let i = 0; i < howMany; i++) {
          const party = 2 + Math.floor(r() * 7);
          const inside = presence(out, date, s.time);
          if (inside + party > limit * (0.55 + r() * 0.4)) break;
          out.push(make(r, date, s.time, s.time + cap.stayMin, { partySize: party }));
        }
      }
      // Today: who is inside arrived; one is late; two walked in.
      if (date === today) {
        const n = now();
        for (const x of out) {
          if (x.state === "cancelled" || x.state === "noshow") continue;
          if (x.start <= n.minutes && n.minutes < x.end) {
            const m = x.start + Math.floor(r() * 12);
            x.state = "arrived";
            x.arrivedAt = at(date, m);
            x.arrivedLocal = hhmm(m);
          }
        }
        const late = out.find((x) => x.state === "arrived" && x.start === 13 * 60);
        if (late) {
          late.state = "confirmed";
          late.arrivedAt = null;
          late.arrivedLocal = null;
        }
        out.push(walkin(date, 13 * 60, 2, ""), walkin(date, 13 * 60, 3, "Ignacio"));
      }
    }
    // The contact of the local inbox, so «Próxima reserva» has something to show.
    if (date === addDays(today, 1)) {
      const lucia = mode === "services"
        ? make(r, date, 17 * 60, 17 * 60 + 45, {
            service: { id: "s-peinado", name: "Corte y peinado", durationMin: 45, price: 18000 },
            pro: { id: "p-marcos", name: "Marcos Soto" },
          })
        : make(r, date, 21 * 60, 22 * 60 + 30, { partySize: 4 });
      lucia.customer = { name: "Lucía Fernández", phone: "+56 9 6123 4567" };
      lucia.state = "confirmed";
      lucia.origin = "agent";
      lucia.channel = "whatsapp";
      lucia.by = null;
      lucia.events = events(lucia);
      out.push(lucia);
    }
    return out.sort((a, b) => a.start - b.start);
  }

  function walkin(date: LocalDate, start: Minutes, party: number, name: string): Reservation {
    const stay = config.capacity?.stayMin ?? 90;
    const res: Reservation = {
      id: `r-${date}-${seq++}`,
      date,
      start,
      end: start + stay,
      state: "arrived",
      customer: { name, phone: null },
      origin: "walkin",
      channel: "in_person",
      by: ME,
      createdAt: at(date, start + 5),
      arrivedAt: at(date, start + 5),
      service: null,
      pro: null,
      partySize: party,
      conflict: null,
      lateMinutes: null,
      events: [],
      actions: [],
      version: 1,
      arrivedLocal: hhmm(start + 5),
    };
    res.events = [{ kind: "created", at: res.createdAt, actor: ME, data: { channel: "in_person", origin: "walkin" } }];
    return res;
  }

  function day(date: LocalDate): Reservation[] {
    let list = days.get(date);
    if (!list) {
      list = generate(date);
      days.set(date, list);
    }
    return list;
  }

  /** Inside at a time, as the API counts it for occupancy (finished ones too, on past days). */
  function presence(list: readonly Reservation[], date: LocalDate, t: Minutes): number {
    const stay = config.capacity?.stayMin ?? 90;
    return list
      .filter((x) => x.date === date && x.state !== "cancelled" && x.state !== "noshow")
      .filter((x) => x.start <= t && t < x.start + stay)
      .reduce((sum, x) => sum + (x.partySize ?? 0), 0);
  }

  /** What the API would let a person do with it now (contracts §3, `actions`). */
  function allowed(x: Reservation): ResAction[] {
    const n = now();
    const isToday = x.date === n.date;
    const future = x.date > n.date || (isToday && x.start > n.minutes);
    const expected = x.state === "pending" || x.state === "confirmed";
    const out: ResAction[] = [];
    if (x.state === "pending") out.push("confirm");
    if (config.mode === "capacity") {
      const stay = config.capacity?.stayMin ?? 90;
      if (isToday && expected && x.start - n.minutes <= 30 && n.minutes < x.start + stay) out.push("arrived");
      if (isToday && expected && n.minutes >= x.start) out.push("noshow");
      if (isToday && (x.state === "arrived" || x.state === "noshow") && x.origin !== "walkin") out.push("undo");
      if (expected && future && x.origin !== "walkin") out.push("cancel");
    } else {
      if (isToday && expected && n.minutes >= x.start) out.push("noshow");
      if (isToday && x.state === "noshow") out.push("undo");
      if (expected && future) out.push("cancel");
    }
    return out;
  }

  const view = (x: Reservation): Reservation => {
    const n = now();
    const stay = config.capacity?.stayMin ?? 90;
    const expected = x.state === "pending" || x.state === "confirmed";
    // The API's `late_minutes` (043 §4): Aforo, still expected, 15 min or more past its time, within the stay.
    const late = config.mode === "capacity" && expected && x.date === n.date && n.minutes - x.start >= 15 && n.minutes < x.start + stay ? n.minutes - x.start : null;
    return { ...x, actions: allowed(x), lateMinutes: late, events: [...x.events] };
  };

  function find(id: string): Reservation {
    for (const list of days.values()) {
      const x = list.find((r) => r.id === id);
      if (x) return x;
    }
    throw new ApiError(404, "not_found");
  }

  function datesBetween(from: LocalDate, to: LocalDate): LocalDate[] {
    const out: LocalDate[] = [];
    for (let d = from; d <= to; d = addDays(d, 1)) out.push(d);
    return out;
  }

  function slotsOf(date: LocalDate): Slot[] {
    const cap = config.capacity;
    if (!cap) return [];
    return slotsOfDay(config, date).map((s) => {
      const blocked = cap.blocks.find((b) => b.date === date && s.time >= b.from && s.time <= b.until);
      return { date, time: s.time, inside: presence(day(date), date, s.time), capacity: cap.capacity, blocked: blocked?.reason ?? null, closed: false };
    });
  }

  function dayPct(date: LocalDate): DayOccupancy {
    if (isClosed(config, date)) return { date, pct: null, closed: true };
    if (config.mode === "capacity") {
      const slots = slotsOf(date);
      const pct = slots.length ? Math.round((slots.reduce((a, s) => a + s.inside / s.capacity, 0) / slots.length) * 100) : null;
      return { date, pct, closed: false };
    }
    const span = openSpan(config, date);
    const team = config.services?.team.length ?? 1;
    if (!span) return { date, pct: null, closed: true };
    const booked = day(date)
      .filter((x) => x.state !== "cancelled")
      .reduce((a, x) => a + (x.end - x.start), 0);
    return { date, pct: Math.min(100, Math.round((booked / ((span.close - span.open) * team)) * 100)), closed: false };
  }

  function freeServices(date: LocalDate, serviceId: string | undefined, proId: string | null | undefined): FreeSlot[] {
    const s = config.services;
    const svc = s?.catalog.find((c) => c.id === serviceId);
    const span = openSpan(config, date);
    if (!s || !svc || !span) return [];
    const pros = s.team.filter((p) => (svc.proIds === null || svc.proIds.includes(p.id)) && (!proId || p.id === proId));
    const n = now();
    const out: FreeSlot[] = [];
    for (let t = span.open; t + svc.durationMin <= span.close; t += s.stepMin) {
      if (date < n.date || (date === n.date && t <= n.minutes)) continue;
      const free = pros.find((p) => !day(date).some((x) => x.pro?.id === p.id && x.state !== "cancelled" && x.start < t + svc.durationMin && t < x.end));
      if (free) out.push({ time: t, pro: { id: free.id, name: free.name }, left: null, full: false });
    }
    return out;
  }

  function leftAt(date: LocalDate, t: Minutes): number {
    const cap = config.capacity!;
    const window = slotsOf(date).filter((s) => s.time >= t && s.time < t + cap.stayMin);
    if (window.some((s) => s.blocked)) return 0;
    return Math.min(...window.map((s) => cap.capacity - cap.walkinReserved - s.inside), cap.capacity - cap.walkinReserved);
  }

  function freeCapacity(date: LocalDate, party: number): FreeSlot[] {
    const n = now();
    return slotsOfDay(config, date)
      .filter((s) => !(date === n.date && s.time <= n.minutes))
      .map((s) => {
        const left = Math.max(0, leftAt(date, s.time));
        return { time: s.time, pro: null, left, full: left < party };
      });
  }

  let waitlist: WaitEntry[] =
    state === "empty"
      ? []
      : mode === "services"
        ? [
            {
              id: "w1",
              name: "Florencia Araya",
              phone: "+56 9 7788 1122",
              wants: { date: null, time: null, partySize: null, service: "Corte y peinado", pro: "Marcos Soto", text: "Adelantar su cita del jueves a las 16:00" },
              state: "waiting",
              fits: null,
              offeredUntil: null,
              joinedBy: "agent",
              by: null,
              joinedAt: at(addDays(today, -1), 18 * 60 + 40),
            },
            {
              id: "w2",
              name: "Cristóbal Reyes",
              phone: "+56 9 6543 2109",
              wants: { date: null, time: null, partySize: null, service: "Corte", pro: null, text: "Cualquier hora antes del viernes" },
              state: "waiting",
              fits: null,
              offeredUntil: null,
              joinedBy: "person",
              by: ME,
              joinedAt: at(today, 9 * 60 + 5),
            },
          ]
        : [
            {
              id: "w1",
              name: "Josefa Castillo",
              phone: "+56 9 5555 1234",
              wants: { date: today, time: 14 * 60, partySize: 2, service: null, pro: null, text: null },
              state: "offered",
              fits: true,
              offeredUntil: new Date(Date.now() + 9 * 60_000).toISOString(),
              joinedBy: "agent",
              by: null,
              joinedAt: at(addDays(today, -1), 21 * 60 + 2),
            },
            {
              id: "w2",
              name: "Martín Herrera",
              phone: "+56 9 4321 8765",
              wants: { date: today, time: 13 * 60 + 30, partySize: 4, service: null, pro: null, text: null },
              state: "waiting",
              fits: true,
              offeredUntil: null,
              joinedBy: "agent",
              by: null,
              joinedAt: at(today, 10 * 60 + 15),
            },
            {
              id: "w3",
              name: "Constanza Vargas",
              phone: null,
              wants: { date: today, time: 21 * 60, partySize: 8, service: null, pro: null, text: null },
              state: "waiting",
              fits: false,
              offeredUntil: null,
              joinedBy: "person",
              by: ME,
              joinedAt: at(today, 11 * 60 + 40),
            },
          ];

  const demo: Demo = {
    mode,

    me(me) {
      if (me.nav.includes("reservas")) return me;
      const nav = [...me.nav];
      const i = nav.indexOf("usage");
      nav.splice(i >= 0 ? i : nav.length, 0, "reservas");
      // What the API adds to `/me` (043 §1, 045 §4).
      return {
        ...me,
        nav,
        client: { ...me.client, modules: [...me.client.modules, "reservas"] },
        reservas: { mode, capacity_kind: mode === "capacity" ? "restaurant" : null },
        business: { timezone: TZ, hours: null, hours_label: config.hoursLabel },
      };
    },

    notices: () => read(() => ({ ...notices, kinds: [...notices.kinds] })),
    setNotices: (body) =>
      write(() => {
        notices = { kinds: body.kinds ?? notices.kinds, quiet_outside_hours: body.quiet_outside_hours ?? notices.quiet_outside_hours };
        return { ...notices };
      }),

    nextFor(name) {
      const n = now();
      for (let d = n.date; d <= addDays(n.date, 30); d = addDays(d, 1)) {
        const x = day(d).find((r) => r.customer.name === name && (r.state === "pending" || r.state === "confirmed") && (d > n.date || r.start > n.minutes));
        if (x) {
          const label = x.service && x.pro ? `${x.service.name} con ${x.pro.name.split(" ")[0]}` : `${x.partySize ?? 0} comensales`;
          return { id: x.id, date: x.date, start: hhmm(x.start), label };
        }
      }
      return null;
    },

    config: () => read(() => clone(config)),
    range: (from, to) => read(() => ({ items: datesBetween(from, to).flatMap((d) => day(d)).map(view), now: clock })),
    booking: (id) => read(() => view(find(id))),
    occupancy: (from, to) =>
      read(() => {
        const dates = datesBetween(from, to);
        return { slots: config.mode === "capacity" ? dates.flatMap(slotsOf) : [], days: dates.map(dayPct) };
      }),
    freeSlots: ({ date, serviceId, proId, partySize }) =>
      read(() => (config.mode === "services" ? freeServices(date, serviceId, proId) : freeCapacity(date, partySize ?? 2))),

    create: (b: NewReservation, key) =>
      write(() => {
        const seen = keys.get(key);
        if (seen) return view(seen);
        if (isClosed(config, b.date)) throw new ApiError(422, "closed");
        let res: Reservation;
        if (config.mode === "services") {
          const svc = config.services?.catalog.find((c) => c.id === b.serviceId);
          const slot = freeServices(b.date, b.serviceId, b.proId).find((s) => s.time === b.time);
          if (!svc || !slot?.pro) throw new ApiError(409, "slot_taken");
          res = make(rng(key), b.date, b.time, b.time + svc.durationMin, {
            service: { id: svc.id, name: svc.name, durationMin: svc.durationMin, price: svc.price },
            pro: slot.pro,
          });
        } else {
          const party = b.partySize ?? 2;
          const slot = freeCapacity(b.date, party).find((s) => s.time === b.time);
          if (!slot || slot.full) throw new ApiError(409, "slot_taken");
          res = make(rng(key), b.date, b.time, b.time + (config.capacity?.stayMin ?? 90), { partySize: party });
        }
        res.customer = { name: b.customer.name, phone: b.customer.phone };
        res.origin = "person";
        res.channel = "phone";
        res.by = ME;
        res.state = "confirmed";
        res.createdAt = new Date().toISOString();
        res.events = [
          { kind: "created", at: res.createdAt, actor: ME, data: { channel: "phone", origin: "person" } },
          ...(b.customer.phone ? [{ kind: "notified", at: res.createdAt, actor: null, data: {} }] : []),
        ];
        day(b.date).push(res);
        day(b.date).sort((a, c) => a.start - c.start);
        keys.set(key, res);
        return view(res);
      }),

    act: (r, action) =>
      write(() => {
        const x = find(r.id);
        if (r.version !== x.version) throw new ApiError(412, "stale");
        if (!allowed(x).includes(action)) throw new ApiError(409, "invalid_transition");
        const stamp = new Date().toISOString();
        x.version += 1;
        if (action === "confirm") {
          x.state = "confirmed";
          x.events.push({ kind: "confirmed", at: stamp, actor: ME, data: {} });
        } else if (action === "arrived") {
          x.state = "arrived";
          x.arrivedAt = at(x.date, now().minutes);
          x.arrivedLocal = hhmm(now().minutes);
          x.events.push({ kind: "arrived", at: stamp, actor: ME, data: {} });
        } else if (action === "noshow") {
          x.state = "noshow";
          x.events.push({ kind: "noshow", at: stamp, actor: ME, data: {} });
        } else if (action === "undo") {
          x.state = "confirmed";
          x.arrivedAt = null;
          x.arrivedLocal = null;
          x.events.push({ kind: "undone", at: stamp, actor: ME, data: {} });
        } else {
          x.state = "cancelled";
          x.events.push({ kind: "cancelled", at: stamp, actor: ME, data: { by: "business" } });
          if (x.customer.phone) x.events.push({ kind: "notified", at: stamp, actor: null, data: {} });
        }
        return view(x);
      }),

    walkIn: (b, key) =>
      write(() => {
        const seen = keys.get(key);
        if (seen) return view(seen);
        const n = now();
        const slot = currentSlot(config, n.date, n.minutes);
        if (slot === null) throw new ApiError(422, "closed");
        const cap = config.capacity!;
        const inside = Math.max(...slotsOf(n.date).filter((s) => s.time >= slot && s.time < slot + cap.stayMin).map((s) => s.inside), 0);
        if (inside + b.partySize > cap.capacity) throw new ApiError(409, "no_room");
        const res = walkin(n.date, slot, b.partySize, b.name?.trim() ?? "");
        res.arrivedAt = at(n.date, n.minutes);
        res.arrivedLocal = hhmm(n.minutes);
        day(n.date).push(res);
        keys.set(key, res);
        return view(res);
      }),

    waitlist: () => read(() => waitlist.map((w) => ({ ...w, wants: { ...w.wants } }))),
    joinWaitlist: (b) =>
      write(() => {
        const entry: WaitEntry = {
          id: `w-${seq++}`,
          name: b.name?.trim() || "Sin nombre",
          phone: null,
          wants: { date: b.date, time: b.time, partySize: b.partySize, service: null, pro: null, text: null },
          state: "waiting",
          fits: false,
          offeredUntil: null,
          joinedBy: "person",
          by: ME,
          joinedAt: new Date().toISOString(),
        };
        waitlist = [...waitlist, entry];
      }),
    offer: (id) =>
      write(() => {
        const w = waitlist.find((x) => x.id === id);
        if (!w) throw new ApiError(404, "not_found");
        if (w.fits === false) throw new ApiError(409, "no_room");
        const next: WaitEntry = { ...w, state: "offered", offeredUntil: new Date(Date.now() + 15 * 60_000).toISOString() };
        waitlist = waitlist.map((x) => (x.id === id ? next : x));
      }),
    removeWait: (id) =>
      write(() => {
        waitlist = waitlist.filter((x) => x.id !== id);
      }),

    patchConfig: (b: ConfigPatch, version) =>
      write(() => {
        if (version !== config.version) throw new ApiError(412, "stale");
        config = {
          ...config,
          version: config.version + 1,
          waitlist: { ...config.waitlist, ...b.waitlist },
          confirmation: { ...config.confirmation, ...b.confirmation },
          capacity: config.capacity ? { ...config.capacity, ...b.capacity } : null,
        };
        return clone(config);
      }),
    block: (b) =>
      write(() => {
        if (!b.reason.trim()) throw new ApiError(422, "reason_required");
        const shift = config.capacity?.shifts.find((s) => s.from === b.from)?.name ?? null;
        const block: Block = { id: `b-${seq++}`, date: b.date, from: b.from, until: b.until, shift, reason: b.reason.trim() };
        if (config.capacity) config = { ...config, capacity: { ...config.capacity, blocks: [...config.capacity.blocks, block] } };
      }),
    unblock: (id) =>
      write(() => {
        if (config.capacity) config = { ...config, capacity: { ...config.capacity, blocks: config.capacity.blocks.filter((b) => b.id !== id) } };
      }),
  };
  return demo;
}
