import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Home, Me } from "@/api/endpoints";
import { HomeView } from "@/features/home/home-view";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T063, R4.1, R4.4, R14.1): Inicio is the console's Panel, in each
 * of its states.
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
  expect(screen.getByText(/16,26/)).toBeTruthy();
  expect(screen.getByText("Esperan a una persona")).toBeTruthy();
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
  await fireEvent.press(screen.getByRole("button", { name: "Atender" }));
  expect(onAttend).toHaveBeenCalledWith("c-2");
});

it("a short balance says for how long and whom to ask — with no buy button (R4.4)", async () => {
  await view({ home: home({ attention: [{ kind: "balance_low", count: null, days_left: 4.6 }] }) });
  expect(screen.getByText("Te quedarás sin saldo en unos 4 días. Pide más saldo a Amacrux.")).toBeTruthy();
  expect(screen.queryByText(/comprar|recargar/i)).toBeNull();
});

it("nothing pending is one calm line", async () => {
  await view();
  expect(screen.getByText("Todo en orden. Nada espera a una persona y el saldo alcanza para el mes.")).toBeTruthy();
});

it("without the Bandeja there is no «waiting» action into it", async () => {
  await view({ nav: ["panel", "usage"], home: home({ waiting: null }) });
  expect(screen.queryByText("Esperan a una persona")).toBeNull();
  expect(screen.queryByRole("button", { name: /Atender/ })).toBeNull();
});

it("the spend splits by agent only with more than one", async () => {
  await view({
    home: home({
      spend_month: {
        total_cents: 1000,
        by_agent: [
          { agent_id: "a1", name: "Recepción", cents: 600 },
          { agent_id: "a2", name: "Ventas", cents: 400 },
        ],
      },
    }),
  });
  expect(screen.getByLabelText(/Recepción: .*60 %/)).toBeTruthy();
  expect(screen.getByLabelText(/Ventas: .*40 %/)).toBeTruthy();
});

describe("large text (R14.3)", () => {
  it("the figures grow with the system text size, so at 200 % they stack instead of splitting words", async () => {
    const { Metric } = require("@/features/home/metric");
    const { icons } = require("@/ui/icon");
    const RN = require("react-native");
    const spy = jest.spyOn(RN, "useWindowDimensions");
    const basisAt = async (fontScale: number) => {
      spy.mockReturnValue({ width: 411, height: 914, scale: 2.625, fontScale });
      await render(<Metric icon={icons.chat} label="Conversaciones" value="5" testID="metric" />);
      return RN.StyleSheet.flatten(screen.getByTestId("metric").props.style).flexBasis as number;
    };
    const normal = await basisAt(1);
    const large = await basisAt(2);
    // Two cards and the gap fit in a 379 dp column at 100 %, and do not at 200 %.
    expect(2 * normal + 12).toBeLessThanOrEqual(379);
    expect(2 * large + 12).toBeGreaterThan(379);
    spy.mockRestore();
  });
});
