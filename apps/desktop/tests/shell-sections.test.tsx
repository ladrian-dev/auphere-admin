// @vitest-environment jsdom
/**
 * Requisitos 1.2, 1.3, 1.4 y 9.2 — una sola navegación, y que llegue a todo.
 *
 * El análisis de la spec encontró aquí el fallo crítico: la lista canónica
 * tenía cinco secciones de consola y la consola ofrece **diez**. Al esconder la
 * barra lateral de la consola dentro de la ventana, esas cinco áreas —inicio,
 * conocimiento, auditoría, notificaciones y claves— se quedaban sin ningún
 * camino. Este test es el que impide que vuelva a pasar desde el lado de la
 * pantalla; `nav-parity.test.ts` lo impide desde el lado de la consola.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { CONSOLE_SECTIONS } from "../src/sections";
import { Sidebar } from "../src/app/shell/sidebar";

afterEach(cleanup);

const TODOS: string[] = CONSOLE_SECTIONS.map((s) => s.permission).filter((p) => p !== null);

function pintar(over: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    active: "hoy",
    onSelect: vi.fn(),
    permissions: TODOS,
    waiting: 0,
    teammates: [],
    selectedTeammate: null,
    onSelectTeammate: vi.fn(),
    ...over,
  };
  return { ...render(<Sidebar {...props} />), props };
}

describe("la lista llega a todo lo que la consola ofrece", () => {
  it("con todos los permisos, están las diez secciones de administrar", () => {
    pintar();
    const grupo = screen.getByRole("heading", { name: /administrar|manage/i }).parentElement!;
    const entradas = within(grupo).getAllByRole("button");
    expect(entradas).toHaveLength(CONSOLE_SECTIONS.length);
  });

  it("y ninguna de ellas es un texto muerto: todas navegan", async () => {
    const { props } = pintar();
    const grupo = screen.getByRole("heading", { name: /administrar|manage/i }).parentElement!;
    for (const entrada of within(grupo).getAllByRole("button")) {
      await userEvent.click(entrada);
    }
    expect(props.onSelect).toHaveBeenCalledTimes(CONSOLE_SECTIONS.length);
  });
});

describe("lo que el rol no permite no se ofrece (§V, R9.2)", () => {
  it("sin permisos sólo queda lo que no pide ninguno", () => {
    pintar({ permissions: [] });
    const grupo = screen.getByRole("heading", { name: /administrar|manage/i }).parentElement!;
    const entradas = within(grupo).getAllByRole("button");
    expect(entradas).toHaveLength(1);
    expect(entradas[0]).toHaveTextContent(/inicio|home/i);
  });

  it("no hay entradas apagadas esperando un «no puedes»", () => {
    pintar({ permissions: [] });
    for (const boton of screen.getAllByRole("button")) {
      expect(boton).not.toBeDisabled();
      expect(boton).not.toHaveAttribute("aria-disabled", "true");
    }
  });

  it("con un permiso concreto aparece su sección y sólo la suya", () => {
    pintar({ permissions: ["billing:read"] });
    expect(screen.getByRole("button", { name: /facturación|billing/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /auditoría|audit/i })).toBeNull();
  });
});

describe("la lista marca dónde se está", () => {
  it("la sección activa se anuncia como la página actual", () => {
    pintar({ active: "consumo" });
    expect(screen.getByRole("button", { name: /consumo|usage/i })).toHaveAttribute("aria-current", "page");
  });

  it("sólo una a la vez", () => {
    pintar({ active: "consumo" });
    const marcadas = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "page");
    expect(marcadas).toHaveLength(1);
  });

  it("un teammate seleccionado se marca él, no la sección", () => {
    pintar({
      active: "teammate",
      selectedTeammate: "t1",
      teammates: [
        { id: "t1", name: "Sofía", unread: false },
        { id: "t2", name: "Marco", unread: true },
      ],
    });
    expect(screen.getByRole("button", { name: /Sofía/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /Marco/ })).not.toHaveAttribute("aria-current");
  });
});

describe("lo que espera se ve sin abrir nada", () => {
  it("el número aparece junto a Pendientes", () => {
    pintar({ waiting: 3 });
    expect(screen.getByRole("button", { name: /pendientes|pending/i })).toHaveTextContent("3");
  });

  it("y sin nada esperando no hay número: la ausencia se diseña", () => {
    pintar({ waiting: 0 });
    expect(screen.getByRole("button", { name: /pendientes|pending/i })).not.toHaveTextContent(/\d/);
  });
});
