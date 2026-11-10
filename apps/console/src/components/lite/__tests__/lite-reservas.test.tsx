import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { LiteHome } from "@/lib/backend/lite";
import type { ReservasSummary } from "@/lib/backend/reservas";

import { booking, capacityBooking } from "../../reservas/model/__tests__/fixtures";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const { LitePanelView } = await import("../lite-panel-view");
const { LiteReservasSkeleton } = await import("../lite-reservas");

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

function home(o: Partial<LiteHome> = {}): LiteHome {
  return {
    spend_month: { total_cents: 1626, by_agent: null },
    conversations: null,
    waiting: { count: 0, first_conversation_id: null },
    balance: { assigned: true, remaining_cents: 3013, cap_cents: 5000, days_left: 40, month_days_left: 10, runs_out_on: null },
    attention: [],
    errors: [],
    ...o,
  };
}

const ANA = "00000000-0000-4000-8000-00000000f001";

function servicesSummary(o: Partial<ReservasSummary> = {}): ReservasSummary {
  return {
    mode: "services",
    today: { date: "2026-10-22", bookings: 12, confirmed: 9, pending: 3, next_at: "2026-10-22T19:30:00Z", people: null, inside_now: null, arriving_next_hour: null, seats: null },
    week: { occupancy_pct: 63.8, agent_share_pct: 58 },
    month: { noshow_pct: 4.2, recovered: 3 },
    waitlist: { waiting: 2 },
    clashes: 0,
    upcoming: [booking({ id: ANA, status: "pending" }), booking({ local: { date: "2026-10-22", start: "17:30", end: "18:15" }, contact: { name: "Pedro Soto", phone: null, conversation_id: null } })],
    errors: [],
    ...o,
  };
}

function capacitySummary(o: Partial<ReservasSummary> = {}): ReservasSummary {
  return {
    mode: "capacity",
    today: { date: "2026-10-22", bookings: 12, confirmed: 9, pending: 3, next_at: null, people: 42, inside_now: 18, arriving_next_hour: 9, seats: 64 },
    week: { occupancy_pct: 71, agent_share_pct: 40 },
    month: { noshow_pct: null, recovered: 1 },
    waitlist: { waiting: 2 },
    clashes: 0,
    upcoming: [capacityBooking({ id: ANA, contact: { name: "Familia Rojas", phone: null, conversation_id: null } })],
    errors: [],
    ...o,
  };
}

type Reservas = NonNullable<Parameters<typeof LitePanelView>[0]["reservas"]>;
const servicesInfo: Reservas["info"] = { mode: "services", capacity_kind: null };
const restaurant: Reservas["info"] = { mode: "capacity", capacity_kind: "restaurant" };

function view(reservas: Reservas | null, o: { home?: LiteHome | null; modules?: string[] } = {}) {
  const modules = o.modules ?? ["panel", "inbox", "reservas", "usage"];
  return render(
    <LocaleProvider locale="es">
      <LitePanelView
        who={{ name: "Valeria Ríos", clientName: "Peluquería Boreal", modules }}
        home={o.home === undefined ? home() : o.home}
        contact={{ kind: "partner", name: "Amacrux" }}
        reservas={reservas}
        t={t}
        locale="es"
      />
    </LocaleProvider>,
  );
}

const figure = (block: HTMLElement, label: string) => {
  const term = within(block).getByText(label, { selector: "dt" });
  return term.parentElement as HTMLElement;
};

/** Spec 043 (T026, Requisito 8.4): the Reservas block of the Panel, by mode and in its five states. */
describe("Panel · bloque de Reservas", () => {
  it("Servicios: «Agenda» with the long date, the five figures and a way into Reservas", () => {
    view({ info: servicesInfo, summary: servicesSummary() });
    const block = screen.getByRole("region", { name: "Agenda" });
    expect(within(block).getByText("Jueves, 22 de octubre")).toBeInTheDocument();
    expect(within(block).getByRole("button", { name: "Ver reservas" })).toHaveAttribute("href", "/reservas");
    const today = figure(block, "Reservas hoy");
    expect(within(today).getByText("12")).toBeInTheDocument();
    expect(within(today).getByText("9 confirmadas · 3 sin confirmar")).toBeInTheDocument();
    expect(within(figure(block, "Ocupación esta semana")).getByText("64 %")).toBeInTheDocument();
    expect(within(figure(block, "Reservadas por el agente")).getByText("58 %")).toBeInTheDocument();
    expect(within(figure(block, "Reservadas por el agente")).getByText("De la semana")).toBeInTheDocument();
    expect(within(figure(block, "No se presentaron")).getByText("4,2 %")).toBeInTheDocument();
    expect(within(figure(block, "Huecos recuperados")).getByText("3")).toBeInTheDocument();
  });

  it("Servicios: the next ones of today open their booking, with service, professional and status", () => {
    view({ info: servicesInfo, summary: servicesSummary() });
    const block = screen.getByRole("region", { name: "Agenda" });
    const next = within(block).getByRole("list", { name: "Próximas de hoy" });
    const rows = within(next).getAllByRole("link");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("href", `/reservas?booking=${ANA}`);
    expect(rows[0]).toHaveTextContent("16:30");
    expect(rows[0]).toHaveTextContent("Ana Pérez");
    expect(rows[0]).toHaveTextContent("Corte y barba · Lucía");
    expect(within(rows[0]!).getByText("Sin confirmar")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Confirmada")).toBeInTheDocument();
  });

  it("Servicios: a figure with no data yet says «—», never an invented zero", () => {
    view({ info: servicesInfo, summary: servicesSummary({ month: { noshow_pct: null, recovered: null } }) });
    const block = screen.getByRole("region", { name: "Agenda" });
    expect(within(figure(block, "No se presentaron")).getByText("—")).toBeInTheDocument();
    const recovered = figure(block, "Huecos recuperados");
    expect(within(recovered).getByText("—")).toBeInTheDocument();
    expect(within(recovered).getByText("La lista de espera está apagada")).toBeInTheDocument();
  });

  it("Aforo: «Ocupación» in the business's words — people in bookings, inside now, unconfirmed, waiting", () => {
    view({ info: restaurant, summary: capacitySummary() });
    const block = screen.getByRole("region", { name: "Ocupación" });
    const booked = figure(block, "Reservados hoy");
    expect(within(booked).getByText("42")).toBeInTheDocument();
    expect(within(booked).getByText("comensales en 12 reservas")).toBeInTheDocument();
    const inside = figure(block, "Dentro ahora");
    expect(within(inside).getByText("18")).toBeInTheDocument();
    expect(within(inside).getByText("De un aforo de 64 · Llegan 9 comensales en la próxima hora")).toBeInTheDocument();
    expect(within(figure(block, "Sin confirmar")).getByText("3")).toBeInTheDocument();
    expect(within(figure(block, "Lista de espera")).getByText("2")).toBeInTheDocument();
    expect(within(block).queryByText("Reservas hoy")).toBeNull();
    const row = within(within(block).getByRole("list", { name: "Próximas de hoy" })).getByRole("link");
    expect(row).toHaveTextContent("20:30");
    expect(row).toHaveTextContent("Familia Rojas");
    expect(row).toHaveTextContent("4 comensales");
  });

  it("Aforo: a bar counts people and a class counts places", () => {
    const { unmount } = view({ info: { mode: "capacity", capacity_kind: "bar" }, summary: capacitySummary() });
    expect(screen.getByText("personas en 12 reservas")).toBeInTheDocument();
    unmount();
    view({ info: { mode: "capacity", capacity_kind: "classes" }, summary: capacitySummary({ today: { ...capacitySummary().today!, people: 1, bookings: 1 } }) });
    expect(screen.getByText("plaza en 1 reserva")).toBeInTheDocument();
  });

  it("empty: nothing left today is one calm line", () => {
    view({ info: servicesInfo, summary: servicesSummary({ upcoming: [] }) });
    const block = screen.getByRole("region", { name: "Agenda" });
    expect(within(block).getByText("No quedan reservas para hoy.")).toBeInTheDocument();
    expect(within(block).queryByRole("list", { name: "Próximas de hoy" })).toBeNull();
  });

  it("error: the summary that did not load says so inside the block, without a single zero", () => {
    view({ info: servicesInfo, summary: null });
    const block = screen.getByRole("region", { name: "Agenda" });
    expect(within(block).getByText("No se pudieron cargar las cifras de Reservas.")).toBeInTheDocument();
    expect(within(block).queryByText("Reservas hoy")).toBeNull();
    expect(within(block).queryByText("0")).toBeNull();
    expect(within(block).getByRole("button", { name: "Ver reservas" })).toHaveAttribute("href", "/reservas");
  });

  it("error without /me either: the block keeps a neutral name", () => {
    view({ info: null, summary: null });
    expect(screen.getByRole("region", { name: "Reservas" })).toBeInTheDocument();
  });

  it("partial: a block that did not load is «—» and a note says part is missing", () => {
    view({ info: servicesInfo, summary: servicesSummary({ week: null, errors: ["week"] }) });
    const block = screen.getByRole("region", { name: "Agenda" });
    expect(within(block).getByText("Parte de las cifras de Reservas no se pudo cargar.")).toBeInTheDocument();
    expect(within(figure(block, "Ocupación esta semana")).getByText("—")).toBeInTheDocument();
    expect(within(figure(block, "Reservas hoy")).getByText("12")).toBeInTheDocument();
  });

  it("without the module there is no block", () => {
    view(null, { modules: ["panel", "inbox", "usage"] });
    expect(screen.queryByRole("region", { name: "Agenda" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Ocupación" })).toBeNull();
    expect(screen.queryByText("Ver reservas")).toBeNull();
  });

  it("loading: a skeleton with the block's final shape", () => {
    const { container } = render(<LiteReservasSkeleton t={t} />);
    expect(screen.getByRole("status", { name: "Cargando Reservas" })).toBeInTheDocument();
    expect(container.querySelector('[data-slot="lite-reservas-skeleton"]')).not.toBeNull();
    expect(screen.getByText("Próximas de hoy")).toBeInTheDocument();
  });
});

/** Spec 043 (T026, Requisito 8.4): «N reservas de hoy sin confirmar» in «Necesita tu atención». */
describe("Panel · atención de Reservas", () => {
  const attention = () => screen.getByRole("region", { name: /Necesita tu atención/ });

  it("unconfirmed bookings of today are a row with a way into Reservas, and «all in order» goes", () => {
    view({ info: servicesInfo, summary: servicesSummary() });
    const box = attention();
    expect(within(box).getByText("Reservas")).toBeInTheDocument();
    expect(within(box).getByText("3 reservas de hoy sin confirmar. El agente ya les escribió.")).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: "Ver reservas" })).toHaveAttribute("href", "/reservas");
    expect(within(box).getByText("1", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText(/Todo en orden/)).toBeNull();
  });

  it("one unconfirmed booking reads in the singular", () => {
    view({ info: servicesInfo, summary: servicesSummary({ today: { ...servicesSummary().today!, pending: 1 } }) });
    expect(within(attention()).getByText("1 reserva de hoy sin confirmar. El agente ya le escribió.")).toBeInTheDocument();
  });

  it("sits between the inbox and the balance, keeping both", () => {
    view(
      { info: servicesInfo, summary: servicesSummary() },
      {
        home: home({
          waiting: { count: 2, first_conversation_id: "c-1" },
          attention: [
            { kind: "waiting", count: 2, days_left: null },
            { kind: "balance_low", count: null, days_left: 4.2 },
          ],
        }),
      },
    );
    const items = within(within(attention()).getByRole("list")).getAllByRole("listitem");
    expect(items.map((li) => li.querySelector("span.font-medium")?.textContent)).toEqual(["Bandeja de entrada", "Reservas", "Saldo"]);
    expect(within(attention()).getByText("3", { selector: "span" })).toBeInTheDocument();
  });

  it("nothing unconfirmed: no row, and the calm line stays", () => {
    view({ info: servicesInfo, summary: servicesSummary({ today: { ...servicesSummary().today!, pending: 0 } }) });
    expect(screen.queryByText(/sin confirmar\. El agente/)).toBeNull();
    expect(screen.getByText("Todo en orden. Nada espera a una persona y el saldo alcanza para el mes.")).toBeInTheDocument();
  });

  it("still says it when the rest of the Panel did not load", () => {
    view({ info: servicesInfo, summary: servicesSummary() }, { home: null });
    expect(within(attention()).getByText("3 reservas de hoy sin confirmar. El agente ya les escribió.")).toBeInTheDocument();
  });
});

