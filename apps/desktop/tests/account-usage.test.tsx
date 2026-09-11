// @vitest-environment jsdom
/**
 * Requisitos 8 y 9.3 — Cuenta: el mismo número, el equipo y el tope.
 *
 * La pantalla que más fácil miente. Tres cosas se comprueban con nombre propio:
 *
 * * **El número es el del medidor.** Cuenta no calcula nada: pinta lo que la
 *   plataforma dice. Si el desglose por teammate no cuadra con el total —porque
 *   parte del gasto vino del Companion de la consola— lo dice en vez de dejar
 *   dos cifras que no suman.
 * * **El tope alcanzado es un estado, no un error** (§V): el trabajo está en
 *   pausa, los hilos siguen vivos, y se dice **dónde** se sube.
 * * **El equipo se lee, no se administra**: los roles se ven y no hay ningún
 *   control apagado invitando a pelearse con él.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { LangProvider } from "../src/app/i18n";
import { Account, type AccountProps } from "../src/app/routes/account";

afterEach(cleanup);

const BUDGET = {
  used: 120_000,
  cap: 1_000_000,
  remaining: 880_000,
  percent: 12,
  exhausted: false,
  period: "2026-09",
  resets_at: "2026-10-01T00:00:00Z",
};

const USAGE = {
  budget: BUDGET,
  by_teammate: [
    { teammate_id: "t-1", name: "Sofía", input_tokens: 60_000, output_tokens: 20_000, runs: 12 },
    { teammate_id: "t-2", name: "Nilo", input_tokens: 30_000, output_tokens: 10_000, runs: 4 },
  ],
};

const TEAM = {
  members: [
    { id: "m-1", email: "ana@partner.com", display_name: "Ana", role: "owner", status: "active", is_you: true },
    { id: "m-2", email: "leo@partner.com", display_name: null, role: "builder", status: "active", is_you: false },
  ],
};

const POLICY = {
  ceiling: "always" as const,
  global_mode: "ask" as const,
  per_executable: [],
  effective: "ask" as const,
  capped: false,
};

function paint(props: Partial<AccountProps> = {}) {
  const onRetry = vi.fn();
  const onOpenConsole = vi.fn();
  render(
    <LangProvider value="es">
      <Account
        status="ready"
        usage={USAGE}
        team={TEAM}
        policy={POLICY}
        onRetry={onRetry}
        onOpenConsole={onOpenConsole}
        {...props}
      />
    </LangProvider>,
  );
  return { onRetry, onOpenConsole };
}

describe("el consumo del mes", () => {
  it("pinta el número de la plataforma, no uno propio", () => {
    paint();
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "120000");
    expect(meter).toHaveAttribute("aria-valuemax", "1000000");
    expect(screen.getByText(/120.000/)).toBeInTheDocument();
  });

  it("reparte por teammate y dice qué parte no es de ninguno", () => {
    // 120.000 usados, 80.000 + 40.000 repartidos: cuadra, y se dice.
    paint();
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByText("Sofía")).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/80.000/)).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Nilo")).toBeInTheDocument();
  });

  it("cuando parte del gasto no es de ningún teammate, lo explica", () => {
    // El Companion de la consola gasta del mismo medidor (R9.1). Sin esta
    // frase, la resta entre el total y el desglose parecería un fallo.
    paint({ usage: { budget: { ...BUDGET, used: 150_000 }, by_teammate: USAGE.by_teammate } });
    expect(screen.getByText(/desde la consola/i)).toBeInTheDocument();
  });

  it("sin gasto de teammates aún, el vacío explica cuándo aparece algo", () => {
    paint({ usage: { budget: { ...BUDGET, used: 0, percent: 0, remaining: BUDGET.cap }, by_teammate: [] } });
    expect(screen.getByText(/ningún teammate ha gastado/i)).toBeInTheDocument();
  });

  it("el tope alcanzado es un estado y dice dónde se sube", () => {
    const { onOpenConsole } = paint({
      usage: {
        budget: { ...BUDGET, used: BUDGET.cap, remaining: 0, percent: 100, exhausted: true },
        by_teammate: USAGE.by_teammate,
      },
    });

    const notice = screen.getByRole("status", { name: /tope/i });
    expect(notice).toHaveTextContent(/en pausa/i);
    expect(notice).toHaveTextContent(/hilos/i);
    expect(notice).toHaveTextContent(/consola/i);
    // Y no se pinta como error: nada roto, solo parado.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onOpenConsole).not.toHaveBeenCalled();
  });
});

describe("el equipo", () => {
  it("enseña los roles y dice que se administran en la consola", () => {
    paint();
    // Quien no tiene nombre se identifica por su correo: es lo único que hay,
    // y una fila sin nada que la identifique no sirve para leer un equipo.
    const ana = screen.getByText(/Ana/).closest("li")!;
    expect(within(ana).getByText(/propietario/i)).toBeInTheDocument();
    expect(within(ana).getByText(/tú/i)).toBeInTheDocument();
    const leo = screen.getByText(/leo@partner.com/).closest("li")!;
    expect(within(leo).getByText(/constructor/i)).toBeInTheDocument();
    expect(screen.getByText(/se administra en la consola/i)).toBeInTheDocument();
  });

  it("no hay ni un control para cambiar un rol", () => {
    paint();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    for (const button of screen.getAllByRole("button")) {
      expect(button).not.toBeDisabled();
    }
  });

  it("si no se pudo leer el equipo, se dice sin romper la pantalla", () => {
    paint({ team: null });
    expect(screen.getByText(/no se pudo leer el equipo/i)).toBeInTheDocument();
    // El resto de Cuenta sigue en pie.
    expect(screen.getByRole("meter")).toBeInTheDocument();
  });
});

describe("la política de esta máquina", () => {
  it("dice lo que se aplica de verdad", () => {
    paint();
    expect(screen.getByText(/preguntar/i)).toBeInTheDocument();
  });

  it("cuando el techo del partner acota, lo dice y dice dónde se cambia", () => {
    paint({ policy: { ...POLICY, ceiling: "ask", global_mode: "always", effective: "ask", capped: true } });
    const note = screen.getByRole("status", { name: /ejecución/i });
    expect(note).toHaveTextContent(/techo/i);
    expect(note).toHaveTextContent(/consola|administrador/i);
  });
});

describe("las dos puertas a la consola", () => {
  it("«abrir la consola» la abre", async () => {
    const user = userEvent.setup();
    const { onOpenConsole } = paint();
    await user.click(screen.getByRole("button", { name: /abrir la consola/i }));
    expect(onOpenConsole).toHaveBeenCalledWith("/");
  });

  it("«cerrar sesión» no inventa otra sesión: abre la de la consola", async () => {
    const user = userEvent.setup();
    const { onOpenConsole } = paint();
    await user.click(screen.getByRole("button", { name: /cerrar sesión/i }));
    expect(onOpenConsole).toHaveBeenCalledWith("/");
    expect(screen.getByText(/tu sesión es la de la consola/i)).toBeInTheDocument();
  });
});

describe("los estados de la pantalla", () => {
  it("mientras carga no enseña cifras a medias", () => {
    paint({ status: "loading", usage: null, team: null, policy: null });
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  it("si el consumo no se pudo leer, ofrece reintentar", async () => {
    const user = userEvent.setup();
    const { onRetry } = paint({ status: "error", usage: null });
    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
