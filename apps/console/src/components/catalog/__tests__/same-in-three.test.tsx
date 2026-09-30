import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { CapabilitiesCatalog } from "@/components/capabilities/catalog";
import { ChannelsList } from "@/components/channels/channels-list";
import { IntegrationsList } from "@/components/integrations/integrations-list";
import type { Capability, CapabilitiesOut } from "@/lib/backend/capabilities";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";
import type { ChannelDetail } from "@/lib/backend/channels";

/**
 * R4.6: **los tres catálogos llaman igual a las mismas cosas y las colocan
 * en el mismo sitio.**
 *
 * Esto no se comprueba leyendo las tres pantallas y confiando en el ojo: se
 * montan las tres y se compara lo que se ve. Antes de la spec 018,
 * Habilidades decía «Buscar una habilidad», Conectores no tenía buscador y
 * Canales tampoco — y nadie se dio cuenta hasta que el owner las puso una al
 * lado de la otra. Un test que compara es lo único que impide que vuelvan a
 * separarse con el siguiente retoque.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/app/(console)/clients/[ref]/capabilities/actions", () => ({ setCapabilityAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({ setChannelRoleAction: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function cap(key: string, fn: string, enabled: boolean): Capability {
  return {
    kind: "tool",
    key,
    business_name: key,
    description: "",
    function: fn as Capability["function"],
    sectors: [],
    recommended: false,
    other_sector: false,
    enabled,
    enabled_in_active: enabled,
    usable: true,
    activatable: true,
    connector: null,
    mode: null,
    read_only: false,
    destructive: false,
    technical: { name: key, kind: "tool", version: null, tags: [] },
  };
}

const CAPS: CapabilitiesOut = {
  sector: "bakery",
  hidden_by_sector: 0,
  has_draft: false,
  version: 1,
  active_version: 1,
  // Dos en «Citas» a propósito: el patrón no agrupa cuando cada grupo
  // tendría uno, así que un arnés de uno por grupo no probaría nada.
  groups: [
    { function: "appointments", items: [cap("Reservar", "appointments", true), cap("Cancelar", "appointments", false)] },
    { function: "orders", items: [cap("Pedir", "orders", false)] },
  ],
};

function connector(slug: string, category: string, status: string | null): ConnectorOut {
  return {
    slug,
    display_name: slug,
    vendor: slug,
    category,
    auth_kind: "api_key",
    logo_url: null,
    capabilities: [],
    installed: status !== null,
    status,
    scopes_granted: [],
    connected_at: null,
    last_synced_at: null,
    last_health_check_at: null,
    consent_expires_at: null,
    credentials_form: [],
    tools_total: 0,
    tools_enabled: 0,
  };
}

const CHANNEL: ChannelDetail = {
  id: "ch1",
  type: "whatsapp",
  provider: "meta",
  provider_identifier: "+34600123456",
  status: "active",
  role: "agent",
  last_health_check_at: null,
  created_at: "2026-09-01T00:00:00Z",
  quality_rating: "GREEN",
  messaging_tier: null,
  verified_name: "Panadería La Espiga",
  mode: null,
  agent_enabled: true,
  logo_url: null,
  unlink_pending: [],
  catalog: null,
  catalog_state: "none",
  catalog_error: null,
};

/** Las tres pantallas, montadas igual. */
const PANTALLAS = {
  Habilidades: () => (
    <CapabilitiesCatalog refId="demo" data={CAPS} canWrite seeAllHref="/a" seeOwnHref="/b" />
  ),
  Conectores: () => (
    <IntegrationsList
      refId="demo"
      connectors={[connector("WooCommerce", "ecommerce", "connected"), connector("AgendaPro", "booking", null)]}
      error={null}
      canWrite
    />
  ),
  Canales: () => <ChannelsList refId="demo" channels={[CHANNEL]} manage empty={<p>sin canales</p>} />,
} as const;

function mount(name: keyof typeof PANTALLAS) {
  const Pantalla = PANTALLAS[name];
  return render(
    <LocaleProvider locale="es">
      <Pantalla />
    </LocaleProvider>,
  );
}

const NOMBRES = Object.keys(PANTALLAS) as (keyof typeof PANTALLAS)[];

afterEach(() => {
  vi.clearAllMocks();
});

describe("Los tres catálogos · las mismas palabras", () => {
  it("el buscador se llama igual en los tres", () => {
    for (const nombre of NOMBRES) {
      const { unmount } = mount(nombre);
      expect(screen.getByRole("searchbox", { name: "Buscar en la lista" }), nombre).toBeInTheDocument();
      unmount();
    }
  });

  it("las dos pestañas se llaman igual y están en el mismo grupo", () => {
    for (const nombre of NOMBRES) {
      const { unmount } = mount(nombre);
      const grupo = screen.getByRole("group", { name: "Qué se ve" });
      expect(
        within(grupo)
          .getAllByRole("link")
          .map((a) => a.textContent),
        nombre,
      ).toEqual(["Activos", "Todo"]);
      unmount();
    }
  });

  it("el contador dice lo mismo en los tres: cuántos se ven, de cuántos, y cuántos activos", () => {
    const contadores: Record<string, string> = {};
    for (const nombre of NOMBRES) {
      const { container, unmount } = mount(nombre);
      contadores[nombre] = container.querySelector("[aria-live=polite]")?.textContent ?? "";
      unmount();
    }
    expect(contadores).toEqual({
      Habilidades: "3 de 3 · 1 activos",
      Conectores: "2 de 2 · 1 activos",
      Canales: "1 de 1 · 1 activos",
    });
  });
});

describe("Los tres catálogos · las categorías", () => {
  it("cada uno agrupa por lo suyo, con el nombre de negocio y no con la clave", () => {
    const { unmount } = mount("Habilidades");
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Citas", "Pedidos"]);
    unmount();

    // Conectores: dos categorías con uno cada una, así que el patrón **no**
    // agrupa —serían dos títulos para dos tarjetas—. Lo que sí se conserva
    // es el orden por urgencia: sin conectar antes que funcionando.
    mount("Conectores");
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "AgendaPro",
      "WooCommerce",
    ]);
  });

  it("con una sola categoría no hay pastillas: no filtrarían nada", () => {
    mount("Canales");
    // Canales tiene un solo tipo hoy. El patrón se calla las pastillas él
    // solo; la pantalla no tiene que saberlo.
    expect(screen.queryByRole("link", { name: /·\s\d+$/ })).toBeNull();
    // Y la tarjeta está: callarse el encabezado no es callarse la lista.
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("Los tres catálogos · lo que no se puede conectar no está", () => {
  it("Canales no enseña un canal apagado ni prometido (R4.7, §V)", () => {
    mount("Canales");
    // La lista es exactamente lo que se le pasó. Messenger, Instagram y
    // Telegram se quedan fuera antes de llegar aquí, y no hay ninguna
    // tarjeta gris con un «próximamente» que los mencione.
    expect(screen.queryByText(/messenger|instagram|telegram|pr[óo]ximamente/i)).toBeNull();
  });
});
