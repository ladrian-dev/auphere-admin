import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { runFailedKey, runRefusedKey } from "../quality-model";
import { questionFor, useRunEstimate, type EstimateRun } from "../run-estimate";

const IDS = { ref: "r", agent: "a" };

function Harness({ estimate, start, goTo }: { estimate?: EstimateRun; start: (scope: string, confirmedTests?: number) => void; goTo?: (href: string) => void }) {
  const { ask, dialog } = useRunEstimate({ estimate, ids: IDS, start, goTo });
  return (
    <>
      <button type="button" onClick={() => void ask("all")}>
        Ejecutar todas
      </button>
      {dialog}
    </>
  );
}

function view(estimate: EstimateRun | undefined, start = vi.fn(), goTo = vi.fn()) {
  render(
    <LocaleProvider locale="es">
      <Harness estimate={estimate} start={start} goTo={goTo} />
    </LocaleProvider>,
  );
  return { start, goTo };
}

const usd = (units: number) => ({ amount_micros: units * 100_000, currency: "USD" as const });
const data = (over: Partial<Parameters<typeof questionFor>[0]>) => ({ ok: true as const, data: { tests: 8, unknown_prices: [], payer: "auphere" as const, charge: usd(1), left: usd(30), fits: true, ...over } });

describe("el coste antes de una pasada (61.8, 66.5 y 68)", () => {
  it("la que paga Auphere y cabe arranca sin preguntar", async () => {
    const { start } = view(async () => data({}));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
    expect(screen.queryByText(/Costaría/)).not.toBeInTheDocument();
  });

  it("la que paga Auphere y no cabe lo dice, en la unidad de verdad", async () => {
    const { start } = view(async () => data({ tests: 18, charge: usd(6), left: usd(5), fits: false }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("¿Ejecutar 18 pruebas?")).toBeInTheDocument();
    expect(screen.getByText(/Costaría unos 6,00.*te quedan 5,00/)).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
  });

  it("la que paga la bolsa siempre pregunta, y confirma el cobro", async () => {
    const { start } = view(async () => data({ payer: "client_bag", charge: usd(2), left: usd(10) }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("¿Ejecutar 8 pruebas con cargo al cliente?")).toBeInTheDocument();
    expect(screen.getByText(/ya pagó la primera pasada.*unos 2,00.*Ahora tiene 10,00/)).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar y cobrar" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all", 8));
  });

  it("si la bolsa no llega no arranca: ofrece asignar saldo a ese cliente", async () => {
    const { start, goTo } = view(async () => data({ payer: "client_bag", charge: usd(2), left: usd(1), fits: false }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("No hay saldo suficiente")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ver el saldo del cliente" }));
    expect(goTo).toHaveBeenCalledWith("/clients/r?assign=1");
    expect(start).not.toHaveBeenCalled();
  });

  it("sin precio no se cobra a ciegas, y asignar saldo no lo arreglaría", async () => {
    const { start, goTo } = view(async () => data({ payer: "client_bag", charge: null, fits: false, unknown_prices: ["m"] }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("No se puede calcular el coste")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Entendido" }));
    expect(start).not.toHaveBeenCalled();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("un doble clic no estima dos veces", async () => {
    let answer = (_: ReturnType<typeof data>) => {};
    const estimate = vi.fn(() => new Promise<ReturnType<typeof data>>((resolve) => (answer = resolve)));
    view(estimate);
    await userEvent.dblClick(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(estimate).toHaveBeenCalledTimes(1);
    answer(data({ payer: "client_bag" }));
    await screen.findByText("¿Ejecutar 8 pruebas con cargo al cliente?");
  });

  it("al cerrar no cambia el texto mientras se va", async () => {
    view(async () => data({ payer: "client_bag" }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    await screen.findByText("¿Ejecutar 8 pruebas con cargo al cliente?");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByText("¿Ejecutar 0 pruebas?")).not.toBeInTheDocument();
  });

  it("la que paga Auphere sin precio no enseña un cero: arranca", async () => {
    const { start } = view(async () => data({ charge: null, unknown_prices: ["m"] }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
  });

  it("si no se puede estimar, la pasada dice qué pasa", async () => {
    const { start } = view(async () => ({ ok: false, status: 402, message: "", code: "build_budget_exhausted" }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
  });
});

describe("por qué no terminó una pasada (INC-67)", () => {
  it("sin partida no dice «inténtalo de nuevo»", () => {
    expect(runFailedKey("build_budget_exhausted")).toBe("money.build.blocked");
    expect(runFailedKey("internal")).toBe("builder.suite.error.run");
  });

  it("con la bolsa justa dice por qué se paró", () => {
    expect(runFailedKey("client_bag_low")).toBe("builder.suite.error.bagLow");
    expect(runRefusedKey({ status: 402, code: "client_bag_not_enough" })).toBe("builder.suite.error.bag");
    expect(runRefusedKey({ status: 402, code: "build_budget_exhausted" })).toBe("money.build.blocked");
    expect(runRefusedKey({ status: 409, code: "charge_not_confirmed" })).toBe("builder.suite.error.charge");
    expect(runRefusedKey({ status: 409, code: "charge_changed" })).toBe("builder.suite.error.charge");
    expect(runRefusedKey({ status: 409, code: "charge_unknown" })).toBe("builder.suite.noPrice.body");
  });
});
