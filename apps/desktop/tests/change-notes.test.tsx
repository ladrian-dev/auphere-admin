// @vitest-environment jsdom
/**
 * Requisito 2.4 — la nota de cambio, dentro del hilo.
 *
 * Lo que se comprueba aquí es lo que la nota **no** dice: no lleva valores, no
 * inventa un autor cuando no consta, y no aparece cuando no hubo cambios. Una
 * franja vacía con el título «Cambios de este teammate» diría que hubo alguno.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import "./dom-matchers";

import { LangProvider } from "../src/app/i18n";
import { ChangeNotes } from "../src/app/routes/change-notes";

afterEach(cleanup);

const change = (over: Partial<Parameters<typeof ChangeNotes>[0]["changes"][number]> = {}) => ({
  id: "11111111-2222-4333-8444-555555555555",
  fields: ["job"] as Array<"job" | "permissions" | "local_exec" | "model">,
  by: "Ana",
  at: "2026-09-11T09:00:00Z",
  ...over,
});

const paint = (changes: Parameters<typeof ChangeNotes>[0]["changes"]) =>
  render(
    <LangProvider value="es">
      <ChangeNotes changes={changes} />
    </LangProvider>,
  );

describe("las notas de cambio", () => {
  it("sin cambios no pinta nada, ni el título", () => {
    const { container } = paint([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("dice qué cambió, quién y cuándo", () => {
    paint([change()]);
    const line = screen.getByRole("listitem");
    expect(line).toHaveTextContent(/cambió el oficio/i);
    expect(line).toHaveTextContent(/por Ana/i);
    expect(line).toHaveTextContent(/11 sept/i);
  });

  it("varios campos se leen como una frase, no como una lista de claves", () => {
    paint([change({ fields: ["job", "permissions", "model"] })]);
    expect(screen.getByRole("listitem")).toHaveTextContent(
      /el oficio, los permisos y el modelo/i,
    );
    // Y nunca el identificador crudo de la columna.
    expect(screen.getByRole("listitem")).not.toHaveTextContent("permissions");
  });

  it("sin autor no se inventa uno", () => {
    paint([change({ by: null })]);
    expect(screen.getByRole("listitem")).not.toHaveTextContent(/por /i);
  });

  it("cada cambio es una línea, en el orden en que ocurrieron", () => {
    paint([change(), change({ id: "22222222-2222-4333-8444-555555555555", fields: ["model"] })]);
    const lines = screen.getAllByRole("listitem");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent(/el oficio/i);
    expect(lines[1]).toHaveTextContent(/el modelo/i);
  });
});
