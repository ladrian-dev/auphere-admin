// @vitest-environment jsdom
/**
 * Requisitos 9.2, 9.6, 9.7 y 9.9 — el plan en Cuenta.
 *
 * Lo que Cuenta no tenía, y por eso ningún tope llevaba a ninguna parte: el
 * plan. «Cambia de plan, en Cuenta» mandaba a una pantalla donde no había plan.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { NEAR_LIMIT, Plan } from "../src/app/routes/plan";
import type { Membership } from "../src/app/bridge";

afterEach(cleanup);

const TIER = {
  code: "pro",
  display_name: "Pro",
  monthly_price_cents: 9900,
  max_teammates: 5,
  max_members: 10,
  consumption_multiple: 4,
};

const MEMBRESIA: Membership = {
  tier: TIER,
  state: "current",
  current_period_end: "2026-10-01T00:00:00Z",
  pending_tier: null,
  usage: { teammates: 2, members: 3 },
  purchased_expires_at: null,
  catalog: [TIER],
};

const PUEDE = ["billing:manage"];
const NO_PUEDE: string[] = [];

const pintar = (over: Partial<React.ComponentProps<typeof Plan>> = {}) =>
  render(
    <Plan
      membership={MEMBRESIA}
      percent={12}
      resetsAt="2026-09-22T00:00:00Z"
      permissions={PUEDE}
      onGo={vi.fn()}
      {...over}
    />,
  );

describe("proporción y fecha, nunca la cifra del pool (9.6)", () => {
  it("dice el porcentaje y cuándo se reinicia", () => {
    pintar();
    expect(screen.getByText(/12 %/)).toBeInTheDocument();
    expect(screen.getByText(/22 de septiembre/)).toBeInTheDocument();
  });

  it("y no enseña ningún número de tokens", () => {
    const { container } = pintar();
    // El tamaño del pool es provisional: imprimirlo convierte cada ajuste en
    // un recorte o un regalo público.
    expect(container.textContent).not.toMatch(/\d{4,}\s*(tokens|créditos)/i);
  });

  it("el saldo comprado sí se dice: es dinero que se pagó", () => {
    pintar({ membership: { ...MEMBRESIA, purchased_expires_at: "2026-12-01T00:00:00Z" } });
    expect(screen.getByText(/saldo comprado/i)).toBeInTheDocument();
  });
});

describe("el aviso llega antes de agotarse (9.7)", () => {
  it("al 80 % se avisa", () => {
    pintar({ percent: NEAR_LIMIT });
    expect(screen.getByText(/Vas por el 80 %/)).toBeInTheDocument();
  });

  it("por debajo, no: un aviso permanente se aprende a ignorar", () => {
    pintar({ percent: NEAR_LIMIT - 1 });
    expect(screen.queryByText(/Vas por el/)).toBeNull();
  });

  it("y el aviso dice cuándo vuelve, no sólo que se acaba", () => {
    pintar({ percent: 92 });
    expect(screen.getByText(/Vas por el 92 %.*22 de septiembre/)).toBeInTheDocument();
  });
});

describe("un cobro degradado se dice antes de notarse (9.9)", () => {
  it("con el cobro pendiente, se dice", () => {
    pintar({ membership: { ...MEMBRESIA, state: "past_due" } });
    expect(screen.getByText(/cobro pendiente/i)).toBeInTheDocument();
  });

  it("y lleva a resolverlo", async () => {
    const onGo = vi.fn();
    pintar({ membership: { ...MEMBRESIA, state: "past_due" }, onGo });
    await userEvent.click(screen.getByRole("button", { name: /resolver el cobro/i }));
    expect(onGo).toHaveBeenCalledWith({ kind: "section", section: "cuenta" });
  });

  it("con la suscripción al día no se dice nada", () => {
    pintar();
    expect(screen.queryByText(/cobro pendiente/i)).toBeNull();
  });
});

describe("sin permiso para contratar no se ofrece la acción (9.2)", () => {
  it("con el plan lleno, se dice a quién pedírselo", () => {
    pintar({
      membership: { ...MEMBRESIA, usage: { teammates: 5, members: 3 } },
      permissions: NO_PUEDE,
    });
    expect(screen.getByText(/facturación/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("y sin tope tampoco se ofrece cambiar de plan a quien no puede", () => {
    pintar({ permissions: NO_PUEDE });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("con permiso, el plan lleno lleva a cambiarlo", async () => {
    const onGo = vi.fn();
    pintar({ membership: { ...MEMBRESIA, usage: { teammates: 5, members: 3 } }, onGo });
    await userEvent.click(screen.getByRole("button", { name: /cambiar de plan/i }));
    expect(onGo).toHaveBeenCalledOnce();
  });
});

describe("un solo tope a la vez, el más grave", () => {
  it("con cobro pendiente y plan lleno, manda el cobro", () => {
    pintar({ membership: { ...MEMBRESIA, state: "past_due", usage: { teammates: 5, members: 3 } } });
    expect(screen.getByRole("button", { name: /resolver el cobro/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cambiar de plan/i })).toBeNull();
  });
});
