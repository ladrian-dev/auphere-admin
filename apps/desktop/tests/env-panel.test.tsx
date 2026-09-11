// @vitest-environment jsdom
/**
 * Requisito 11 — el panel de entorno: dónde trabaja el teammate.
 *
 * Tres cosas que la pantalla no puede fingir:
 *
 * * **`archivos` es lo que los comandos nombraron**, no lo que se escribió. La
 *   plataforma nunca recibe esa lista (§III) y la aplicación no mira el disco;
 *   la etiqueta lo dice con esas palabras, porque «Archivos» a secas se leería
 *   como un listado del directorio.
 * * **`navegador` es una ausencia diseñada**: una frase, nunca un botón apagado
 *   ni un error.
 * * **Sin máquina o sin directorio, se lleva a la puesta en marcha de la 002**,
 *   no se repite aquí: dos sitios donde emparejar es uno que miente.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { LangProvider } from "../src/app/i18n";
import { EnvPanel, type EnvPanelProps } from "../src/app/routes/env";

afterEach(cleanup);

const TEAMMATE = {
  id: "t-1",
  name: "Nilo",
  job: "Desarrollo",
  model: "openai/gpt-5.6-sol",
  tool_names: [],
  permissions: { read: true, write: false, spend: false, publish: false, contact: false },
  local_exec: false,
  status: "active" as const,
  my_state: "en_espera" as const,
  my_unread: false,
  my_thread_id: "th-1",
  last_done: null,
};

const ENV = {
  machine: { displayName: "MacBook de Ana", hostname: "mac.local" },
  presence: "presente" as const,
  links: [{ clientRef: "cultor", clientName: "Cultor Barber", workdir: "/Users/ana/cultor" }],
  task_id: "task-1",
  files: ["backend", "src/app/main.tsx"],
};

function paint(props: Partial<EnvPanelProps> = {}) {
  const onOpenConsole = vi.fn();
  render(
    <LangProvider value="es">
      <EnvPanel teammate={TEAMMATE} env={ENV} policy={null} onOpenConsole={onOpenConsole} {...props} />
    </LangProvider>,
  );
  return { onOpenConsole };
}

describe("dónde trabaja", () => {
  it("dice la máquina, el cliente y su directorio", () => {
    paint();
    expect(screen.getByText(/MacBook de Ana/)).toBeInTheDocument();
    expect(screen.getByText(/Cultor Barber/)).toBeInTheDocument();
    expect(screen.getByText("/Users/ana/cultor")).toBeInTheDocument();
  });

  it("la máquina apagada es un estado, no un error", () => {
    paint({ env: { ...ENV, presence: "ausente" } });
    expect(screen.getByText(/sin conectar/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("los archivos de la tarea", () => {
  it("se llaman por lo que son: lo que los comandos nombraron", () => {
    paint();
    const section = screen.getByRole("region", { name: /nombraron/i });
    expect(section).toHaveTextContent("src/app/main.tsx");
    expect(section).toHaveTextContent("backend");
  });

  it("no se abren desde aquí: son referencia", () => {
    paint();
    const section = screen.getByRole("region", { name: /nombraron/i });
    expect(section.querySelector("a")).toBeNull();
    expect(section.querySelector("button")).toBeNull();
  });

  it("sin comandos todavía, no se pinta la sección vacía", () => {
    paint({ env: { ...ENV, files: [] } });
    expect(screen.queryByRole("region", { name: /nombraron/i })).not.toBeInTheDocument();
  });
});

describe("lo que todavía no hay", () => {
  it("el navegador se dice, no se apaga", () => {
    paint();
    expect(screen.getByText(/todavía no/i)).toBeInTheDocument();
    for (const button of screen.getAllByRole("button")) expect(button).not.toBeDisabled();
  });
});

describe("cuando falta la máquina o el directorio", () => {
  it("sin máquina emparejada lleva a la puesta en marcha, no la repite", async () => {
    const user = userEvent.setup();
    const { onOpenConsole } = paint({ env: { ...ENV, machine: null, links: [] } });

    expect(screen.getByText(/no hay ninguna máquina/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /puesta en marcha|emparejar/i }));
    expect(onOpenConsole).toHaveBeenCalledWith("/workstation");
    // Y aquí no se empareja: no hay código, ni campo, ni botón de emparejar.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("con máquina pero sin directorio para el cliente, también lleva allí", async () => {
    const user = userEvent.setup();
    const { onOpenConsole } = paint({
      env: { ...ENV, links: [{ clientRef: "cultor", clientName: "Cultor Barber", workdir: null }] },
    });

    // La sección de puesta en marcha, no el campo: el campo dice el estado
    // («Sin directorio declarado») y esta dice qué hacer con él.
    const setup = screen.getByRole("region", { name: /puesta en marcha/i });
    expect(setup).toHaveTextContent(/sin directorio declarado/i);
    await user.click(within(setup).getByRole("button", { name: /puesta en marcha|declarar/i }));
    expect(onOpenConsole).toHaveBeenCalledWith("/workstation");
  });
});

describe("mientras no se sabe", () => {
  it("sin datos del entorno todavía, no se inventa ninguno", () => {
    paint({ env: null });
    expect(screen.queryByText(/MacBook/)).not.toBeInTheDocument();
    // El oficio y el modelo del teammate sí se saben sin preguntar a la máquina.
    expect(screen.getByText("Desarrollo")).toBeInTheDocument();
  });
});
