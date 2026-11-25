import type { components } from "../schema.gen";

type S = components["schemas"];

/**
 * The example business (spec 069, Requisito 23.3): «Clínica Brisa», a dental
 * clinic answered by «Ava», used by «Camila Rojas». Everyone here is made up:
 * the phones are `+34 600 000 0xx`, the emails end in `.test`. The people and
 * the texts follow the approved design (KB `research/2026-11-21-app-movil-a-tiendas`,
 * inventory B §3.9 and A §2.4); times are relative to when the example starts,
 * so «hace 12 min» reads the same at any hour.
 */

/** A UUID-shaped id (the deep links and the API's ids are UUIDs): `c0000000-0000-4000-8000-00000000000e`. */
export const uuid = (prefix: string, n: number): string => `${prefix}0000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;

export const AGENT = { id: uuid("e", 1), name: "Ava" } as const;
export const BUSINESS = "Clínica Brisa";
export const USER = { name: "Camila Rojas", email: "camila@clinicabrisa.test" } as const;
export const PHONE_ID = uuid("f", 1);
export const TIMEZONE = "Europe/Madrid";

/** The modules as `/me.nav` names them (`lib/modules.ts`): Inicio is `panel`. */
export const NAV = ["panel", "inbox", "reservas", "usage"] as const;
export const CHANNELS = ["whatsapp", "instagram", "messenger"] as const;
export type ChannelKind = (typeof CHANNELS)[number];

export const HOURS: Record<string, { from: string; to: string }[]> = {
  monday: [{ from: "09:00", to: "20:00" }],
  tuesday: [{ from: "09:00", to: "20:00" }],
  wednesday: [{ from: "09:00", to: "20:00" }],
  thursday: [{ from: "09:00", to: "20:00" }],
  friday: [{ from: "09:00", to: "20:00" }],
  saturday: [{ from: "10:00", to: "14:00" }],
};
export const HOURS_LABEL = "lunes a viernes 9:00–20:00, sábado 10:00–14:00";

// ── money ─────────────────────────────────────────────────────────────

export type Currency = "USD" | "EUR" | "CLP";

/** `EXPO_PUBLIC_DEMO_CURRENCY` (EUR or CLP), read literally so Expo inlines it; US$ otherwise. */
export function demoCurrency(): Currency {
  const v = process.env.EXPO_PUBLIC_DEMO_CURRENCY;
  return v === "EUR" || v === "CLP" ? v : "USD";
}

const RATE: Record<Currency, number> = { USD: 1, EUR: 0.92, CLP: 940 };

/**
 * An amount given in US cents, in `c`'s hundredths — the API's `*_cents`,
 * which `formatMoney` divides by 100 whatever the currency. CLP has no cents:
 * whole pesos (×100).
 */
export function money(usdCents: number, c: Currency): number {
  const v = usdCents * RATE[c];
  return c === "CLP" ? Math.round(v / 100) * 100 : Math.round(v);
}

/** The balance (US$23.91), the bag it came in (US$50) and how long it lasts (about four months). */
export const BALANCE_USD_CENTS = 2391;
export const CAP_USD_CENTS = 5000;
export const DAYS_LEFT = 120;
/** This month's spend (US$4.21) over its conversations (8), as the design says them. */
export const MONTH_USD_CENTS = 421;
export const MONTH_CONVERSATIONS = 8;
/** The previous seven days' conversations, for the trend on Inicio. */
export const PREV_7D = 7;

/** A wall date of this phone, `YYYY-MM-DD`. */
export function localDate(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** `n` days before `ms`, at the same wall time. */
export function daysBefore(ms: number, n: number): number {
  const d = new Date(ms);
  d.setDate(d.getDate() - n);
  return d.getTime();
}

/**
 * Ninety days of spend, in US cents, oldest first: a few days with spend, and
 * this month's adding up to exactly `MONTH_USD_CENTS` whatever day it is.
 */
export function spendSeries(now: number): { days: string[]; usdCents: number[] } {
  const today = new Date(now);
  const month = today.getMonth();
  const days: string[] = [];
  const usdCents: number[] = [];
  for (let i = 89; i >= 0; i--) {
    days.push(localDate(daysBefore(now, i)));
    usdCents.push(0);
  }
  // Older months: a handful of quiet days.
  for (const [ago, cents] of [
    [83, 46],
    [76, 92],
    [69, 38],
    [61, 75],
    [54, 120],
    [47, 64],
    [40, 88],
    [33, 52],
  ] as const) {
    if (new Date(daysBefore(now, ago)).getMonth() !== month) usdCents[89 - ago] = cents;
  }
  // This month: up to six days that exist in it, weighted, with the rounding left on today.
  const candidates = [0, 2, 5, 9, 14, 20].filter((ago) => new Date(daysBefore(now, ago)).getMonth() === month);
  const weights = [3, 2, 4, 1, 3, 2].slice(0, candidates.length);
  const total = weights.reduce((a, b) => a + b, 0);
  let left = MONTH_USD_CENTS;
  candidates.forEach((ago, i) => {
    if (i === 0) return;
    const share = Math.floor((MONTH_USD_CENTS * (weights[i] ?? 0)) / total);
    usdCents[89 - ago] = share;
    left -= share;
  });
  usdCents[89] = left;
  return { days, usdCents };
}

// ── the inbox ─────────────────────────────────────────────────────────

export type DemoKey =
  | "lucia"
  | "sofia"
  | "diego"
  | "valentina"
  | "marta"
  | "andres"
  | "pedro"
  | "jorge"
  | "carmen"
  | "elena"
  | "pablo"
  | "ana"
  | "laura"
  | "nuria";

const KEYS: readonly DemoKey[] = ["lucia", "sofia", "diego", "valentina", "marta", "andres", "pedro", "jorge", "carmen", "elena", "pablo", "ana", "laura", "nuria"];

/** Every example conversation's id, by name: for deep links (`auphere-customers://inbox/<id>`) and screenshots. */
export const CONVERSATION_IDS = Object.fromEntries(KEYS.map((k, i) => [k, uuid("c", i + 1)])) as Record<DemoKey, string>;

export type Media = { kind: "image" | "document" | "audio"; filename: string | null; transcript: string | null };
export type EventKind = "escalated" | "takeover" | "released" | "resolved" | "reopened";
export type Who = "contact" | "agent" | "me" | "system";

export type Line =
  | {
      at: number;
      from: "contact" | "agent" | "me";
      text?: string;
      media?: Media;
      delivery?: "sent" | "delivered" | "read" | "failed";
      failure?: string;
      /** A comment under a post (Instagram), with the post it is under. */
      comment?: boolean;
      post?: S["CommentPostOut"];
    }
  | { at: number; event: EventKind; by: Who; detail?: string };

export type Seed = {
  key: DemoKey;
  name: string;
  handle: string;
  channel: ChannelKind;
  state: "agent" | "waiting" | "person" | "resolved";
  unread?: boolean;
  tags?: string[];
  note?: string;
  summary?: string;
  /** Why it waits: the code (`events.md` §2) and the agent's own words. */
  waiting?: { code: string; reason: string };
  /** The contact's past with the business: how many conversations, since how many days. */
  history: { conversations: number; firstDaysAgo: number };
  lines: Line[];
};

export const LUCIA_REASON = "Pide que le devuelvan la seña de 20 dólares. Ava no puede hacer devoluciones.";
/** The one who waits for a person; Reservas' example has her next booking too. */
export const LUCIA = { name: "Lucía Fernández", handle: "+34 600 000 001" } as const;

/** The thirteen conversations the example starts with (inventory B §3.9: today 3, yesterday 3, this week 3, older 4). */
export function seeds(now: number): Seed[] {
  const min = (m: number) => now - m * 60_000;
  const day = (ago: number, h: number, m = 0) => {
    const d = new Date(daysBefore(now, ago));
    d.setHours(h, m, 0, 0);
    return d.getTime();
  };
  return [
    {
      key: "lucia",
      name: LUCIA.name,
      handle: LUCIA.handle,
      channel: "whatsapp",
      state: "waiting",
      unread: true,
      waiting: { code: "escalated", reason: LUCIA_REASON },
      summary: "Quiere cancelar su blanqueamiento y que le devuelvan la seña de 20 dólares.",
      history: { conversations: 3, firstDaysAgo: 128 },
      lines: [
        { at: min(41), from: "contact", text: "Hola, buenos días. El martes pagué una seña de 20 dólares para el blanqueamiento, pero al final no voy a poder ir." },
        { at: min(40), from: "agent", text: "Hola, Lucía. Siento que no puedas venir. ¿Quieres que te busque otro día para el blanqueamiento?", delivery: "read" },
        { at: min(31), from: "contact", text: "No, prefiero cancelarla. ¿Me podéis devolver la seña?" },
        { at: min(30), from: "contact", text: "Os paso el justificante", media: { kind: "image", filename: "justificante-pago.jpg", transcript: null } },
        {
          at: min(13),
          from: "agent",
          text: "Las devoluciones las gestiona el equipo de la clínica. Le paso tu mensaje a una persona para que te responda lo antes posible.",
          delivery: "read",
        },
        { at: min(12), event: "escalated", by: "agent", detail: LUCIA_REASON },
      ],
    },
    {
      key: "sofia",
      name: "Sofía Herrera",
      handle: "@sofi.herrera",
      channel: "instagram",
      state: "person",
      unread: true,
      history: { conversations: 1, firstDaysAgo: 0 },
      lines: [
        { at: min(96), from: "contact", text: "¡Hola! Quería pedir cita para una limpieza dental." },
        { at: min(95), from: "agent", text: "¡Hola, Sofía! Tengo hueco el viernes a las 10:00 o a las 12:30. ¿Cuál te viene mejor?", delivery: "read" },
        { at: min(90), from: "contact", text: "El viernes a las 12:30, perfecto." },
        { at: min(89), from: "agent", text: "Hecho: viernes a las 12:30, limpieza dental con la Dra. Molina. Te llegará un recordatorio el día antes.", delivery: "read" },
        { at: min(84), event: "takeover", by: "me" },
        { at: min(83), from: "me", text: "Hola, Sofía, soy Camila, de la clínica. Te confirmo la cita; tenemos aparcamiento gratuito en la puerta.", delivery: "read" },
        { at: min(74), from: "contact", text: "¿Puedo llevar a mi hijo también? Tiene 8 años" },
      ],
    },
    {
      key: "diego",
      name: "Diego Ramírez",
      handle: "+34 600 000 002",
      channel: "whatsapp",
      state: "agent",
      tags: ["Primera visita", "Ortodoncia"],
      note: "Prefiere las citas por la tarde. Viene acompañado de su madre.",
      summary: "Pide información sobre ortodoncia invisible; valoración el jueves a las 16:30 con el Dr. Ruiz.",
      history: { conversations: 2, firstDaysAgo: 41 },
      lines: [
        { at: min(58), from: "contact", text: "Buenas, quería información sobre la ortodoncia invisible." },
        {
          at: min(57),
          from: "agent",
          text: "¡Hola, Diego! La primera visita de valoración es gratuita e incluye la radiografía. ¿Te viene bien el jueves por la tarde?",
          delivery: "read",
        },
        { at: min(52), from: "contact", text: "Sí, el jueves a partir de las 16:00." },
        { at: min(50), from: "agent", text: "Listo: jueves a las 16:30 con el Dr. Ruiz. Estamos en la calle de los Almendros 8. ¡Hasta el jueves!", delivery: "read" },
      ],
    },
    {
      key: "valentina",
      name: "Valentina Muñoz",
      handle: "Valentina Muñoz",
      channel: "messenger",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 1 },
      lines: [
        {
          at: day(1, 18, 2),
          from: "contact",
          media: { kind: "audio", filename: null, transcript: "Hola, quería saber cuánto cuesta una endodoncia, que me han dicho que necesito una." },
        },
        { at: day(1, 18, 3), from: "agent", text: "Hola, Valentina. La endodoncia cuesta entre 180 y 250 dólares según la pieza. Si quieres, te doy cita para valorarla.", delivery: "read" },
        { at: day(1, 18, 9), from: "contact", text: "Lo pienso y te digo." },
        { at: day(1, 18, 10), from: "agent", text: "¡Claro! Aquí estoy cuando lo decidas.", delivery: "read" },
      ],
    },
    {
      key: "marta",
      name: "Marta Gil",
      handle: "@marta.gil",
      channel: "instagram",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 1 },
      lines: [
        {
          at: day(1, 12, 15),
          from: "contact",
          text: "¿Cuánto cuesta el blanqueamiento?",
          comment: true,
          post: {
            text: "Blanqueamiento dental en una sola sesión. Pide tu cita por mensaje.",
            permalink: "https://instagram.test/p/clinica-brisa-blanqueamiento",
            image_url: null,
          },
        },
        { at: day(1, 12, 16), from: "agent", text: "¡Hola, Marta! Te escribimos por privado con los precios.", comment: true, delivery: "sent" },
        { at: day(1, 12, 16), from: "agent", text: "El blanqueamiento cuesta 290 dólares e incluye la revisión. ¿Quieres que te busque cita?", delivery: "read" },
        { at: day(1, 12, 40), from: "contact", text: "Gracias, lo miro con calma." },
        { at: day(1, 12, 41), from: "agent", text: "¡Perfecto! Cualquier duda, me escribes por aquí.", delivery: "read" },
      ],
    },
    {
      key: "andres",
      name: "Andrés Lara",
      handle: "Andrés Lara",
      channel: "messenger",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 1 },
      lines: [
        { at: day(1, 10, 30), from: "contact", text: "¿Abrís los sábados?" },
        {
          at: day(1, 10, 31),
          from: "agent",
          text: "Sí, los sábados de 10:00 a 14:00. ¿Te busco hueco?",
          delivery: "failed",
          failure: "el contacto ya no admite mensajes de esta página",
        },
      ],
    },
    {
      key: "pedro",
      name: "Pedro Alarcón",
      handle: "+34 600 000 003",
      channel: "whatsapp",
      state: "resolved",
      history: { conversations: 4, firstDaysAgo: 210 },
      lines: [
        { at: day(2, 17, 5), from: "contact", text: "¿Me confirmáis la cita de mañana a las 11?" },
        { at: day(2, 17, 6), from: "agent", text: "Confirmada, Pedro: mañana a las 11:00 con la Dra. Molina.", delivery: "read" },
        { at: day(2, 17, 8), from: "contact", text: "¡Gracias!" },
        { at: day(2, 17, 8), from: "agent", text: "¡Gracias a ti, Pedro! Que te vaya muy bien.", delivery: "read" },
        { at: day(2, 17, 30), event: "resolved", by: "me" },
      ],
    },
    {
      key: "jorge",
      name: "Jorge Vidal",
      handle: "+34 600 000 004",
      channel: "whatsapp",
      state: "agent",
      history: { conversations: 2, firstDaysAgo: 64 },
      lines: [
        { at: day(3, 11, 20), from: "contact", text: "Hola, ¿hacéis empastes sin cita?" },
        {
          at: day(3, 11, 21),
          from: "agent",
          text: "Hola, Jorge. Atendemos urgencias sin cita, pero para un empaste es mejor reservar. ¿Te busco hueco esta semana?",
          delivery: "read",
        },
        { at: day(3, 11, 40), from: "contact", text: "Vale, mañana te digo." },
      ],
    },
    {
      key: "carmen",
      name: "Carmen Ortiz",
      handle: "@carmen.ortiz",
      channel: "instagram",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 4 },
      lines: [
        { at: day(4, 16, 0), from: "contact", text: "¿Trabajáis con seguros dentales?" },
        { at: day(4, 16, 1), from: "agent", text: "Sí, con los principales. Dime cuál tienes y te confirmo la cobertura.", delivery: "read" },
      ],
    },
    {
      key: "elena",
      name: "Elena Castro",
      handle: "Elena Castro",
      channel: "messenger",
      state: "resolved",
      history: { conversations: 2, firstDaysAgo: 95 },
      lines: [
        { at: day(9, 9, 45), from: "contact", text: "Quería cambiar mi cita del lunes." },
        { at: day(9, 9, 46), from: "agent", text: "Hecho, Elena: la pasamos al miércoles a las 17:00.", delivery: "read" },
        { at: day(9, 10, 30), event: "resolved", by: "agent" },
      ],
    },
    {
      key: "pablo",
      name: "Pablo Díaz",
      handle: "+34 600 000 005",
      channel: "whatsapp",
      state: "agent",
      history: { conversations: 3, firstDaysAgo: 150 },
      lines: [
        { at: day(10, 13, 10), from: "contact", text: "Os mando el informe que me pidió el doctor.", media: { kind: "document", filename: "informe-radiografia.pdf", transcript: null } },
        { at: day(10, 13, 11), from: "agent", text: "Recibido, Pablo. El doctor lo verá antes de tu cita.", delivery: "read" },
      ],
    },
    {
      key: "ana",
      name: "Ana Ruiz",
      handle: "@ana.ruiz",
      channel: "instagram",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 13 },
      lines: [
        { at: day(13, 19, 5), from: "contact", text: "¿Tenéis cita para niños?" },
        { at: day(13, 19, 6), from: "agent", text: "Sí, la Dra. Molina atiende odontopediatría los martes y los jueves.", delivery: "read" },
      ],
    },
    {
      key: "laura",
      name: "Laura Vega",
      handle: "Laura Vega",
      channel: "messenger",
      state: "agent",
      history: { conversations: 1, firstDaysAgo: 18 },
      lines: [
        { at: day(18, 12, 0), from: "contact", text: "¿Cuál es el horario en agosto?" },
        { at: day(18, 12, 1), from: "agent", text: "En agosto abrimos de lunes a viernes, de 9:00 a 15:00.", delivery: "read" },
      ],
    },
  ];
}

/** The one that arrives while the app is open (inventory B §3.9: Nuria, at 3.2 s). */
export function nuriaSeed(now: number): Seed {
  return {
    key: "nuria",
    name: "Nuria Campos",
    handle: "@nuria.campos",
    channel: "instagram",
    state: "agent",
    unread: true,
    history: { conversations: 1, firstDaysAgo: 0 },
    lines: [
      { at: now - 20_000, from: "contact", text: "Hola, ¿atienden urgencias hoy? Me duele una muela" },
      {
        at: now,
        from: "agent",
        text: "Hola, Nuria, siento que te duela. Sí, hoy atendemos urgencias: tengo hueco a las 17:30. ¿Te lo reservo?",
        delivery: "delivered",
      },
    ],
  };
}

export const SUGGESTED_TAGS = ["Primera visita", "Ortodoncia", "Urgencia", "Presupuesto", "Seguro dental"];

export const REPLIES: S["ReplyOut"][] = [
  { id: uuid("b", 1), title: "Horario", body: "Abrimos de lunes a viernes de 9:00 a 20:00 y los sábados de 10:00 a 14:00." },
  { id: uuid("b", 2), title: "Ubicación", body: "Estamos en la calle de los Almendros 8, con aparcamiento gratuito en la puerta." },
  { id: uuid("b", 3), title: "Devoluciones", body: "Te devolvemos la seña en 3 a 5 días hábiles, por el mismo medio con el que pagaste." },
];

/** What this phone is told about at first (`notices.ts`): everything but the waitlist. */
export const NOTICE_KINDS = ["inbox.waiting", "inbox.message_for_you", "client.balance", "reservas.agent_change", "reservas.cancelled_today", "agents.state"];
