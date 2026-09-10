/**
 * Requisito 6 (spec 002) — la puesta en marcha guiada.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { SetupOut } from "@/lib/backend/workstation";

import { WorkstationSetupCard } from "../workstation-setup-card";

const setup = (over: Partial<SetupOut> = {}): SetupOut => ({
  complete: false,
  steps: [
    { key: "paired", done: true, pending: 0 },
    { key: "clients", done: true, pending: 0 },
    { key: "directories", done: false, pending: 2 },
    { key: "executables", done: false, pending: 1 },
  ],
  ...over,
});

function card(data: SetupOut | null) {
  return render(
    <LocaleProvider locale="es">
      <WorkstationSetupCard setup={data} />
    </LocaleProvider>,
  );
}

describe("la tarjeta de puesta en marcha", () => {
  it("cuatro pasos, con lo pendiente contado y los hechos tachados (6.1)", () => {
    card(setup());
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByText(/2 de 4 pasos/i)).toBeInTheDocument();
    expect(screen.getByText(/2 pendiente/i)).toBeInTheDocument();
    expect(screen.getByText(/ejecutables habilitados por auphere/i)).toBeInTheDocument();
    expect(screen.getByText(/pídelo desde la página del cliente/i)).toBeInTheDocument();
  });

  it("se cierra y no bloquea; no se persiste nada (6.3)", () => {
    card(setup());
    fireEvent.click(screen.getByRole("button", { name: /cerrar por ahora/i }));
    expect(screen.queryByText(/tu puesto de trabajo/i)).not.toBeInTheDocument();
    expect(Object.keys(window.localStorage)).toEqual([]);
  });

  it("con los cuatro en verde no se renderiza, y no hay control para verla (6.4)", () => {
    const { container } = card(setup({ complete: true, steps: setup().steps.map((s) => ({ ...s, done: true, pending: 0 })) }));
    expect(container).toBeEmptyDOMElement();
  });

  it("si no se pudo calcular, lo dice como error y no inventa pasos", () => {
    card(null);
    expect(screen.getByRole("alert")).toHaveTextContent(/no se pudo comprobar/i);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("los pasos de ejecutables no ofrecen añadirlos: se piden (6.6)", () => {
    card(setup());
    expect(screen.queryByRole("button", { name: /añadir ejecutable/i })).not.toBeInTheDocument();
  });
});
