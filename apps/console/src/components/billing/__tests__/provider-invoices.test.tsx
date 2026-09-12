/**
 * Spec 005 · R8.4 — se llega a las facturas del proveedor desde la consola.
 *
 * El recibo de aquí explica el consumo; **la factura del proveedor es el
 * documento fiscal**. Alguien que necesita la factura para su contabilidad
 * tiene que poder llegar a ella sin escribir a soporte, y sin que le pidamos
 * que recuerde en qué proveedor está su suscripción.
 *
 * Se delega en el portal del proveedor en vez de construir una pantalla de
 * facturas propia: construirla significaría tocar datos de tarjeta, que es
 * exactamente lo que la página alojada existe para evitar.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const openPortal = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/billing/actions", () => ({
  openPortalAction: () => openPortal(),
  startCheckoutAction: vi.fn(),
  buyCreditAction: vi.fn(),
  cancelSubscriptionAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";

import { ProviderInvoicesLink } from "../provider-invoices-link";

beforeEach(() => {
  openPortal.mockReset();
  openPortal.mockResolvedValue({ ok: true, data: { url: "https://portal.example/x" } });
});

describe("el enlace a las facturas", () => {
  it("existe cuando hay suscripción", () => {
    render(
      <LocaleProvider locale="es">
        <ProviderInvoicesLink hasSubscription />
      </LocaleProvider>,
    );
    expect(screen.getByRole("button", { name: /factura/i })).toBeTruthy();
  });

  it("sin suscripción no se pinta apagado: no se pinta (§V)", () => {
    render(
      <LocaleProvider locale="es">
        <ProviderInvoicesLink hasSubscription={false} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("button", { name: /factura/i })).toBeNull();
  });

  it("al pulsarlo pide el portal al servidor", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <ProviderInvoicesLink hasSubscription />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: /factura/i }));
    expect(openPortal).toHaveBeenCalled();
  });

  it("no enseña el nombre del proveedor: es un detalle nuestro", () => {
    const { container } = render(
      <LocaleProvider locale="es">
        <ProviderInvoicesLink hasSubscription />
      </LocaleProvider>,
    );
    expect(container.textContent?.toLowerCase()).not.toContain("stripe");
  });
});
