// @vitest-environment jsdom
/**
 * Requisito 9.3 — el tope se dice **antes** de rellenar nada.
 *
 * Lo que el anexo 04 anotó: «el tope del plan se descubre al enviar». Nombre,
 * oficio, cerebro, seis permisos y un interruptor de ejecución local — y
 * entonces «tu plan admite 0 teammates». Todo ese trabajo tirado, y la frase
 * llega en el peor momento posible: cuando ya decidiste.
 *
 * Y el segundo caso, más fino: el interruptor de **ejecución local** cuando el
 * plan no la incluye. Un interruptor que se puede mover y luego no hace nada es
 * peor que no tenerlo (§V).
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { CapNotice } from "../src/app/routes/cap-notice";

afterEach(cleanup);

describe("sin plan que admita teammates, el formulario no se llega a ofrecer", () => {
  it("se dice qué pasa y se lleva a resolverlo", async () => {
    const onGo = vi.fn();
    render(<CapNotice cap="sin_plan" permissions={["billing:manage"]} onGo={onGo} onCancel={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toMatch(/no incluye teammates|includes no teammates/i);
    await userEvent.click(screen.getByRole("button", { name: /elegir un plan|choose a plan/i }));
    expect(onGo).toHaveBeenCalledWith({ kind: "section", section: "cuenta" });
  });

  it("no hay ni un campo del formulario a la vista", () => {
    const { container } = render(
      <CapNotice cap="sin_plan" permissions={["billing:manage"]} onGo={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("form")).toBeNull();
  });

  it("y siempre se puede volver sin haber hecho nada", async () => {
    const onCancel = vi.fn();
    render(<CapNotice cap="sin_plan" permissions={["billing:manage"]} onGo={vi.fn()} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole("button", { name: /cancelar|cancel/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe("con el plan lleno, lo mismo pero con otra salida", () => {
  it("dice que está lleno y que archivar también vale", () => {
    render(<CapNotice cap="plan_lleno" permissions={["billing:manage"]} onGo={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toMatch(/archiva|archive/i);
  });
});

describe("sin permiso para contratar, se dice a quién pedirlo (9.2)", () => {
  it("y no se ofrece la acción de pagar", () => {
    render(<CapNotice cap="sin_plan" permissions={[]} onGo={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toMatch(/facturación|billing/i);
    // Sólo queda cancelar: lo que no puede hacer, no se le ofrece.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
