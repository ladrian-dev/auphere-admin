/**
 * Requisito 10.1 — el techo del partner, en la página de Equipo.
 *
 * Tres cosas que la pantalla no puede fallar:
 *
 * 1. El techo **no** es una casilla de «permitir/prohibir»: son tres valores, y
 *    el de partida —«cada persona decide»— tiene que verse elegido, porque un
 *    grupo sin nada marcado se lee como «esto está apagado».
 * 2. Quien solo puede leerlo lo ve y se le dice **por qué** no puede tocarlo.
 *    Aquí el control deshabilitado sí se pinta, al revés que en el puesto de
 *    trabajo: el techo es información que un builder necesita para entender por
 *    qué su app le pregunta siempre.
 * 3. Si el guardado falla, el botón **vuelve** a donde estaba. Dejarlo marcado
 *    sería una pantalla que miente sobre lo que hay guardado (§V).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Misma convención que el resto de la consola: el componente es de cliente y
// las server actions arrastran `server-only`, que no existe en jsdom.
const setCeiling = vi.fn();
vi.mock("@/app/(console)/team/actions", () => ({
  setLocalExecCeilingAction: (input: { ceiling: string }) => setCeiling(input),
}));

import { LocaleProvider } from "@/i18n/client";
import type { ExecMode } from "@/lib/backend";

import { LocalExecCeiling } from "../local-exec-ceiling";

function paint(props: Partial<React.ComponentProps<typeof LocalExecCeiling>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <LocalExecCeiling ceiling={"always" as ExecMode} manage {...props} />
    </LocaleProvider>,
  );
}

const button = (name: string) => screen.getByRole("button", { name });

describe("el techo de ejecución local", () => {
  beforeEach(() => {
    setCeiling.mockReset();
    setCeiling.mockResolvedValue({ ok: true });
  });

  it("enseña los tres valores y marca el que está puesto", () => {
    paint({ ceiling: "ask" as ExecMode });
    expect(button("Cada persona decide")).toHaveAttribute("aria-pressed", "false");
    expect(button("Preguntar siempre")).toHaveAttribute("aria-pressed", "true");
    expect(button("Nadie ejecuta")).toHaveAttribute("aria-pressed", "false");
  });

  it("«cada persona decide» es un valor elegido, no la ausencia de uno", () => {
    paint({ ceiling: "always" as ExecMode });
    expect(button("Cada persona decide")).toHaveAttribute("aria-pressed", "true");
  });

  it("guarda el valor nuevo y no vuelve a guardar el que ya está puesto", async () => {
    const user = userEvent.setup();
    paint({ ceiling: "always" as ExecMode });

    await user.click(button("Preguntar siempre"));
    await waitFor(() => expect(setCeiling).toHaveBeenCalledWith({ ceiling: "ask" }));
    expect(button("Preguntar siempre")).toHaveAttribute("aria-pressed", "true");

    await user.click(button("Preguntar siempre"));
    expect(setCeiling).toHaveBeenCalledTimes(1);
  });

  it("si el guardado falla, el techo vuelve a donde estaba y se dice", async () => {
    setCeiling.mockResolvedValue({ ok: false });
    const user = userEvent.setup();
    paint({ ceiling: "always" as ExecMode });

    await user.click(button("Nadie ejecuta"));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("El techo sigue como estaba"),
    );
    expect(button("Cada persona decide")).toHaveAttribute("aria-pressed", "true");
    expect(button("Nadie ejecuta")).toHaveAttribute("aria-pressed", "false");
  });

  it("quien solo puede leerlo lo ve, deshabilitado y explicado", async () => {
    const user = userEvent.setup();
    paint({ ceiling: "ask" as ExecMode, manage: false });

    expect(button("Nadie ejecuta")).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(
      "Solo el propietario y los administradores",
    );
    // Y sigue diciendo cuál es el techo: es lo que explica por qué su app le
    // pregunta siempre.
    expect(button("Preguntar siempre")).toHaveAttribute("aria-pressed", "true");

    await user.click(button("Nadie ejecuta"));
    expect(setCeiling).not.toHaveBeenCalled();
  });

  it("dice que bajar el techo no revoca lo ya concedido", () => {
    paint();
    expect(screen.getByText(/no revoca/i)).toBeInTheDocument();
  });
});
