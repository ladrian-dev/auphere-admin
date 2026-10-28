import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientDetailV2 } from "@/lib/backend/client-records";

vi.mock("next/navigation", () => ({
  usePathname: () => "/clients/barberia-cultor/business",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  archiveClientAction: vi.fn(),
  deleteClientV2Action: vi.fn(),
  getClientV2Action: vi.fn(),
  restoreClientAction: vi.fn(),
  updateClientV2Action: vi.fn(),
}));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { ClientHeaderV2 } = await import("../client-header-v2");
const { useCrumbNames } = await import("@/components/shell/crumb-names");

/**
 * Recorrido UI de la 047: las migas de un cliente decían su referencia
 * («Clientes › flor-y-encanto»). Con el alta en tres datos la referencia la
 * deriva la consola, no la elige el partner: la cabecera anuncia el nombre.
 */
const DETAIL: ClientDetailV2 = {
  external_client_ref: "barberia-cultor",
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  niche: "Barbería de barrio",
  info: null,
  website: null,
  country: "ES",
  price_currency: "EUR",
  wallet_currency: "USD",
  eu_only: true,
  lifecycle: "active",
  revision: 4,
  allowed: [],
};

function Crumbs() {
  const names = useCrumbNames();
  return <output data-testid="crumbs">{names["barberia-cultor"] ?? ""}</output>;
}

describe("ClientHeaderV2", () => {
  it("da a las migas el nombre del cliente, no su referencia", () => {
    render(
      <LocaleProvider locale="es">
        <Crumbs />
        <ClientHeaderV2 client={DETAIL} />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("crumbs").textContent).toBe("Barbería Cultor");
  });
});
