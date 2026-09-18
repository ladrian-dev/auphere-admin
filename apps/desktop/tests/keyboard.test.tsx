// @vitest-environment jsdom
/**
 * Requisito 11 — el teclado alcanza todo, y el armazón tiene zonas.
 *
 * Una ventana con franja, lista lateral y panel tiene tres zonas, y tabular de
 * una a otra puede costar treinta pulsaciones. macOS resuelve eso con **F6 y
 * ⇧F6**, y es la convención que la guía de escritorio pide: saltar de zona, no
 * recorrerla.
 *
 * Lo que este test vigila, además, es lo que se degrada solo: una región sin
 * nombre no se puede elegir en el rotor de VoiceOver, y una acción que sólo
 * llega con el ratón no llega.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { LANDMARKS, nextLandmark } from "../src/app/shell/landmarks";
import { Sidebar } from "../src/app/shell/sidebar";
import { WorkstationActions } from "../src/app/shell/workstation-actions";

afterEach(cleanup);

describe("las zonas del armazón, y el salto entre ellas", () => {
  it("son tres, en el orden en que se leen", () => {
    expect([...LANDMARKS]).toEqual(["franja", "lateral", "panel"]);
  });

  it("F6 avanza y da la vuelta", () => {
    expect(nextLandmark("franja", 1)).toBe("lateral");
    expect(nextLandmark("lateral", 1)).toBe("panel");
    expect(nextLandmark("panel", 1)).toBe("franja");
  });

  it("⇧F6 retrocede y también da la vuelta", () => {
    expect(nextLandmark("franja", -1)).toBe("panel");
    expect(nextLandmark("panel", -1)).toBe("lateral");
  });

  it("y desde ninguna zona conocida se entra por la primera", () => {
    expect(nextLandmark(null, 1)).toBe("franja");
  });
});

describe("el estado del puesto se alcanza con el teclado (8.1)", () => {
  it("sus acciones son botones, no un adorno del pie", async () => {
    const onAction = vi.fn();
    render(
      <WorkstationActions
        state={{ status: "sin_emparejar", actions: ["introducir_codigo"], clients: [] }}
        onAction={onAction}
      />,
    );
    await userEvent.tab();
    expect(document.activeElement?.textContent).toMatch(/emparejar/i);
    await userEvent.keyboard("{Enter}");
    expect(onAction).toHaveBeenCalledWith("introducir_codigo");
  });
});

describe("la lista lateral se recorre entera con el teclado", () => {
  it("cada entrada es un botón, y ninguna se salta el orden de tabulación", () => {
    render(
      <Sidebar
        active="hoy"
        onSelect={vi.fn()}
        permissions={["clients:read"]}
        waiting={0}
        teammates={[{ id: "t-1", name: "Sofía", unread: false }]}
        rosterStatus="ready"
        selectedTeammate={null}
        onSelectTeammate={vi.fn()}
      />,
    );
    for (const boton of screen.getAllByRole("button")) {
      expect(boton).not.toHaveAttribute("tabindex", "-1");
    }
  });

  it("y las zonas tienen nombre: sin él no se eligen en el rotor", () => {
    const { container } = render(
      <Sidebar
        active="hoy"
        onSelect={vi.fn()}
        permissions={[]}
        waiting={0}
        teammates={[]}
        rosterStatus="empty"
        selectedTeammate={null}
        onSelectTeammate={vi.fn()}
      />,
    );
    expect(container.querySelector("nav")).toHaveAttribute("aria-label");
  });
});
