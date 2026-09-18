// @vitest-environment jsdom
/**
 * Requisito 11 — controles que dicen lo que son, y que se pueden acertar.
 *
 * Dos defectos concretos:
 *
 * * **la política de ejecución local son tres interruptores** —«Preguntar»,
 *   «Permitir siempre», «Nunca»— cuando en realidad es **una elección entre
 *   tres**. Anunciados como tres `aria-pressed` sueltos, un lector de pantalla
 *   dice «botón, no presionado» tres veces y no dice que elegir uno apaga los
 *   otros;
 * * **objetivos por debajo de 24 × 24** (WCAG 2.2, 2.5.8). El botón de crear
 *   teammate era de 28 px y el punto de estado, de 8.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import type { LocalExecPolicy } from "../src/app/bridge";
import { LocalExecPolicySection } from "../src/app/routes/env";
import { FeedbackProvider } from "../src/app/feedback/provider";

vi.mock("../src/app/bridge", () => ({
  bridge: { policyPrefs: async () => ({ ok: true, data: POLICY }), policySetPref: async () => ({ ok: true, data: POLICY }) },
}));

const POLICY: LocalExecPolicy = {
  global_mode: "ask",
  effective: "ask",
  ceiling: "always",
  capped: false,
  per_executable: [],
};

afterEach(cleanup);

describe("una elección entre tres se anuncia como tal (4.1.2)", () => {
  it("es un grupo de radios, no tres interruptores sueltos", () => {
    render(
      <FeedbackProvider>
        <LocalExecPolicySection initial={POLICY} />
      </FeedbackProvider>,
    );
    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("y exactamente uno está marcado: elegir uno apaga los otros", () => {
    render(
      <FeedbackProvider>
        <LocalExecPolicySection initial={POLICY} />
      </FeedbackProvider>,
    );
    const marcados = screen.getAllByRole("radio").filter((r) => r.getAttribute("aria-checked") === "true");
    expect(marcados).toHaveLength(1);
  });

  it("ya no queda ningún `aria-pressed` fingiendo ser una elección", () => {
    const { container } = render(
      <FeedbackProvider>
        <LocalExecPolicySection initial={POLICY} />
      </FeedbackProvider>,
    );
    expect(container.querySelector("[aria-pressed]")).toBeNull();
  });

  it("el grupo tiene nombre, o no se sabe de qué se elige", () => {
    render(
      <FeedbackProvider>
        <LocalExecPolicySection initial={POLICY} />
      </FeedbackProvider>,
    );
    expect(screen.getByRole("radiogroup")).toHaveAttribute("aria-label");
  });
});

describe("los objetivos llegan a 24 × 24 (2.5.8)", () => {
  /** Las clases de altura que Tailwind traduce a menos de 24 px. */
  const PEQUEÑAS = /\b(?:min-)?h-[0-5]\b|\bsize-[0-5]\b/;

  it("ninguna opción de la política es menor que el mínimo", () => {
    const { container } = render(
      <FeedbackProvider>
        <LocalExecPolicySection initial={POLICY} />
      </FeedbackProvider>,
    );
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio.className, radio.textContent ?? "").not.toMatch(PEQUEÑAS);
    }
    expect(container).toBeTruthy();
  });
});
