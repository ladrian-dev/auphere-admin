import { fireEvent, render, screen, within } from "@testing-library/react-native";

import type { Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import type { TodayReservas } from "@/features/home/today-reservas";
import { t as translate, type MessageKey } from "@/i18n/t";

import { capacityConfig, corte, marcos, peinado, javiera, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

/**
 * Spec 031 (T063, R4.1, R4.4, R14.1): Inicio is the console's Panel, in each
 * of its states. Spec 042 (T028–T032, R5, R6.4, CE-001): it says each thing
 * once. Spec 069 (R8) amends 044 R9 and the blocks of 042 R5: the attention
 * block, the money group and the conversations card became the design's four
 * tiles and the card of whoever waits; each test below says what it checked
 * before when 069 changed it (`log.md`, «Tests existentes enmendados»).
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
const NOW = new Date("2026-10-08T12:00:00Z");
const days = ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"];

function home(o: Partial<Home> = {}): Home {
  return {
    spend_month: { total_cents: 1626, by_agent: null },
    conversations: { last_7d: 75, prev_7d: null, daily: days.map((day, i) => ({ day, count: [5, 21, 9, 7, 5, 12, 16][i]! })) },
    waiting: { count: 3, first_conversation_id: "c-2" },
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 11 },
    attention: [],
    errors: [],
    ...o,
  } as Home;
}

const me = (nav: string[] = ["panel", "inbox", "usage"]) =>
  ({ client: { name: "Flor y Encanto", modules: nav }, nav, balance_contact: { kind: "partner", name: "Amacrux" } }) as unknown as Me;

async function view(p: { home?: Home | null; nav?: string[]; reservas?: TodayReservas | null } = {}) {
  const onAttend = jest.fn();
  const onUsage = jest.fn();
  const onRetry = jest.fn();
  const onInbox = jest.fn();
  const onReservas = jest.fn();
  await render(
    <HomeView
      me={me(p.nav)}
      home={p.home === undefined ? home() : p.home}
      t={t}
      locale="es"
      now={NOW}
      onRetry={onRetry}
      onAttend={onAttend}
      onUsage={onUsage}
      onInbox={onInbox}
      reservas={p.reservas ?? null}
      onReservas={onReservas}
    />,
  );
  return { onAttend, onUsage, onRetry, onInbox, onReservas };
}

const nobodyWaits = { waiting: { count: 0, first_conversation_id: null } };

// 069 (R8.1): the figures are tiles now — the 7-day conversations and the month's spend, each with its words.
it("ideal: the client's figures, as the console shows them", async () => {
  await view();
  expect(screen.getByLabelText(/^Conversaciones: 75 en 7 días/)).toBeTruthy();
  expect(screen.getByLabelText(/^Este mes: .*16,26/)).toBeTruthy();
});

it("error: the whole read failed — an alert with a retry, no invented zeros", async () => {
  const { onRetry } = await view({ home: null });
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.queryByText("75")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Reintentar" }));
  expect(onRetry).toHaveBeenCalled();
});

// 069: «75» is a tile's figure with its unit («75 en 7 días»), so it is found by the tile's sentence.
it("partial: a block that failed is said, the rest shows", async () => {
  await view({ home: home({ errors: ["spend_month"], spend_month: null }) });
  expect(screen.getByText("Una parte del Panel no se pudo cargar. Recarga para intentarlo de nuevo.")).toBeTruthy();
  expect(screen.getByLabelText(/^Conversaciones: 75/)).toBeTruthy();
  expect(screen.queryByTestId("tile-month")).toBeNull();
});

// 069 (R8.4): whoever waits is the card at the bottom, not «Necesita tu atención»; «Atender» still opens the API's first one.
it("whoever waits is at the bottom, and «Atender» opens the waiting conversation", async () => {
  const { onAttend } = await view({ home: home({ attention: [{ kind: "waiting", count: 3, days_left: null }] }) });
  expect(screen.getByTestId("home-waiting")).toBeTruthy();
  expect(screen.queryByRole("header", { name: "Necesita tu atención" })).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: /^Atender/ }));
  expect(onAttend).toHaveBeenCalledWith("c-2");
});

describe("each thing once (spec 042, R5)", () => {
  // 069: the count is said once, in the waiting card («+1 más» is the rest of it).
  it("CE-001: with two conversations waiting, the number appears once, in the waiting card, and nowhere else", async () => {
    await view({
      home: home({ attention: [{ kind: "waiting", count: 2, days_left: null }], waiting: { count: 2, first_conversation_id: "c-2" } }),
    });
    expect(screen.getAllByText("2 conversaciones esperan a una persona")).toHaveLength(1);
    expect(screen.getAllByText(/\+1 más/)).toHaveLength(1);
    // Not the old «Esperan a una persona» metric, and no badge counting something else (H13).
    expect(screen.queryByText("Esperan a una persona")).toBeNull();
    expect(screen.queryByText(/^[12]$/)).toBeNull();
  });

  // 069 (R8.5): with nobody waiting from the start, the bottom is empty — the calm card only follows someone waiting.
  it("nothing pending is nothing at the bottom, never a zero", async () => {
    await view({ home: home(nobodyWaits) });
    expect(screen.queryByTestId("home-waiting")).toBeNull();
    expect(screen.queryByText(/esperan a una persona/i)).toBeNull();
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  // 069 (R8.1): the balance and the month are two tiles, each the way to Consumo; how long it lasts is the Saldo tile's words.
  it("money is two tiles: the balance with how long it lasts, the month's spend — each the way to Consumo", async () => {
    const { onUsage } = await view();
    expect(screen.getByLabelText(/^Saldo: .*30,13.*\. Para unos 11 días/)).toBeTruthy();
    expect(screen.getByLabelText(/^Este mes: .*16,26/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId("tile-balance"));
    await fireEvent.press(screen.getByTestId("tile-month"));
    expect(onUsage).toHaveBeenCalledTimes(2);
  });

  // 069 (R8.2): a module the client lacks has no tile — without Consumo there is nothing leading to it.
  it("without the Consumo module there is no tile into it and nothing to press towards it (R6.4, 069 R8.2)", async () => {
    const { onUsage } = await view({ nav: ["panel", "inbox"] });
    expect(screen.queryByTestId("tile-balance")).toBeNull();
    expect(screen.queryByTestId("tile-month")).toBeNull();
    for (const b of screen.queryAllByRole("button")) await fireEvent.press(b);
    expect(onUsage).not.toHaveBeenCalled();
  });

  // 069: the waiting card and the Saldo tile, each datum once; whom to ask once, in the tile.
  it("waiting and a low balance: the card and the tile, each datum once", async () => {
    await view({
      home: home({
        attention: [
          { kind: "waiting", count: 1, days_left: null },
          { kind: "balance_low", count: null, days_left: 4.6 },
        ],
        waiting: { count: 1, first_conversation_id: "c-2" },
        balance: { assigned: true, remaining_cents: 300, cap_cents: 5000, days_left: 4.6 } as Home["balance"],
      }),
    });
    expect(screen.getAllByText("1 conversación espera a una persona")).toHaveLength(1);
    expect(screen.getAllByText("Para unos 4 días")).toHaveLength(1);
    expect(screen.getAllByText("Pide más saldo a Amacrux.")).toHaveLength(1);
  });

  // 069: no «Ver consumo» row any more; the tiles are the ways in.
  it("no «Ver consumo» row: the tiles are the way into Consumo", async () => {
    await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }] }) });
    expect(screen.queryByRole("button", { name: "Ver consumo" })).toBeNull();
  });

  it("the waiting row says it once: no «Bandeja de entrada» label repeating the sentence next to it", async () => {
    await view({ home: home({ attention: [{ kind: "waiting", count: 2, days_left: null }], waiting: { count: 2, first_conversation_id: "c-2" } }) });
    expect(screen.queryByText("Bandeja de entrada")).toBeNull();
    expect(screen.getByText("2 conversaciones esperan a una persona")).toBeTruthy();
  });

  // 069: said by the Saldo tile.
  it("an unassigned balance says so, with no invented figures", async () => {
    await view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null, month_days_left: 24, currency: "USD" } }) });
    expect(screen.getByLabelText(/^Saldo: —\. Todavía no tienes un tope asignado/)).toBeTruthy();
    expect(screen.queryByText(/Cubre/)).toBeNull();
  });

  // 069 (R8.1): one tile with its figure and, without the Bandeja's counts, its trend; the bars left Inicio with the design.
  it("conversations are one figure with their trend, and no bars", async () => {
    await view({ home: home({ conversations: { last_7d: 75, prev_7d: 60, daily: days.map((day) => ({ day, count: 10 })) } }) });
    expect(screen.getByLabelText(/^Conversaciones: 75 en 7 días/)).toBeTruthy();
    expect(screen.getByText("25 % más que los 7 días anteriores")).toBeTruthy();
    expect(screen.queryByLabelText(/^Conversaciones por día de los últimos 7 días/)).toBeNull();
  });
});

// 069: said by the Saldo tile — how long, and whom to ask.
it("a short balance says for how long and whom to ask — with no buy button (R4.4)", async () => {
  await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }], balance: { assigned: true, remaining_cents: 300, cap_cents: 5000, days_left: 4.6 } as Home["balance"] }) });
  expect(screen.getByText("Para unos 4 días")).toBeTruthy();
  expect(screen.getByText("Pide más saldo a Amacrux.")).toBeTruthy();
  expect(screen.queryByText(/comprar|recargar/i)).toBeNull();
});

it("without the Bandeja there is no «waiting» action into it", async () => {
  await view({ nav: ["panel", "usage"], home: home({ waiting: null }) });
  expect(screen.queryByText(/esperan a una persona/i)).toBeNull();
  expect(screen.queryByRole("button", { name: /Atender/ })).toBeNull();
});

/**
 * Spec 044, Historia 5, Requisito 9: «Hoy en Reservas» — counted from the
 * same read as the Reservas tab (D4). Spec 069 (R8.1): it is the Hoy tile.
 */
describe("Inicio with Reservas (spec 044, R9; spec 069, R8.1)", () => {
  const nav = ["panel", "inbox", "reservas", "usage"];
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

  // 069: the unconfirmed are said in the Hoy tile, which opens Reservas (the attention block is gone).
  it("today's unconfirmed reservations are said in the Hoy tile, which opens Reservas", async () => {
    const { onReservas } = await view({ nav, reservas: servicesToday });
    expect(within(screen.getByTestId("tile-today")).getByText("2 sin confirmar")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("tile-today"));
    expect(onReservas).toHaveBeenCalled();
  });

  // 069: they no longer bring an attention block; with nobody waiting, nothing at the bottom.
  it("they do not invent anything waiting", async () => {
    await view({ nav, reservas: servicesToday, home: home(nobodyWaits) });
    expect(screen.queryByRole("header", { name: "Necesita tu atención" })).toBeNull();
    expect(screen.queryByTestId("home-waiting")).toBeNull();
  });

  // 069: today's count and the next one in the tile; the list of the next three left Inicio with the design.
  it("Hoy in Servicios: today's count and the next one", async () => {
    await view({ nav, reservas: servicesToday });
    expect(within(screen.getByTestId("tile-today")).getByText("5 reservas")).toBeTruthy();
    expect(screen.getByText("Siguiente 11:30 · Camila")).toBeTruthy();
    expect(screen.queryByText("Joaquín Contreras")).toBeNull();
  });

  // 069: the tile's figure keeps one line and fits itself; with large text the tiles go one per row (R1.7).
  it("with large text, the figure is never cut: it fits its line, and each tile takes the whole row", async () => {
    await view({ nav, reservas: servicesToday });
    const figure = within(screen.getByTestId("tile-today")).getByText("5 reservas");
    expect(figure.props.numberOfLines).toBe(1);
    expect(figure.props.adjustsFontSizeToFit).toBe(true);
    // Jest's Dimensions carry `fontScale: 2`: one tile per row.
    expect(screen.getByTestId("home-tiles").children).toHaveLength(4);
  });

  // 069: the same words, in the Hoy tile; the arriving guest's name left with the list.
  it("Hoy in Aforo: inside now, who arrives in the next hour and the waitlist", async () => {
    await view({
      nav,
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
    // At 13:20 the 13:00 table (4) is inside; the 13:30 one (6) is not yet.
    expect(screen.getByText("4 de 64 dentro ahora")).toBeTruthy();
    expect(screen.getByText("Llegan 6 comensales en la próxima hora · 2 en lista de espera")).toBeTruthy();
  });

  it("without the module there is no trace of Reservas", async () => {
    await view();
    expect(screen.queryByTestId("tile-today")).toBeNull();
    expect(screen.queryByText("Hoy en Reservas")).toBeNull();
    expect(screen.queryByText(/reservas de hoy/)).toBeNull();
  });

  it("loading and failing are said in place", async () => {
    await view({ nav, reservas: { state: "error", retry: () => undefined } });
    expect(screen.getByText("No pudimos cargar las reservas.")).toBeTruthy();
  });

  // 069: the Conversaciones tile is the way to the Bandeja.
  it("the conversations tile takes you to the Bandeja (R9.3, 069 R8.1)", async () => {
    const { onInbox } = await view({ nav });
    await fireEvent.press(screen.getByTestId("tile-conversations"));
    expect(onInbox).toHaveBeenCalled();
  });
});

/**
 * Spec 056 (requisito 2.6): «Agentes» and «Negocio» are no longer modules of
 * a client. Inicio draws neither, even when an older `/me` still names them.
 */
const mockNav = ["panel", "inbox", "agents", "business", "usage"];
const mockHome: { current: Home | undefined } = { current: undefined };
jest.mock("@/api/hooks", () => ({
  useMe: () => ({
    data: {
      user: { name: "Valeria Ríos" },
      client: { name: "Flor y Encanto", modules: mockNav },
      nav: mockNav,
      balance_contact: { kind: "partner", name: "Amacrux" },
      business: { timezone: "America/Santiago", hours: null, hours_label: "De lunes a viernes de 9:00 a 14:00" },
    },
  }),
  useHome: () => ({ data: mockHome.current, isError: false, dataUpdatedAt: 0, refetch: jest.fn(async () => undefined) }),
}));
// 069: Inicio reads the Bandeja through its own module (R8.3, R8.4).
jest.mock("@/features/home/reads", () => ({
  useHomeInbox: () => ({ latest: { state: "ready", items: [] }, waiting: { state: "ready", items: [] }, refetch: async () => undefined }),
  useHomeCounts: () => ({ data: { unread: 0, waiting: 0 }, refetch: async () => undefined }),
}));
// 069: the calm card compares what Inicio saw while in front (R8.5).
jest.mock("expo-router/react-navigation", () => ({ useIsFocused: () => true }));
jest.mock("@/api/reservas-hooks", () => ({
  useHasReservas: () => false,
  useReservasConfig: () => ({ data: undefined, isError: false, refetch: jest.fn() }),
  useBizToday: () => "2026-10-08",
  useReservasRange: () => ({ data: undefined, isError: false, refetch: jest.fn() }),
  useWaitlist: () => ({ data: undefined }),
  useBizNow: () => null,
}));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
jest.mock("expo-router", () => {
  // The settings bar button (spec 042, SettingsToolbar) renders nothing here.
  function Toolbar() {
    return null;
  }
  Toolbar.Button = function ToolbarButton() {
    return null;
  };
  return { router: { push: jest.fn(), navigate: jest.fn() }, Stack: { Screen: () => null, Toolbar } };
});

describe("no Agentes nor Negocio in Inicio (spec 056, 2.6)", () => {
  // 069: «75» is found by the Conversaciones tile's sentence.
  it("not even with `agents` and `business` in `/me.nav`", async () => {
    mockHome.current = home();
    const Inicio = require("@/app/(app)/inicio/index").default as () => React.JSX.Element;
    await render(<Inicio />);
    expect(screen.getByTestId("inicio")).toBeTruthy();
    expect(screen.getByLabelText(/^Conversaciones: 75/)).toBeTruthy();
    expect(screen.queryByText("Agentes")).toBeNull();
    expect(screen.queryByText("Recepción")).toBeNull();
    expect(screen.queryByTestId("home-business")).toBeNull();
    expect(screen.queryByText("Horario, servicios y sedes")).toBeNull();
  });

  // 069 (log, decision 3): one rule from Inicio — a conversation opens in the Bandeja's tab, then the conversation.
  it("«Atender» opens the conversation in the Bandeja's tab", async () => {
    const { router } = require("expo-router") as { router: { push: jest.Mock; navigate: jest.Mock } };
    router.push.mockClear();
    router.navigate.mockClear();
    mockHome.current = home({ waiting: { count: 1, first_conversation_id: "c-9" } });
    const Inicio = require("@/app/(app)/inicio/index").default as () => React.JSX.Element;
    await render(<Inicio />);
    await fireEvent.press(screen.getByRole("button", { name: "Atender ahora" }));
    expect(router.navigate).toHaveBeenCalledWith("/bandeja");
    expect(router.push).toHaveBeenCalledWith("/conversacion/c-9");
    expect(router.navigate.mock.invocationCallOrder[0]!).toBeLessThan(router.push.mock.invocationCallOrder[0]!);
  });
});
