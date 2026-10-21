import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import { t as translate, type MessageKey } from "@/i18n/t";

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

async function view(p: { home?: Home | null; nav?: string[] } = {}) {
  const onAttend = jest.fn();
  const onUsage = jest.fn();
  const onRetry = jest.fn();
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
    />,
  );
  return { onAttend, onUsage, onRetry };
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
    expect(screen.queryByTestId("row-indicator-push")).toBeNull();
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
    await view({ home: home({ balance: { assigned: false, remaining_cents: null, cap_cents: null, days_left: null } }) });
    expect(screen.getByLabelText(/^Saldo disponible: —\. Todavía no tienes un tope asignado/)).toBeTruthy();
    expect(screen.queryByText(/Cubre/)).toBeNull();
  });

  it("conversations are one hero figure with their trend, and the bars under it", async () => {
    await view({ home: home({ conversations: { last_7d: 75, prev_7d: 60, daily: days.map((day) => ({ day, count: 10 })) } }) });
    expect(screen.getByText("75")).toBeTruthy();
    expect(screen.getByText("25 % más que los 7 días anteriores")).toBeTruthy();
    expect(screen.getByLabelText(/^Conversaciones por día de los últimos 7 días/)).toBeTruthy();
    expect(screen.queryByTestId("row-indicator-push")).toBeTruthy(); // only the money group's way to Consumo
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
