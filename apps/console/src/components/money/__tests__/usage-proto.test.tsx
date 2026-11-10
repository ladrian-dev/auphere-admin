import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientUsage, UsageDetail } from "@/lib/backend/money-types";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/usage", useSearchParams: () => new URLSearchParams() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/app/(console)/usage/money-actions", () => ({
  assignBalanceAction: vi.fn(),
  bagContextAction: vi.fn(),
  lowerBalanceAction: vi.fn(),
  requestBalanceAction: vi.fn(),
  bagChoicesAction: vi.fn(),
  eurUsdAction: vi.fn(),
  moveBalanceAction: vi.fn(),
  setRefillAction: vi.fn(),
  setBagCurrencyAction: vi.fn(),
}));

const { SpendFilters } = await import("../spend-by-day");
const { UsageClientsTable } = await import("../usage-clients-table");
const { UsageDetailPanel } = await import("../usage-detail");
const { UsageFigure } = await import("../usage-figure");

/**
 * Spec 047 — Consumo como el prototipo «Consola de partners v2»: las cifras sin
 * icono, la tabla por cliente con la moneda bajo el nombre y «Abrir ficha del
 * cliente» al final del «⋯», el periodo en el conmutador de vidrio y el detalle
 * técnico que dice qué hay dentro.
 */
const M = (n: number, currency: "EUR" | "USD" = "EUR") => ({ amount_micros: Math.round(n * 100_000), currency });
const wrap = (ui: React.ReactNode) => render(<LocaleProvider locale="es">{ui}</LocaleProvider>);
function client(over: Partial<ClientUsage> = {}): ClientUsage {
  return { ref: "flor-y-encanto", name: "Flor y Encanto", bag: M(35.5, "USD"), month_spent: M(12.4), days_left: 9, refill_up_to: null, empty: false, ...over };
}

describe("Consumo · como el prototipo", () => {
  beforeEach(() => vi.clearAllMocks());

  it("las cifras: etiqueta pequeña, cifra grande y nota, sin icono", () => {
    const { container } = wrap(<UsageFigure label="Saldo disponible" value="240,00 €" hint="Lo que puedes asignar." />);
    expect(screen.getByRole("heading", { name: "Saldo disponible" })).toBeInTheDocument();
    expect(screen.getByText("240,00 €").className).toMatch(/\btext-2xl\b/);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("una cifra puede llevar su barra (lo repartido sobre el total)", () => {
    wrap(<UsageFigure label="En bolsas de clientes" value="42,99 €" bar={{ value: 43, max: 283 }} hint="240,00 € sin asignar" />);
    const bar = document.querySelector("[data-slot=usage-figure-bar] > span") as HTMLElement;
    expect(bar.style.width).toBe("15%");
  });

  it("el periodo de «Gasto por día» es el conmutador de vidrio y cambia la URL", async () => {
    const user = userEvent.setup();
    wrap(<SpendFilters days={30} client="" line={null} clients={[{ ref: "flor", name: "Flor" }]} />);
    const period = screen.getByRole("group", { name: "Periodo" });
    expect(period).toHaveAttribute("data-slot", "segmented-control");
    expect(period.className).toMatch(/\bglass\b/);
    expect(within(period).getByRole("button", { name: "30 días" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(period).getByRole("button", { name: "7 días" }));
    expect(nav.push).toHaveBeenCalledWith("/usage?days=7#gasto", { scroll: false });
  });

  it("la tabla: la moneda de la bolsa bajo el nombre y «Abrir ficha del cliente» al final del ⋯", async () => {
    const user = userEvent.setup();
    const { container } = wrap(<UsageClientsTable canWrite days={30} clients={[client(), client({ ref: "cultor", name: "Cultor", bag: M(10) })]} />);
    const table = screen.getByRole("region", { name: "Saldo por cliente" });
    const [, first, second] = within(table).getAllByRole("row");
    expect(within(first!).getByText("USD")).toBeInTheDocument();
    expect(within(second!).getByText("EUR")).toBeInTheDocument();
    // Las cabeceras van en tipo normal, sin fondo gris.
    expect(table.querySelector("thead")!.className).not.toMatch(/bg-muted/);
    await user.click(screen.getByRole("button", { name: "Acciones de Flor y Encanto" }));
    const items = await screen.findAllByRole("menuitem");
    expect(items.at(-1)).toHaveTextContent("Abrir ficha del cliente");
    expect(items.at(-1)).toHaveAttribute("href", "/clients/flor-y-encanto");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("el detalle técnico dice qué hay dentro y gira su flecha", () => {
    const detail: UsageDetail = { since: "2026-10-01", until: "2026-10-28", rows: [] };
    wrap(<UsageDetailPanel detail={detail} names={{}} days={30} client="" />);
    const summary = document.querySelector("summary")!;
    expect(summary).toHaveTextContent("Detalle técnico: mensajes, uso del modelo y multimedia");
    expect(summary).toHaveTextContent("Lo que mide la plataforma por dentro, por cliente y medidor. Para revisar con detalle o exportar.");
    expect(summary.querySelector("svg")!.getAttribute("class")).toMatch(/group-open:rotate-180/);
  });
});
