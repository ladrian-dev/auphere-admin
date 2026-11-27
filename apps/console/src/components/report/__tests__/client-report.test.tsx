import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientReport as Report } from "@/lib/backend/client-report";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/clients/jemma/report",
}));

const { ClientReport, ReportSkeleton } = await import("../client-report");

/**
 * Spec 083 (T005) — la pestaña «Informe» de un cliente: las cuatro cifras arriba,
 * la gráfica, la agenda, los recordatorios, las incidencias y el freno, cada
 * bloque con su definición (8.5). Sus cinco estados (8.6), sin Reservas no hay
 * agenda (6.5), la nota de quien no cierra por inactividad (historia 2) y lo que
 * sale al imprimir (8.7).
 */

const money = (amount_micros: number) => ({ amount_micros, currency: "USD" as const });

const REPORT: Report = {
  from: "2026-11-10",
  to: "2026-11-26",
  timezone: "America/Caracas",
  since: "2026-11-10T04:00:00Z",
  until: "2026-11-26T15:00:00Z",
  generated_at: "2026-11-26T15:02:11Z",
  autoclose: true,
  targets: { without_person_pct: 70, first_response_pct: 95, first_response_seconds: 60 },
  conversations: {
    total: 214,
    without_person: 163,
    with_person: 51,
    without_person_pct: 76.2,
    series: [
      { day: "2026-11-25", without_person: 6, with_person: 2 },
      { day: "2026-11-26", without_person: 4, with_person: 1 },
    ],
  },
  first_response: { answered: 205, within_target: 199, within_target_pct: 97.1, median_seconds: 9, p90_seconds: 21, unanswered: 9 },
  incidents: {
    total: 58,
    resolved: 55,
    open: 3,
    by_cause: [
      { cause: "escalated", total: 31, resolved: 30 },
      { cause: "booking_brake", total: 10, resolved: 10 },
    ],
    items: [
      { at: "2026-11-26T02:14:03Z", cause: "booking_brake", resolved_at: null },
      { at: "2026-11-25T18:00:00Z", cause: "no_balance", resolved_at: "2026-11-25T19:00:00Z" },
    ],
    truncated: false,
  },
  booking_brake: { stopped: 12, corrected: 10, handed_over: 2 },
  agenda: {
    created: { agent: 61, person: 9, customer: 1, total: 71 },
    moved: { agent: 14, person: 3, customer: 0, total: 17 },
    cancelled: { agent: 8, person: 2, customer: 5, total: 15 },
    released: 2,
    reminders: [
      { kind: "reminder", sent: 80, failed: 1, skipped: 0 },
      { kind: "ask_confirmation", sent: 66, failed: 0, skipped: 2 },
    ],
  },
  spend: {
    currency: "USD",
    total: money(41_280_000),
    conversations: money(40_100_000),
    client_tests: money(1_180_000),
    meta: money(3_020_000),
    approx: false,
    per_conversation: money(192_897),
  },
};

const CLIENTS = [
  { ref: "jemma", name: "Jemma's Hair" },
  { ref: "boreal", name: "Clínica Boreal" },
];

function view(report: Report | null, extra: Partial<React.ComponentProps<typeof ClientReport>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientReport
        refId="jemma"
        clientName="Jemma's Hair"
        clients={CLIENTS}
        period={{ from: "2026-11-10", to: "2026-11-26" }}
        today="2026-11-26"
        report={report}
        {...extra}
      />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  router.push.mockReset();
  router.refresh.mockReset();
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.colorScheme = "";
});

describe("ClientReport · ideal", () => {
  it("abre con las cuatro cifras, frente a sus objetivos y con el código de la moneda detrás", () => {
    view(REPORT);
    const figures = screen.getByRole("list", { name: "Cifras del periodo" });
    const items = within(figures).getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent("Conversaciones atendidas");
    expect(items[0]).toHaveTextContent("214");
    expect(items[1]).toHaveTextContent("76,2 %");
    expect(items[1]).toHaveTextContent("Objetivo 70 %");
    expect(items[1]).toHaveTextContent("Alcanza el objetivo");
    expect(items[2]).toHaveTextContent("97,1 %");
    expect(items[2]).toHaveTextContent("Objetivo 95 % en 60 s o menos");
    expect(items[3]).toHaveTextContent("412,80 USD");
    expect(items[3]).toHaveTextContent("1,93 USD por conversación");
  });

  it("debajo, la gráfica por día con sus dos series", () => {
    view(REPORT);
    expect(screen.getByRole("heading", { name: "Conversaciones por día" })).toBeVisible();
    expect(screen.getByText("Resueltas sin persona", { selector: "li span" })).toBeInTheDocument();
    expect(screen.getByText("Con persona", { selector: "li span" })).toBeInTheDocument();
    expect(screen.getByRole("listbox", { name: "Conversaciones por día" })).toBeInTheDocument();
  });

  it("la primera respuesta da la mediana, el percentil 90 y las que el agente no contestó", () => {
    view(REPORT);
    const block = screen.getByRole("region", { name: "Primera respuesta" });
    expect(block).toHaveTextContent("9 s");
    expect(block).toHaveTextContent("21 s");
    expect(block).toHaveTextContent("9 conversaciones sin respuesta del agente");
  });

  it("la agenda por quién la hizo, y los recordatorios por resultado", () => {
    view(REPORT);
    const agenda = screen.getByRole("table", { name: "Agenda" });
    const rows = within(agenda).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(/Creadas\s*61\s*9\s*1\s*71/);
    expect(rows[3]).toHaveTextContent(/Canceladas\s*8\s*2\s*5\s*15/);
    expect(screen.getByRole("region", { name: "Agenda" })).toHaveTextContent("2 liberadas sin confirmar");
    const reminders = screen.getByRole("table", { name: "Recordatorios" });
    expect(within(reminders).getAllByRole("row")[1]).toHaveTextContent(/Recordatorios de la cita\s*80\s*1\s*0/);
  });

  it("las incidencias por motivo y las más recientes, en palabras, sin texto del agente", () => {
    view(REPORT);
    const block = screen.getByRole("region", { name: "Incidencias" });
    expect(block).toHaveTextContent("58");
    expect(block).toHaveTextContent("55 resueltas");
    expect(block).toHaveTextContent("3 abiertas");
    expect(block).toHaveTextContent("Pidió una persona");
    expect(block).toHaveTextContent("Freno de reservas");
    const list = within(block).getByRole("table", { name: "Las más recientes" });
    expect(within(list).getAllByRole("row")[1]).toHaveTextContent("Sin resolver");
    expect(within(list).getAllByRole("row")[2]).toHaveTextContent("Sin saldo");
  });

  it("cada bloque dice qué mide, y el freno sus límites", () => {
    view(REPORT);
    expect(screen.getByText(/un ciclo: desde que el contacto escribe hasta que se resuelve/i)).toBeInTheDocument();
    expect(screen.getByText(/desde el primer mensaje del contacto hasta que el canal acepta la primera respuesta del agente/i)).toBeInTheDocument();
    expect(screen.getByText(/cada vez que el agente pidió una persona, una regla no le dejó contestar o el freno paró una respuesta/i)).toBeInTheDocument();
    const brake = screen.getByRole("region", { name: "Freno de reservas" });
    expect(brake).toHaveTextContent(/12\s*veces paró una respuesta/);
    expect(brake).toHaveTextContent(/no detecta una cita confirmada a mano fuera de la agenda/i);
  });

  it("un objetivo no alcanzado se dice con palabras, no con ámbar", () => {
    const { container } = view({
      ...REPORT,
      conversations: { ...REPORT.conversations, without_person: 128, with_person: 86, without_person_pct: 59.8 },
    });
    expect(screen.getByRole("list", { name: "Cifras del periodo" })).toHaveTextContent("Por debajo del objetivo");
    expect(container.querySelector("[class*='warn'], [class*='amber']")).toBeNull();
  });
});

describe("ClientReport · los otros estados", () => {
  it("cargando: el esqueleto del tamaño final, anunciado", () => {
    render(
      <LocaleProvider locale="es">
        <ReportSkeleton />
      </LocaleProvider>,
    );
    const status = screen.getByRole("status", { name: "Cargando el informe" });
    expect(status.querySelectorAll("[data-slot=skeleton]").length).toBeGreaterThanOrEqual(8);
  });

  it("vacío: el informe sale entero, con ceros, y explica que no hubo conversaciones", () => {
    view({
      ...REPORT,
      conversations: { total: 0, without_person: 0, with_person: 0, without_person_pct: null, series: REPORT.conversations.series.map((d) => ({ ...d, without_person: 0, with_person: 0 })) },
      first_response: { answered: 0, within_target: 0, within_target_pct: null, median_seconds: null, p90_seconds: null, unanswered: 0 },
      incidents: { total: 0, resolved: 0, open: 0, by_cause: [], items: [], truncated: false },
      spend: { ...REPORT.spend!, total: money(0), per_conversation: null },
    });
    expect(screen.getByText("No hubo conversaciones en estas fechas")).toBeVisible();
    const items = within(screen.getByRole("list", { name: "Cifras del periodo" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("0");
    expect(items[1]).toHaveTextContent("—");
    expect(items[1]).not.toHaveTextContent("objetivo");
    expect(items[3]).not.toHaveTextContent("por conversación");
    expect(screen.getByRole("region", { name: "Incidencias" })).toHaveTextContent("Ninguna incidencia en estas fechas");
  });

  it("error: lo dice y deja reintentar", async () => {
    view(null);
    expect(screen.getByText("No se pudo cargar el informe")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(router.refresh).toHaveBeenCalled();
    // Los filtros siguen ahí: se puede pedir otro periodo.
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-11-10");
  });

  it("parcial: sin el gasto, el resto sale y el gasto dice que no se pudo leer", async () => {
    view({ ...REPORT, spend: null });
    const items = within(screen.getByRole("list", { name: "Cifras del periodo" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("214");
    expect(items[3]).toHaveTextContent("No se pudo leer el gasto");
    await userEvent.click(within(items[3]!).getByRole("button", { name: "Reintentar" }));
    expect(router.refresh).toHaveBeenCalled();
  });

  it("sin Reservas no hay agenda ni recordatorios, ni vacíos ni explicados", () => {
    view({ ...REPORT, agenda: null });
    expect(screen.queryByRole("region", { name: "Agenda" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Recordatorios" })).toBeNull();
    expect(screen.queryByText(/Reservas/)).toBeNull();
  });

  it("si el cliente no cierra por inactividad, lo dice", () => {
    view({ ...REPORT, autoclose: false });
    expect(screen.getByText(/no cierra solas las conversaciones inactivas/i)).toBeVisible();
  });

  it("si las cierra, no hay nota", () => {
    view(REPORT);
    expect(screen.queryByText(/no cierra solas las conversaciones inactivas/i)).toBeNull();
  });
});

describe("ClientReport · los filtros", () => {
  it("un atajo pide los últimos días con hoy incluido", async () => {
    view(REPORT);
    await userEvent.click(screen.getByRole("button", { name: "7 días" }));
    expect(router.push).toHaveBeenCalledWith("/clients/jemma/report?from=2026-11-20&to=2026-11-26", { scroll: false });
  });

  it("otro cliente, con las mismas fechas", async () => {
    view(REPORT);
    await userEvent.selectOptions(screen.getByLabelText("Cliente"), "boreal");
    expect(router.push).toHaveBeenCalledWith("/clients/boreal/report?from=2026-11-10&to=2026-11-26", { scroll: false });
  });

  it("las fechas no dejan pedir el futuro ni más de 92 días", () => {
    view(REPORT);
    const from = screen.getByLabelText("Desde");
    const to = screen.getByLabelText("Hasta");
    expect(to).toHaveAttribute("max", "2026-11-26");
    expect(to).toHaveAttribute("min", "2026-11-10");
    expect(from).toHaveAttribute("max", "2026-11-26");
    expect(from).toHaveAttribute("min", "2026-08-27");
  });

  it("un periodo imposible se explica y no se pide", () => {
    view(REPORT);
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-11-27" } });
    expect(screen.getByText("El periodo no puede acabar después de hoy ni empezar después de acabar")).toBeVisible();
    expect(router.push).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-11-01" } });
    expect(router.push).toHaveBeenCalledWith("/clients/jemma/report?from=2026-11-01&to=2026-11-26", { scroll: false });
  });
});

describe("ClientReport · imprimir (8.7)", () => {
  it("«Imprimir» abre el diálogo del navegador", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    view(REPORT);
    await userEvent.click(screen.getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalled();
    print.mockRestore();
  });

  it("sale un encabezado solo de impresión con el cliente, el periodo, la zona y cuándo se generó", () => {
    const { container } = view(REPORT);
    const header = container.querySelector("[data-slot=report-print-header]")!;
    expect(header.className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(header.className).toMatch(/print:block/);
    expect(header).toHaveTextContent("Jemma's Hair");
    expect(header).toHaveTextContent("Del 10 nov 2026 al 26 nov 2026");
    expect(header).toHaveTextContent("America/Caracas");
    expect(header).toHaveTextContent("Generado el");
    // Los filtros no se imprimen.
    expect(container.querySelector("[data-slot=report-filters]")!.className).toMatch(/print:hidden/);
    // Los colores de la gráfica, sí.
    expect(container.querySelector("[data-slot=client-report]")!.className).toMatch(/print-color-adjust:exact/);
  });

  it("al imprimir se encoge y compacta las tablas para que 30 días quepan en dos A4 (CE-004)", () => {
    // Medido en la pasada viva (T017): sin esto, 30 días con Reservas e incidencias
    // salen en tres A4 con márgenes de 10 mm; con zoom 0,9 y filas de `py-1`, en dos,
    // también con nombres alemanes largos.
    const { container } = view(REPORT);
    expect(container.querySelector("[data-slot=client-report]")!.className).toMatch(/print:\[zoom:0\.9\]/);
    const tables = container.querySelectorAll("[data-slot=client-report] [data-scroll-x][role=group]");
    expect(tables.length).toBeGreaterThan(0);
    // La variante arbitraria va delante: `print:[&_td]:py-1` Tailwind no la genera.
    for (const box of tables) {
      expect(box.className).toMatch(/\[&_td\]:print:py-1/);
      expect(box.className).toMatch(/\[&_th\]:print:h-auto/);
      expect(box.className).toMatch(/\[&_th\]:print:py-1/);
    }
  });

  it("imprime en tema claro y vuelve al oscuro después", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.style.colorScheme = "dark";
    view(REPORT);
    window.dispatchEvent(new Event("beforeprint"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("con el tema claro no toca nada", () => {
    document.documentElement.setAttribute("data-theme", "light");
    view(REPORT);
    window.dispatchEvent(new Event("beforeprint"));
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
