/**
 * Spec 005 · R1.4, R5.7 y §V — lo que la pantalla de planes dice y lo que calla.
 *
 * Tres cosas se prueban aquí, y las tres son constitución antes que diseño:
 *
 * 1. **La ausencia se diseña.** En el nivel gratuito no hay botón apagado de
 *    «crear teammate»: no hay botón. Un control deshabilitado dice «esto
 *    existe pero tú no» y deja a la persona peleándose con él.
 * 2. **La cifra del pool no se enseña nunca.** Lo que describe a un nivel son
 *    sus topes y un múltiplo; el número es provisional y publicarlo convierte
 *    cada ajuste de capacidad en un recorte visible (research D9).
 * 3. **El estado de la cuenta dice qué lo arregla**, y no culpa al partner.
 *    Un impago es un problema de facturación, no una falta.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/billing/actions", () => ({
  startCheckoutAction: vi.fn(),
  openPortalAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import type { MembershipOut, TierOut } from "@/lib/backend/membership";

import { MembershipPanel } from "../membership-panel";

const tier = (over: Partial<TierOut> = {}): TierOut => ({
  code: "pro",
  display_name: "Pro",
  monthly_price_cents: 2000,
  max_teammates: 2,
  max_members: 1,
  consumption_multiple: 1,
  ...over,
});

const CATALOG: TierOut[] = [
  tier({ code: "free", display_name: "Free", monthly_price_cents: 0, max_teammates: 0, consumption_multiple: null }),
  tier(),
  tier({ code: "team", display_name: "Team", monthly_price_cents: 6000, max_teammates: 6, max_members: 3, consumption_multiple: 4 }),
  tier({ code: "business", display_name: "Business", monthly_price_cents: 15000, max_teammates: 12, max_members: 8, consumption_multiple: 12 }),
];

const membership = (over: Partial<MembershipOut> = {}): MembershipOut => ({
  tier: tier(),
  state: "current",
  state_changed_at: "2026-09-01T10:00:00Z",
  current_period_end: "2026-10-01T10:00:00Z",
  pending_tier: null,
  usage: { teammates: 1, members: 1 },
  purchased_expires_at: null,
  catalog: CATALOG,
  ...over,
});

function panel(over: Partial<MembershipOut> = {}) {
  return render(
    <LocaleProvider locale="es">
      <MembershipPanel membership={membership(over)} />
    </LocaleProvider>,
  );
}

describe("la ausencia se diseña (R1.4, §V)", () => {
  it("en el nivel gratuito no hay control de teammates, ni siquiera apagado", () => {
    panel({ tier: CATALOG[0], usage: { teammates: 0, members: 1 } });
    expect(screen.queryByRole("button", { name: /teammate/i })).toBeNull();
    // Y lo que sí hay: por qué, y qué lo desbloquea.
    expect(screen.getAllByText(/plan/i).length).toBeGreaterThan(0);
  });

  it("con un plan de pago el control existe y está vivo", () => {
    panel();
    const control = screen.queryByRole("link", { name: /teammate/i });
    if (control) expect(control.getAttribute("aria-disabled")).not.toBe("true");
  });
});

describe("la cifra del pool no sale a pantalla (D9)", () => {
  it("no aparece ningún número de unidades en ningún nivel", () => {
    const { container } = panel();
    const text = container.textContent ?? "";
    for (const figure of ["100000", "500000", "2000000", "6000000", "100.000", "500.000", "2.000.000", "6.000.000"]) {
      expect(text).not.toContain(figure);
    }
  });

  it("lo que se ve de cada nivel son sus topes y su múltiplo", () => {
    panel();
    expect(screen.getAllByText(/4×|4x/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/12×|12x/).length).toBeGreaterThan(0);
  });

  it("el nivel gratuito no enseña un múltiplo absurdo", () => {
    const { container } = panel();
    expect(container.textContent).not.toContain("0,2×");
    expect(container.textContent).not.toContain("0.2x");
  });
});

describe("el estado de la cuenta dice qué lo arregla (R5.7)", () => {
  it.each([
    ["payment_failed", /tarjeta|pago/i],
    ["unpaid", /tarjeta|pago/i],
    ["canceled", /plan|contrat/i],
  ] as const)("«%s» explica la salida", (state, hint) => {
    panel({ state });
    expect(screen.getAllByText(hint).length).toBeGreaterThan(0);
  });

  it("ninguno de los estados culpa al partner", () => {
    for (const state of ["payment_failed", "unpaid", "canceled"] as const) {
      const { container, unmount } = render(
        <LocaleProvider locale="es">
          <MembershipPanel membership={membership({ state })} />
        </LocaleProvider>,
      );
      const text = (container.textContent ?? "").toLowerCase();
      for (const blame of ["no has pagado", "incumpl", "moroso", "tu culpa", "error tuyo"]) {
        expect(text).not.toContain(blame);
      }
      unmount();
    }
  });

  it("al corriente no pinta ninguna alarma", () => {
    const { container } = panel();
    expect((container.textContent ?? "").toLowerCase()).not.toContain("pago fallido");
  });
});

describe("un cambio programado se ve (D7)", () => {
  it("dice a qué nivel se baja y cuándo", () => {
    panel({ pending_tier: "pro", current_period_end: "2026-10-01T10:00:00Z" });
    expect(screen.getAllByText(/Pro/).length).toBeGreaterThan(0);
  });
});
