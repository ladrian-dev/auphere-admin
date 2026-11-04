import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { runFailedKey } from "../quality-model";
import { estimateCents, useRunEstimate, type EstimateRun } from "../run-estimate";

const IDS = { ref: "r", agent: "a" };

function Harness({ estimate, start }: { estimate?: EstimateRun; start: (scope: string) => void }) {
  const { ask, dialog } = useRunEstimate({ estimate, ids: IDS, start });
  return (
    <>
      <button type="button" onClick={() => void ask("all")}>
        Ejecutar todas
      </button>
      {dialog}
    </>
  );
}

function view(estimate: EstimateRun | undefined, start = vi.fn()) {
  render(
    <LocaleProvider locale="es">
      <Harness estimate={estimate} start={start} />
    </LocaleProvider>,
  );
  return start;
}

describe("el coste antes de una pasada (61.8)", () => {
  it("dice cuánto costará y solo arranca al confirmar", async () => {
    const start = view(async () => ({
      ok: true,
      data: { tests: 18, estimate: { amount_micros: 1_250_000, currency: "USD" }, unknown_prices: [] },
    }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("¿Ejecutar 18 pruebas?")).toBeInTheDocument();
    expect(screen.getByText(/Costará aproximadamente 1,25/)).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
  });

  it("sin precio de un modelo lo dice, y no enseña un cero", async () => {
    view(async () => ({ ok: true, data: { tests: 1, estimate: null, unknown_prices: ["m"] } }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    expect(await screen.findByText("¿Ejecutar 1 prueba?")).toBeInTheDocument();
    expect(screen.getByText(/No podemos estimar/)).toBeInTheDocument();
  });

  it("si no se puede estimar, la pasada dice qué pasa", async () => {
    const start = view(async () => ({ ok: false, status: 402, message: "", code: "build_budget_exhausted" }));
    await userEvent.click(screen.getByRole("button", { name: "Ejecutar todas" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("all"));
  });

  it("una pasada que cuesta algo nunca se lee como nada", () => {
    expect(estimateCents({ amount_micros: 100, currency: "USD" })).toBe(1);
    expect(estimateCents(null)).toBeNull();
  });
});

describe("por qué no terminó una pasada (INC-67)", () => {
  it("sin partida no dice «inténtalo de nuevo»", () => {
    expect(runFailedKey("build_budget_exhausted")).toBe("money.build.blocked");
    expect(runFailedKey("internal")).toBe("builder.suite.error.run");
  });
});
