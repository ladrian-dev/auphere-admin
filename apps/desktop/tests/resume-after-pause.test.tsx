// @vitest-environment jsdom
/**
 * Requisito 9.11 — resuelta la causa, lo pausado se reanuda **sin empezar de
 * nuevo**.
 *
 * El caso: el pool se agota a mitad de un trabajo. El turno cierra limpio —lo
 * hecho sigue arriba— y la tarea queda `pausada_por_tope`. Cuando llega el
 * lunes, o alguien compra saldo, lo pausado tiene que poder seguir: volver a
 * pedir lo mismo gastaría otra vez lo ya gastado y llegaría a otro resultado.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { blockedBy, canResume, pausedCount } from "../src/resume";
import { ResumePaused } from "../src/app/routes/resume-paused";

afterEach(cleanup);

describe("cuándo se puede reanudar", () => {
  it("con la causa resuelta, sí", () => {
    expect(canResume({ taskState: "pausada_por_tope", stillCapped: false })).toBe(true);
  });

  it("con la causa en pie, no: sería el mismo 409 con un botón delante", () => {
    expect(canResume({ taskState: "pausada_por_tope", stillCapped: true })).toBe(false);
  });

  it("y lo que no está pausado por tope no se reanuda: se sigue", () => {
    for (const state of ["en_marcha", "esperandote", "terminada", "cancelada", "caducada"] as const) {
      expect(canResume({ taskState: state, stillCapped: false }), state).toBe(false);
    }
  });

  it("mientras la causa sigue, se ofrece lo que la resuelve", () => {
    expect(blockedBy({ taskState: "pausada_por_tope", stillCapped: true })).toBe("pool_agotado");
    expect(blockedBy({ taskState: "pausada_por_tope", stillCapped: false })).toBeNull();
  });

  it("y se sabe cuántas quedaron: es lo que deja decidir si comprar saldo", () => {
    expect(
      pausedCount([
        { state: "pausada_por_tope" },
        { state: "en_marcha" },
        { state: "pausada_por_tope" },
      ]),
    ).toBe(2);
  });
});

describe("en pantalla", () => {
  it("con la causa resuelta, se ofrece reanudar", async () => {
    const onResume = vi.fn();
    render(<ResumePaused count={2} capped={false} onResume={onResume} onBuy={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /reanudar|resume/i }));
    expect(onResume).toHaveBeenCalledOnce();
  });

  it("y se dice que sigue donde se quedó, no que empieza de nuevo", () => {
    render(<ResumePaused count={1} capped={false} onResume={vi.fn()} onBuy={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toMatch(/donde se quedó|where it left off/i);
  });

  it("con la causa en pie, lo que se ofrece es resolverla", async () => {
    const onBuy = vi.fn();
    render(<ResumePaused count={1} capped onResume={vi.fn()} onBuy={onBuy} />);
    expect(screen.queryByRole("button", { name: /reanudar|resume/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /saldo|credit/i }));
    expect(onBuy).toHaveBeenCalledOnce();
  });

  it("sin nada pausado no se pinta: la ausencia se diseña", () => {
    const { container } = render(<ResumePaused count={0} capped={false} onResume={vi.fn()} onBuy={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
