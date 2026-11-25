import { act, fireEvent, render, screen, within } from "@testing-library/react-native";
import { AccessibilityInfo, StyleSheet } from "react-native";

import type { Conversation, Counts, Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import { CALM_MS } from "@/features/home/model";
import type { InboxPeek } from "@/features/home/reads";
import type { TodayReservas } from "@/features/home/today-reservas";
import { t as translate, type MessageKey } from "@/i18n/t";
import { tokens } from "@/theme/tokens.gen";

import { capacityConfig, corte, javiera, marcos, peinado, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

/**
 * Spec 069, Historia 1, Requisito 8 (T030): Inicio fits one screen — the
 * business and who answers, four tiles that open their tab, the latest of the
 * Bandeja, and at the bottom whoever waits, or the calm card once.
 */
// The photo comes with the phone's credential (the Bandeja's hook); here, a plain source when the API has one.
jest.mock("@/api/v13-bandeja-hooks", () => ({ useAvatarSource: (id: string, has: boolean) => (has ? { uri: `photo-${id}` } : null) }));

const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
const NOW = new Date("2026-10-08T12:00:00Z");
const ALL = ["panel", "inbox", "reservas", "usage"];

function home(o: Partial<Home> = {}): Home {
  return {
    spend_month: { total_cents: 1626, currency: "USD", by_agent: null },
    conversations: { last_7d: 75, prev_7d: null, daily: [] },
    waiting: { count: 0, first_conversation_id: null },
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11, month_days_left: 24, currency: "USD" },
    attention: [],
    errors: [],
    ...o,
  } as Home;
}

const me = (nav: string[] = ALL, agents = [{ id: "a1", name: "Recepción" }]) =>
  ({ client: { name: "Flor y Encanto", modules: nav }, nav, agents, channels: [], balance_contact: { kind: "partner", name: "Amacrux" } }) as unknown as Me;

let seq = 0;
function conv(o: Partial<Conversation> & { name?: string; preview?: string; author?: "contact" | "agent" | "me" } = {}): Conversation {
  seq += 1;
  const { name = `Contacto ${seq}`, preview = "Hola", author = "contact", ...rest } = o;
  return {
    id: `c-${seq}`,
    state: "agent",
    assignee: null,
    unread: false,
    tags: [],
    agent: null,
    channel: { kind: "whatsapp" },
    contact: { name, handle: "+56 9 1234 5678", initials: "", has_avatar: false },
    last_message: {
      at: "2026-10-08T11:00:00Z",
      preview,
      has_media: false,
      author: author === "me" ? { kind: "member", is_me: true, name: "Valeria" } : author === "agent" ? { kind: "agent", is_me: false } : { kind: "contact", is_me: false },
    },
    ...rest,
  } as Conversation;
}

const ready = (items: Conversation[]): InboxPeek => ({ state: "ready", items });

// The preset's Dimensions say `fontScale: 2`; the default text size here is the phone's 1.
let dims: jest.SpyInstance;
beforeEach(() => {
  // `require`, not `import * as`: the namespace copy babel makes would not reach the module the screen reads.
  dims = jest.spyOn(require("react-native") as typeof import("react-native"), "useWindowDimensions").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
});
afterEach(() => dims.mockRestore());

const servicesToday: TodayReservas = {
  state: "ready",
  config: servicesConfig,
  now: { date: TODAY, minutes: 11 * 60 + 20 },
  waitlist: null,
  items: [
    res({ id: "a", start: 600, end: 630, service: corte, pro: marcos, state: "done" }),
    res({ id: "b", start: 690, end: 735, service: peinado, pro: javiera, state: "pending", customer: { name: "Camila Rojas", phone: null } }),
    res({ id: "c", start: 720, end: 750, service: corte, pro: marcos, customer: { name: "Tomás Silva", phone: null } }),
    res({ id: "d", start: 780, end: 810, service: corte, pro: marcos, state: "pending", customer: { name: "Isidora Morales", phone: null } }),
    res({ id: "e", start: 840, end: 870, service: corte, pro: marcos, customer: { name: "Joaquín Contreras", phone: null } }),
    res({ id: "x", start: 900, end: 930, service: corte, pro: marcos, state: "cancelled" }),
  ],
};

type P = {
  home?: Home | null;
  nav?: string[];
  agents?: { id: string; name: string }[];
  reservas?: TodayReservas | null;
  latest?: InboxPeek | null;
  waiting?: InboxPeek | null;
  counts?: Counts | null;
  focused?: boolean;
};

function element(p: P, fns: Record<string, jest.Mock>) {
  return (
    <HomeView
      me={me(p.nav, p.agents)}
      home={p.home === undefined ? home() : p.home}
      t={t}
      locale="es"
      now={NOW}
      onRetry={fns.onRetry!}
      onAttend={fns.onAttend!}
      onUsage={fns.onUsage!}
      onInbox={fns.onInbox!}
      reservas={p.reservas === undefined ? servicesToday : p.reservas}
      onReservas={fns.onReservas!}
      latest={p.latest === undefined ? ready([]) : p.latest}
      waiting={p.waiting === undefined ? ready([]) : p.waiting}
      counts={p.counts === undefined ? { unread: 2, waiting: 0 } : p.counts}
      onOpenConversation={fns.onOpen!}
      focused={p.focused ?? true}
    />
  );
}

async function view(p: P = {}) {
  const fns = { onRetry: jest.fn(), onAttend: jest.fn(), onUsage: jest.fn(), onInbox: jest.fn(), onReservas: jest.fn(), onOpen: jest.fn() };
  const r = await render(element(p, fns));
  return { ...fns, rerender: (next: P) => r.rerender(element(next, fns)) };
}

describe("the business and who answers (R8.1, R21.2)", () => {
  it("one agent: its name from `/me.agents`", async () => {
    await view();
    expect(screen.getByText("Flor y Encanto · Recepción atiende")).toBeTruthy();
  });

  it("several agents: how many, never a made-up name", async () => {
    await view({ agents: [{ id: "a1", name: "Recepción" }, { id: "a2", name: "Ventas" }] });
    expect(screen.getByText("Flor y Encanto · 2 agentes atienden")).toBeTruthy();
  });

  it("no agent: the business alone", async () => {
    await view({ agents: [] });
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
  });
});

describe("the four tiles (R8.1, R8.2)", () => {
  it("a long title that doesn't fit with large text breaks with a hyphen, and still scales («Conversaciones»)", async () => {
    await view({ reservas: servicesToday });
    const kicker = screen.getByText("Conversaciones");
    expect(kicker.props.android_hyphenationFrequency).toBe("normal");
    expect(kicker.props.adjustsFontSizeToFit).toBeUndefined();
  });

  it("Hoy, Conversaciones, Saldo and Este mes, each opening its tab", async () => {
    const { onReservas, onInbox, onUsage } = await view();
    for (const id of ["tile-today", "tile-conversations", "tile-balance", "tile-month"]) expect(screen.getByTestId(id)).toBeTruthy();
    await fireEvent.press(screen.getByTestId("tile-today"));
    expect(onReservas).toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId("tile-conversations"));
    expect(onInbox).toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId("tile-balance"));
    await fireEvent.press(screen.getByTestId("tile-month"));
    expect(onUsage).toHaveBeenCalledTimes(2);
  });

  it("Hoy wears the mint frame: the highlight's soft ground and its border (log, decision 2)", async () => {
    await view();
    const today = screen.getByTestId("tile-today");
    expect(within(today).getByTestId("tile-highlight")).toBeTruthy();
    expect(StyleSheet.flatten(within(today).getByTestId("tile-highlight").props.style).backgroundColor).toBe(tokens.light.highlightSoft);
    expect(StyleSheet.flatten(today.props.style).borderColor).toBe(tokens.light.highlight);
    expect(within(screen.getByTestId("tile-balance")).queryByTestId("tile-highlight")).toBeNull();
  });

  it("Escenario 3: without Reservas there is no Hoy, and the other three fill the space (two, then one across)", async () => {
    await view({ nav: ["panel", "inbox", "usage"], reservas: null });
    expect(screen.queryByTestId("tile-today")).toBeNull();
    const rows = screen.getByTestId("home-tiles").children as unknown as { props: { children: unknown[] } }[];
    expect(rows).toHaveLength(2);
    expect(within(screen.getByTestId("home-tiles")).getAllByRole("button")).toHaveLength(3);
  });

  it("without Consumo: no Saldo nor Este mes — and a balance in trouble is still said, with whom to ask (031 R4.1)", async () => {
    await view({ nav: ["panel", "inbox"], reservas: null, home: home({ attention: [{ kind: "balance_out", count: null, days_left: null }] }) });
    expect(screen.queryByTestId("tile-balance")).toBeNull();
    expect(screen.queryByTestId("tile-month")).toBeNull();
    expect(screen.getByText("Tu saldo se agotó y el agente no responde. Pide más saldo a Amacrux.")).toBeTruthy();
  });

  it("without the Bandeja: no Conversaciones tile, no list and nothing waiting", async () => {
    await view({ nav: ["panel", "usage"], reservas: null, latest: null, waiting: null, home: home({ waiting: null }) });
    expect(screen.queryByTestId("tile-conversations")).toBeNull();
    expect(screen.queryByText("Lo último en la Bandeja")).toBeNull();
    expect(screen.queryByRole("button", { name: /Atender/ })).toBeNull();
  });

  it("with large text, one tile per row (R1.7)", async () => {
    dims.mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 2 });
    await view();
    expect(screen.getByTestId("home-tiles").children).toHaveLength(4);
  });
});

describe("Hoy (R8.1)", () => {
  it("Servicios: today's bookings, the next one and the unconfirmed", async () => {
    await view();
    expect(within(screen.getByTestId("tile-today")).getByText("5 reservas")).toBeTruthy();
    expect(screen.getByText("Siguiente 11:30 · Camila")).toBeTruthy();
    expect(screen.getByText("2 sin confirmar")).toBeTruthy();
  });

  it("Aforo: who is inside now, who arrives and the waitlist", async () => {
    await view({
      reservas: {
        state: "ready",
        config: capacityConfig,
        now: { date: TODAY, minutes: 13 * 60 + 20 },
        waitlist: 2,
        items: [
          res({ id: "in", start: 780, end: 870, partySize: 4, state: "arrived" }),
          res({ id: "soon", start: 810, end: 900, partySize: 6, state: "confirmed", customer: { name: "Josefa Castillo", phone: null } }),
        ],
      },
    });
    expect(screen.getByText("4 de 64 dentro ahora")).toBeTruthy();
    expect(screen.getByText("Llegan 6 comensales en la próxima hora · 2 en lista de espera")).toBeTruthy();
  });

  it("no booking today says so, not a bare zero or «no more» (review H16)", async () => {
    await view({ reservas: { ...servicesToday, items: [] } as TodayReservas });
    expect(within(screen.getByTestId("tile-today")).getByText("0 reservas")).toBeTruthy();
    expect(screen.getByText("Sin reservas hoy")).toBeTruthy();
    expect(screen.queryByText("No quedan más hoy")).toBeNull();
  });

  it("with today's bookings all past, nothing left today", async () => {
    await view({ reservas: { ...servicesToday, now: { date: TODAY, minutes: 23 * 60 } } as TodayReservas });
    expect(screen.getByText("No quedan más hoy")).toBeTruthy();
  });

  it("loading and failing are said in the tile", async () => {
    await view({ reservas: { state: "loading" } });
    expect(screen.getByText("Cargando las reservas")).toBeTruthy();
    await view({ reservas: { state: "error", retry: jest.fn() } });
    expect(screen.getByText("No pudimos cargar las reservas.")).toBeTruthy();
  });
});

describe("Conversaciones, Saldo and Este mes (R8.1)", () => {
  it("Conversaciones: the API's 7 days and the unread from the Bandeja's counts", async () => {
    await view();
    expect(screen.getByLabelText("Conversaciones: 75 en 7 días. 2 sin leer")).toBeTruthy();
    await view({ counts: { unread: 0, waiting: 0 } });
    expect(screen.getByText("Nada sin leer")).toBeTruthy();
  });

  it("the week against the one before stays, under the unread (042 R5)", async () => {
    await view({ home: home({ conversations: { last_7d: 75, prev_7d: 60, daily: [] } }) });
    expect(screen.getByLabelText("Conversaciones: 75 en 7 días. 2 sin leer. 25 % más que los 7 días anteriores")).toBeTruthy();
  });

  it("a new business: words, never loose zeros", async () => {
    await view({
      home: home({ conversations: { last_7d: 0, prev_7d: null, daily: [] }, spend_month: { total_cents: 0, currency: "USD", by_agent: null } }),
      counts: { unread: 0, waiting: 0 },
      reservas: { ...servicesToday, items: [] } as TodayReservas,
    });
    expect(screen.getByText("Aún nadie escribió esta semana")).toBeTruthy();
    expect(screen.getByText("Sin gasto este mes")).toBeTruthy();
    expect(screen.getByText("Cuando alguien escriba a tu negocio, aquí verás sus últimas conversaciones.")).toBeTruthy();
  });

  it.each([
    [11, "Para unos 11 días"],
    [125, "Para unos 4 meses"],
    [1.4, "Para 1 día"],
    [0.4, "Para menos de un día"],
  ])("Saldo says how long it lasts: %s days → «%s»", async (days, line) => {
    await view({ home: home({ balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: days, month_days_left: 24, currency: "USD" } }) });
    expect(screen.getByText(line)).toBeTruthy();
  });

  it("Saldo in trouble: low says whom to ask; used up says the agent is silent; unassigned invents nothing", async () => {
    await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }], balance: { assigned: true, remaining_cents: 300, cap_cents: 5000, days_left: 4.6, month_days_left: 24, currency: "USD" } }) });
    expect(screen.getByText("Para unos 4 días")).toBeTruthy();
    expect(screen.getByText("Pide más saldo a Amacrux.")).toBeTruthy();
    await view({ home: home({ attention: [{ kind: "balance_out", count: null, days_left: null }], balance: { assigned: true, remaining_cents: 0, cap_cents: 5000, days_left: 0, month_days_left: 24, currency: "USD" } }) });
    expect(screen.getByText("Saldo agotado: el agente no responde")).toBeTruthy();
    await view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null, month_days_left: 24, currency: "USD" } }) });
    expect(screen.getByLabelText(/^Saldo: —\. Todavía no tienes un tope asignado/)).toBeTruthy();
    expect(screen.queryByText(/comprar|recargar/i)).toBeNull();
  });

  it("Este mes: the spend in the bag's currency, since the 1st", async () => {
    await view();
    expect(screen.getByLabelText(/^Este mes: 16,26\s*US\$\. Desde el 1 de octubre/)).toBeTruthy();
  });
});

describe("«Lo último en la Bandeja» (R8.3)", () => {
  const four = () => [
    conv({ name: "Sofía Pérez", unread: true, channel: { kind: "instagram" }, preview: "¿Tienen hora?", author: "contact" }),
    conv({ name: "Diego Ruiz", preview: "Te esperamos el jueves", author: "agent" }),
    conv({ name: "Ana Soto", state: "person", preview: "Listo", author: "me" }),
    conv({ name: "Resuelta", state: "resolved" }),
    conv({ name: "Pedro Gil" }),
    conv({ name: "Luis Mora" }),
  ];

  it("four rows when nobody waits — no resolved ones — with the channel and who wrote last", async () => {
    await view({ latest: ready(four()) });
    const list = screen.getByTestId("home-latest");
    expect(within(list).getAllByRole("button")).toHaveLength(4);
    expect(within(list).queryByText("Resuelta")).toBeNull();
    // The badge is decorative (the row's sentence names the person): hidden from assistive tech, present on screen.
    expect(within(list).getByTestId("avatar-channel-instagram", { includeHiddenElements: true })).toBeTruthy();
    expect(within(list).getByText("Recepción: Te esperamos el jueves")).toBeTruthy();
    expect(within(list).getByText("Tú: Listo")).toBeTruthy();
    expect(screen.getByLabelText("Sofía Pérez. Sin leer. ¿Tienen hora?")).toBeTruthy();
  });

  it("the contact's photo when the API has one, the initials otherwise", async () => {
    const withPhoto = conv({ name: "Sofía Pérez", channel: { kind: "instagram" } });
    withPhoto.contact.has_avatar = true;
    await view({ latest: ready([withPhoto, conv({ name: "Diego Ruiz" })]) });
    const list = screen.getByTestId("home-latest");
    expect(within(list).getAllByTestId("avatar-photo", { includeHiddenElements: true })).toHaveLength(1);
    expect(within(list).getByText("DR", { includeHiddenElements: true })).toBeTruthy();
  });

  it("two rows when someone waits, and the waiting one is not among them", async () => {
    const lucia = conv({ name: "Lucía Fernández", state: "waiting" });
    await view({ latest: ready([lucia, ...four()]), waiting: ready([lucia]), home: home({ waiting: { count: 1, first_conversation_id: lucia.id } }) });
    const list = screen.getByTestId("home-latest");
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    expect(within(list).queryByText("Lucía Fernández")).toBeNull();
  });

  it("a row opens its conversation (in the Bandeja's tab, decided by the screen)", async () => {
    const items = four();
    const { onOpen } = await view({ latest: ready(items) });
    await fireEvent.press(screen.getByTestId(`home-latest-${items[0]!.id}`));
    expect(onOpen).toHaveBeenCalledWith(items[0]!.id);
  });

  it("loading and failing are said in place, with «Reintentar»", async () => {
    await view({ latest: { state: "loading" } });
    expect(screen.getByRole("progressbar", { name: "Cargando la Bandeja" })).toBeTruthy();
    const retry = jest.fn();
    await view({ latest: { state: "error", retry } });
    expect(screen.getByText("No pudimos cargar la Bandeja.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalled();
  });
});

describe("whoever waits, at the bottom (R8.4)", () => {
  const since = new Date(NOW.getTime() - 12 * 60_000).toISOString();
  const lucia = conv({ name: "Lucía Fernández", state: "waiting", waiting: { reason: "Pide que le devuelvan la seña de 20 €.", since } });
  const other = conv({ name: "Otro Más", state: "waiting" });

  it("Escenario 1: the name, since when, the reason, «+N más» and «Atender a {nombre}»", async () => {
    const { onAttend } = await view({ waiting: ready([other, lucia]), home: home({ waiting: { count: 3, first_conversation_id: lucia.id } }) });
    const card = screen.getByTestId("home-waiting");
    expect(within(card).getByText("Espera a una persona · hace 12 min · +2 más")).toBeTruthy();
    expect(within(card).getByText("Lucía Fernández")).toBeTruthy();
    expect(within(card).getByText("Pide que le devuelvan la seña de 20 €.")).toBeTruthy();
    await fireEvent.press(within(card).getByRole("button", { name: "Atender a Lucía" }));
    expect(onAttend).toHaveBeenCalledWith(lucia.id);
  });

  it("a white card: amber only in its label and its icon tile (owner, 18 Nov)", async () => {
    await view({ waiting: ready([lucia]), home: home({ waiting: { count: 1, first_conversation_id: lucia.id } }) });
    const card = screen.getByTestId("home-waiting");
    expect(StyleSheet.flatten(card.props.style).backgroundColor).toBe(tokens.light.card);
    expect(StyleSheet.flatten(within(card).getByText("Espera a una persona · hace 12 min").props.style).color).toBe(tokens.light.warningText);
  });

  it("before the list arrives, the count and «Atender ahora», to the API's first one", async () => {
    const { onAttend } = await view({ waiting: { state: "loading" }, home: home({ waiting: { count: 1, first_conversation_id: "c-first" } }) });
    expect(screen.getByText("1 conversación espera a una persona")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Atender ahora" }));
    expect(onAttend).toHaveBeenCalledWith("c-first");
  });

  it("a reason given as a code is said in words, never as a code (spec 056, 7.1)", async () => {
    const coded = conv({ name: "Marta Gil", state: "waiting", waiting: { reason: "escalated", since } });
    await view({ waiting: ready([coded]), home: home({ waiting: { count: 1, first_conversation_id: coded.id } }) });
    expect(screen.queryByText("escalated")).toBeNull();
    expect(screen.getByText("El agente pidió ayuda")).toBeTruthy();
  });
});

describe("«Todo en orden» (R8.5, micro 8)", () => {
  const waitingHome = home({ waiting: { count: 1, first_conversation_id: "c-w" } });
  // A balance that reaches the month's end: the only one that lets the card say so.
  const lasting = { assigned: true, remaining_cents: 9000, cap_cents: 10000, days_left: 40, month_days_left: 24, currency: "USD" };
  const calmHome = home({ waiting: { count: 0, first_conversation_id: null }, balance: lasting });
  afterEach(() => {
    jest.useRealTimers();
    // The preset's own mock: put its answer back (a restore would leave it answering nothing).
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(false);
  });

  it("Escenario 2: once nobody waits, it appears once and leaves at 3,2 s", async () => {
    jest.useFakeTimers();
    const { rerender } = await view({ home: waitingHome });
    expect(screen.queryByText("Todo en orden")).toBeNull();
    await rerender({ home: calmHome });
    expect(screen.getByText("Todo en orden")).toBeTruthy();
    expect(screen.getByText("Nadie espera a una persona y el saldo alcanza para el mes.")).toBeTruthy();
    await act(async () => jest.advanceTimersByTime(CALM_MS - 1));
    expect(screen.getByText("Todo en orden")).toBeTruthy();
    await act(async () => jest.advanceTimersByTime(1));
    expect(screen.queryByText("Todo en orden")).toBeNull();
    // Once: another read with nobody waiting does not bring it back.
    await rerender({ home: home({ waiting: { count: 0, first_conversation_id: null } }) });
    expect(screen.queryByText("Todo en orden")).toBeNull();
  });

  it("with «Reducir movimiento» it stays the same 3,2 s: a wait is not an animation (R2.5)", async () => {
    const reduce = jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
    jest.useFakeTimers();
    const { rerender } = await view({ home: waitingHome });
    await act(async () => undefined);
    await rerender({ home: calmHome });
    await act(async () => jest.advanceTimersByTime(CALM_MS - 1));
    expect(screen.getByText("Todo en orden")).toBeTruthy();
    await act(async () => jest.advanceTimersByTime(1));
    expect(screen.queryByText("Todo en orden")).toBeNull();
    expect(reduce).toHaveBeenCalled();
  });

  it("a cold start with nobody waiting shows nothing at the bottom", async () => {
    await view({ home: calmHome });
    expect(screen.queryByText("Todo en orden")).toBeNull();
    expect(screen.queryByTestId("home-waiting")).toBeNull();
  });

  it("the last one attended while Inicio was in the background: it shows on coming back", async () => {
    const { rerender } = await view({ home: waitingHome });
    await rerender({ home: calmHome, focused: false });
    expect(screen.queryByText("Todo en orden")).toBeNull();
    await rerender({ home: calmHome, focused: true });
    expect(screen.getByText("Todo en orden")).toBeTruthy();
  });

  it("never over a balance in trouble; and without a balance it says only what is true", async () => {
    const { rerender } = await view({ home: waitingHome });
    await rerender({ home: home({ waiting: { count: 0, first_conversation_id: null }, attention: [{ kind: "balance_low", count: null, days_left: 3 }] }) });
    expect(screen.queryByText("Todo en orden")).toBeNull();

    const second = await view({ home: waitingHome });
    await second.rerender({ home: home({ waiting: { count: 0, first_conversation_id: null }, balance: null }) });
    expect(screen.getByText("Nadie espera a una persona.")).toBeTruthy();
  });

  it("an unknown count is not a zero", async () => {
    const { rerender } = await view({ home: waitingHome });
    await rerender({ home: null });
    expect(screen.queryByText("Todo en orden")).toBeNull();
  });
});
