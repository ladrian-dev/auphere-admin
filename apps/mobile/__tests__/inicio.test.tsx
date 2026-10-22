import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import type { Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import type { TodayReservas } from "@/features/home/today-reservas";
import { t as translate, type MessageKey } from "@/i18n/t";

import { capacityConfig, corte, marcos, peinado, javiera, res, servicesConfig, TODAY } from "../test/reservas-fixtures";

/**
 * Spec 031 (T063, R4.1, R4.4, R14.1): Inicio is the console's Panel, in each
 * of its states. Spec 042 (T028–T032, R5, R6.4, CE-001): it says each thing
 * once — one attention block, one money group, one conversations block.
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

it("ideal: the client's figures, as the console shows them", async () => {
  await view();
  expect(screen.getByText("75")).toBeTruthy();
  expect(screen.getByText("Últimos 7 días · sin semana anterior para comparar")).toBeTruthy();
  expect(screen.getByLabelText(/^Gasto del mes: .*16,26/)).toBeTruthy();
});

it("error: the whole read failed — an alert with a retry, no invented zeros", async () => {
  const { onRetry } = await view({ home: null });
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.queryByText("75")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Reintentar" }));
  expect(onRetry).toHaveBeenCalled();
});

it("partial: a block that failed is said, the rest shows", async () => {
  await view({ home: home({ errors: ["spend_month"], spend_month: null }) });
  expect(screen.getByText("Una parte del Panel no se pudo cargar. Recarga para intentarlo de nuevo.")).toBeTruthy();
  expect(screen.getByText("75")).toBeTruthy();
});

it("«Necesita tu atención» comes first, and «Atender» opens the waiting conversation", async () => {
  const { onAttend } = await view({ home: home({ attention: [{ kind: "waiting", count: 3, days_left: null }] }) });
  expect(screen.getByRole("header", { name: "Necesita tu atención" })).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: /^Atender/ }));
  expect(onAttend).toHaveBeenCalledWith("c-2");
});

describe("each thing once (spec 042, R5)", () => {
  it("CE-001: with two conversations waiting, the number appears once, in the attention block, and nowhere else", async () => {
    await view({
      home: home({ attention: [{ kind: "waiting", count: 2, days_left: null }], waiting: { count: 2, first_conversation_id: "c-2" } }),
    });
    expect(screen.getAllByText("2 conversaciones esperan a una persona")).toHaveLength(1);
    // Not the old «Esperan a una persona» metric, and no badge counting something else (H13).
    expect(screen.queryByText("Esperan a una persona")).toBeNull();
    expect(screen.queryByText(/^[12]$/)).toBeNull();
  });

  it("nothing pending is one calm line, never a zero", async () => {
    await view();
    expect(screen.getByText("Todo en orden. Nada espera a una persona y el saldo alcanza para el mes.")).toBeTruthy();
    expect(screen.queryByText(/esperan a una persona/i)).toBeNull();
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  it("money is one group: the balance, how long it lasts, the month's spend — and the way to Consumo", async () => {
    const { onUsage } = await view();
    expect(screen.getAllByText("Saldo disponible")).toHaveLength(1);
    expect(screen.getByLabelText(/^Saldo disponible: .*30,13/)).toBeTruthy();
    expect(screen.getByLabelText(/^Cubre 11 de 24 días del mes/)).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Días del mes que cubre el saldo" })).toBeTruthy();
    expect(screen.getByLabelText(/^Gasto del mes: .*16,26/)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Ver consumo" }));
    expect(onUsage).toHaveBeenCalled();
  });

  it("without the Consumo module the money group has no way in and nothing to press (R6.4)", async () => {
    await view({ nav: ["panel", "inbox"] });
    expect(screen.getByLabelText(/^Saldo disponible: .*30,13/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ver consumo" })).toBeNull();
    // The money group has nothing to press (the conversations' row to the Bandeja is another block, spec 044 R9.3).
    expect(within(screen.getByTestId("home-money")).queryByTestId("row-indicator-push")).toBeNull();
  });

  it("waiting and a low balance: two rows in the attention block, each datum once", async () => {
    await view({
      home: home({
        attention: [
          { kind: "waiting", count: 1, days_left: null },
          { kind: "balance_low", count: null, days_left: 4.6 },
        ],
      }),
    });
    expect(screen.getAllByText("1 conversación espera a una persona")).toHaveLength(1);
    expect(screen.getAllByText("Te quedarás sin saldo en unos 4 días. Pide más saldo a Amacrux.")).toHaveLength(1);
    expect(screen.getAllByText("Saldo disponible")).toHaveLength(1);
  });

  it("one way to Consumo per screen: when the attention block offers it, the money group does not repeat it", async () => {
    await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }] }) });
    expect(screen.getAllByRole("button", { name: "Ver consumo" })).toHaveLength(1);
  });

  it("the waiting row says it once: no «Bandeja de entrada» label repeating the sentence next to it", async () => {
    await view({ home: home({ attention: [{ kind: "waiting", count: 2, days_left: null }] }) });
    expect(screen.queryByText("Bandeja de entrada")).toBeNull();
    expect(screen.getByText("2 conversaciones esperan a una persona")).toBeTruthy();
  });

  it("an unassigned balance says so, with no invented figures", async () => {
    await view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null, month_days_left: 24 } }) });
    expect(screen.getByLabelText(/^Saldo disponible: —\. Todavía no tienes un tope asignado/)).toBeTruthy();
    expect(screen.queryByText(/Cubre/)).toBeNull();
  });

  it("conversations are one hero figure with their trend, and the bars under it", async () => {
    await view({ home: home({ conversations: { last_7d: 75, prev_7d: 60, daily: days.map((day) => ({ day, count: 10 })) } }) });
    expect(screen.getByText("75")).toBeTruthy();
    expect(screen.getByText("25 % más que los 7 días anteriores")).toBeTruthy();
    expect(screen.getByLabelText(/^Conversaciones por día de los últimos 7 días/)).toBeTruthy();
    // The money group's way to Consumo, and the conversations' way to the Bandeja (spec 044, R9.3).
    expect(screen.getAllByTestId("row-indicator-push")).toHaveLength(2);
  });
});

it("a short balance says for how long and whom to ask — with no buy button (R4.4)", async () => {
  await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }] }) });
  expect(screen.getByText("Te quedarás sin saldo en unos 4 días. Pide más saldo a Amacrux.")).toBeTruthy();
  expect(screen.queryByText(/comprar|recargar/i)).toBeNull();
});

it("without the Bandeja there is no «waiting» action into it", async () => {
  await view({ nav: ["panel", "usage"], home: home({ waiting: null }) });
  expect(screen.queryByText(/esperan a una persona/i)).toBeNull();
  expect(screen.queryByRole("button", { name: /Atender/ })).toBeNull();
});

/**
 * Spec 044, Historia 5, Requisito 9: what needs a person in every module, and
 * «Hoy en Reservas» — counted from the same read as the Reservas tab (D4).
 */
describe("Inicio with Reservas (spec 044, R9)", () => {
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

  it("today's unconfirmed reservations join «Necesita tu atención», with «Ver reservas»", async () => {
    const { onReservas } = await view({ nav, reservas: servicesToday });
    expect(screen.getByText("2 reservas de hoy sin confirmar. El agente ya les escribió.")).toBeTruthy();
    await fireEvent.press(screen.getAllByRole("button", { name: "Ver reservas" })[0]!);
    expect(onReservas).toHaveBeenCalled();
  });

  it("they bring the attention block even when nothing else needs a person", async () => {
    await view({ nav, reservas: servicesToday });
    expect(screen.getByRole("header", { name: "Necesita tu atención" })).toBeTruthy();
    expect(screen.queryByText(/Todo en orden/)).toBeNull();
  });

  it("«Hoy en Reservas» in Servicios: today's count, the next one and the three next", async () => {
    await view({ nav, reservas: servicesToday });
    expect(screen.getByRole("header", { name: "Hoy en Reservas" })).toBeTruthy();
    expect(screen.getByText("5 reservas hoy")).toBeTruthy();
    expect(screen.getByText("Próxima a las 11:30 · 2 sin confirmar")).toBeTruthy();
    expect(screen.getByText("Camila Rojas")).toBeTruthy();
    expect(screen.getByText("Isidora Morales")).toBeTruthy();
    expect(screen.queryByText("Joaquín Contreras")).toBeNull();
  });

  it("with large text, the time grows instead of breaking and the state goes under the name (gate review)", async () => {
    await view({ nav, reservas: servicesToday });
    const time = screen.getByText("11:30");
    expect(time.props.numberOfLines).toBe(1);
    expect(StyleSheet.flatten(time.props.style).width).toBeUndefined();
    expect(within(screen.getByTestId("today-b-body")).getByTestId("pill-pending")).toBeTruthy();
  });

  it("«Hoy en Reservas» in Aforo: inside now, who arrives in the next hour and the waitlist", async () => {
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
    expect(screen.getByText("Josefa Castillo")).toBeTruthy();
  });

  it("without the module there is no trace of Reservas", async () => {
    await view();
    expect(screen.queryByText("Hoy en Reservas")).toBeNull();
    expect(screen.queryByText(/reservas de hoy/)).toBeNull();
  });

  it("loading and failing are said in place", async () => {
    await view({ nav, reservas: { state: "error", retry: () => undefined } });
    expect(screen.getByText("No pudimos cargar las reservas.")).toBeTruthy();
  });

  it("the conversations block takes you to the Bandeja (R9.3)", async () => {
    const { onInbox } = await view({ nav });
    await fireEvent.press(screen.getByRole("button", { name: "Ver la Bandeja" }));
    expect(onInbox).toHaveBeenCalled();
  });
});
