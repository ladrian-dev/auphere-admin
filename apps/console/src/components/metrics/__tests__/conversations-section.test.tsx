import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientReport as Report } from "@/lib/backend/client-report";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/usage",
  useSearchParams: () => new URLSearchParams("client=jemma"),
}));

const { ConversationsSection, ConversationsChooseClient, ConversationsSkeleton } = await import("../conversations-section");

/**
 * Spec 083, enmienda del 2026-11-27 (T022) — la sección «Conversaciones» de
 * Métricas: las cifras con su diferencia (12), las tres gráficas y las
 * incidencias por motivo (13.2–13.3), sin lista de recientes ni definiciones en
 * párrafo (13.4), sus cinco estados (8.6) y lo que sale al imprimir (8.7, D21).
 */

const money = (amount_micros: number) => ({ amount_micros, currency: "USD" as const });
const hours = (at: Record<number, [number, number]>) =>
  Array.from({ length: 24 }, (_, hour) => ({ hour, without_person: at[hour]?.[0] ?? 0, with_person: at[hour]?.[1] ?? 0 }));
const weekdays = Array.from({ length: 7 }, (_, i) => ({ weekday: i + 1, without_person: 20, with_person: 5 }));

const CURRENT: Report = {
  from: "2026-10-29",
  to: "2026-11-27",
  timezone: "America/Caracas",
  since: "2026-10-29T04:00:00Z",
  until: "2026-11-27T15:00:00Z",
  generated_at: "2026-11-27T15:02:11Z",
  autoclose: true,
  targets: { without_person_pct: 70, first_response_pct: 95, first_response_seconds: 60 },
  conversations: {
    total: 214,
    without_person: 163,
    with_person: 51,
    without_person_pct: 76.2,
    series: [
      { day: "2026-11-26", without_person: 6, with_person: 2 },
      { day: "2026-11-27", without_person: 4, with_person: 1 },
    ],
    by_hour: hours({ 9: [20, 2], 21: [3, 9] }),
    by_weekday: weekdays,
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
    items: [{ at: "2026-11-26T02:14:03Z", cause: "booking_brake", resolved_at: null }],
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

const PREVIOUS: Report = {
  ...CURRENT,
  from: "2026-09-29",
  to: "2026-10-28",
  conversations: { ...CURRENT.conversations, total: 200, without_person_pct: 75 },
  first_response: { ...CURRENT.first_response, within_target_pct: 98, median_seconds: 7 },
  incidents: { ...CURRENT.incidents, total: 50, by_cause: [{ cause: "escalated", total: 25, resolved: 25 }] },
  spend: { ...CURRENT.spend!, per_conversation: money(200_000) },
};

function view(current: Report | null, previous: Report | null = PREVIOUS) {
  return render(
    <LocaleProvider locale="es">
      <ConversationsSection clientName="Jemma's Hair" days={30} today="2026-11-27" current={current} previous={previous} />
    </LocaleProvider>,
  );
}

const figure = (label: string) => screen.getByRole("listitem", { name: label });

beforeEach(() => {
  router.push.mockReset();
  router.refresh.mockReset();
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.colorScheme = "";
});

describe("ConversationsSection · las cifras frente al periodo anterior (12.1–12.4)", () => {
  it("cada cifra con su diferencia: % en recuentos, puntos en porcentajes y segundos en tiempos", () => {
    view(CURRENT);
    expect(figure("Conversaciones")).toHaveTextContent("214");
    expect(figure("Conversaciones")).toHaveTextContent("+7 % frente a los 30 días anteriores");
    expect(figure("Resueltas sin persona")).toHaveTextContent("76,2 %");
    expect(figure("Resueltas sin persona")).toHaveTextContent("+1,2 puntos frente a los 30 días anteriores");
    expect(figure("Respondidas en 60 s o menos")).toHaveTextContent("−0,9 puntos");
    expect(figure("Primera respuesta, mediana")).toHaveTextContent("+2 s");
    expect(figure("Incidencias")).toHaveTextContent("+16 %");
    expect(figure("Coste por conversación")).toHaveTextContent("−4 %");
  });

  it("el objetivo se dice con palabras, no con color", () => {
    view(CURRENT);
    expect(figure("Resueltas sin persona")).toHaveTextContent("Objetivo 70 %");
    expect(figure("Resueltas sin persona")).toHaveTextContent("Alcanza el objetivo");
    expect(figure("Respondidas en 60 s o menos")).toHaveTextContent("Alcanza el objetivo");
    const figures = screen.getByRole("list", { name: "Cifras del periodo" });
    expect(figures.querySelector("[class*=amber], [class*=warning], [class*=destructive], [class*=success]")).toBeNull();
  });

  it("si no cambia, lo dice en una frase que se lee bien", () => {
    view(CURRENT, { ...PREVIOUS, conversations: { ...PREVIOUS.conversations, total: 214 } });
    expect(figure("Conversaciones")).toHaveTextContent("Igual que los 30 días anteriores");
  });

  it("sin nada en el periodo anterior, ninguna diferencia (12.2)", () => {
    view(CURRENT, { ...PREVIOUS, conversations: { ...PREVIOUS.conversations, total: 0, without_person_pct: null } });
    expect(figure("Conversaciones")).not.toHaveTextContent("frente a");
    expect(figure("Resueltas sin persona")).not.toHaveTextContent("frente a");
  });

  it("si el periodo anterior no se pudo leer, las cifras salen sin comparar y lo dice (12.3, parcial)", () => {
    view(CURRENT, null);
    expect(screen.getByText("No se pudo leer el periodo anterior: las cifras van sin comparar.")).toBeInTheDocument();
    expect(figure("Conversaciones")).toHaveTextContent("214");
    expect(screen.queryByText(/frente a los/)).toBeNull();
  });
});

describe("ConversationsSection · los desgloses (13.2–13.4)", () => {
  it("por día, por hora del día y por día de la semana", () => {
    view(CURRENT);
    for (const title of ["Por día", "Por hora del día", "Por día de la semana"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("las incidencias por motivo, con su parte del total y su diferencia", () => {
    view(CURRENT);
    const table = screen.getByRole("table", { name: "Incidencias por motivo" });
    const escalated = within(table).getByRole("row", { name: /Pidió una persona/ });
    expect(escalated).toHaveTextContent("31");
    expect(escalated).toHaveTextContent("53 %");
    expect(escalated).toHaveTextContent("+24 %");
    // El freno no estaba antes: sin con qué comparar.
    expect(within(table).getByRole("row", { name: /Freno de reservas/ })).toHaveTextContent("—");
  });

  it("sin la lista de incidencias recientes ni definiciones en párrafo; «Cómo se cuenta», plegado", () => {
    const { container } = view(CURRENT);
    expect(screen.queryByText("Las más recientes")).toBeNull();
    expect(screen.queryByText("Ver las 1")).toBeNull();
    const how = container.querySelector("details")!;
    expect(how).not.toHaveAttribute("open");
    expect(within(how).getByText("Cómo se cuenta")).toBeInTheDocument();
    expect(how).toHaveTextContent("Conversación: un ciclo");
  });

  it("con Reservas, la agenda por quién, los recordatorios y el freno; sin Reservas, nada de eso", () => {
    view(CURRENT);
    expect(screen.getByRole("table", { name: "Agenda" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Recordatorios" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Freno de reservas" })).toBeInTheDocument();
    view({ ...CURRENT, agenda: null, booking_brake: { stopped: 0, corrected: 0, handed_over: 0 } });
    expect(screen.getAllByRole("table", { name: "Agenda" })).toHaveLength(1);
  });

  it("si el cliente no cierra por inactividad, «Cómo se cuenta» lo dice", () => {
    const { container } = view({ ...CURRENT, autoclose: false });
    expect(container.querySelector("details")).toHaveTextContent("Este cliente no cierra solas las conversaciones inactivas");
  });
});

describe("ConversationsSection · los cinco estados (8.6)", () => {
  it("error: lo dice y deja reintentar", async () => {
    view(null);
    expect(screen.getByText("No se pudieron cargar las conversaciones")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(router.refresh).toHaveBeenCalled();
  });

  it("vacío: ceros, sin porcentajes y lo dice", () => {
    view({
      ...CURRENT,
      conversations: { ...CURRENT.conversations, total: 0, without_person: 0, with_person: 0, without_person_pct: null },
      first_response: { answered: 0, within_target: 0, within_target_pct: null, median_seconds: null, p90_seconds: null, unanswered: 0 },
      incidents: { total: 0, resolved: 0, open: 0, by_cause: [], items: [], truncated: false },
    });
    expect(screen.getByText("Sin conversaciones en estos días")).toBeInTheDocument();
    expect(figure("Resueltas sin persona")).toHaveTextContent("—");
  });

  it("cargando: el esqueleto se anuncia", () => {
    render(
      <LocaleProvider locale="es">
        <ConversationsSkeleton />
      </LocaleProvider>,
    );
    expect(screen.getByRole("status", { name: "Cargando las conversaciones" })).toBeInTheDocument();
  });

  it("sin cliente elegido: pide uno y no da cifras (11.4)", () => {
    render(
      <LocaleProvider locale="es">
        <ConversationsChooseClient />
      </LocaleProvider>,
    );
    expect(screen.getByText("Elige un cliente para ver sus conversaciones")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Cifras del periodo" })).toBeNull();
  });
});

describe("ConversationsSection · imprimir (8.7, D21, CE-004)", () => {
  it("«Imprimir» abre el diálogo del navegador", async () => {
    view(CURRENT);
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    await userEvent.click(screen.getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalled();
    print.mockRestore();
  });

  it("un encabezado solo de impresión, y al imprimir solo sale la sección, encogida y con las barras en color", () => {
    const { container } = view(CURRENT);
    const header = container.querySelector("[data-slot=metrics-print-header]")!;
    expect(header.className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(header.className).toMatch(/print:block/);
    expect(header).toHaveTextContent("Jemma's Hair");
    expect(header).toHaveTextContent("America/Caracas");
    expect(header).toHaveTextContent("Generado el");
    const section = container.querySelector("[data-slot=metrics-conversations]")!;
    expect(section.className).toMatch(/print-color-adjust:exact/);
    expect(section.className).toMatch(/print:\[zoom:0\.9\]/);
    expect(screen.getByRole("button", { name: "Imprimir" }).className).toMatch(/print:hidden/);
  });

  it("al imprimir pasa a tema claro y luego vuelve al que hubiera", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    view(CURRENT);
    window.dispatchEvent(new Event("beforeprint"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
