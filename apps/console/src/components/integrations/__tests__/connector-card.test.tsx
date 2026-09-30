import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";

import { ConnectorCard } from "../connector-card";

/**
 * La tarjeta de conector, rehecha con el owner el 2026-09-28.
 *
 * Lo que estos tests fijan es la forma que se pidió —icono, nombre, para qué
 * sirve, y **una** acción— y las dos decisiones que la sostienen: que el
 * estado no depende de una insignia, y que ninguna acción se perdió al
 * meterlas en «Más».
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({
  connectApiKeyAction: vi.fn(),
  connectorStatusAction: vi.fn(),
  setAgendaProUrlAction: vi.fn(),
  startConsentAction: vi.fn(),
  syncConnectorAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

function conector(over: Partial<ConnectorOut> = {}): ConnectorOut {
  return {
    slug: "woocommerce",
    display_name: "WooCommerce",
    vendor: "woocommerce",
    category: "ecommerce",
    auth_kind: "api_key",
    logo_url: null,
    capabilities: [],
    installed: false,
    status: null,
    scopes_granted: [],
    connected_at: null,
    last_synced_at: null,
    last_health_check_at: null,
    consent_expires_at: null,
    credentials_form: [],
    tools_total: 12,
    tools_enabled: 0,
    ...over,
  };
}

function mount(over: Partial<ConnectorOut> = {}, canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <ul>
        <ConnectorCard refId="demo" connector={conector(over)} canWrite={canWrite} />
      </ul>
    </LocaleProvider>,
  );
}

describe("Tarjeta de conector · la forma", () => {
  it("dice para qué sirve, no solo cómo se llama", () => {
    mount();
    expect(screen.getByRole("heading", { level: 3, name: "WooCommerce" })).toBeInTheDocument();
    expect(screen.getByText(/La tienda del negocio/)).toBeInTheDocument();
  });

  it("un conector que no conocemos no enseña su clave interna", () => {
    // El catálogo puede publicar uno nuevo cualquier día. La frase de
    // reserva no inventa nada sobre él, y sobre todo no pinta el slug.
    mount({ slug: "algo_nuevo", display_name: "Algo Nuevo" });
    expect(screen.getByText("Conéctalo para que el agente pueda usarlo.")).toBeInTheDocument();
    expect(screen.queryByText(/algo_nuevo/)).toBeNull();
  });

  it("los tres de Composio con lista cerrada tienen su frase, no la de reserva (spec 023)", () => {
    mount({ slug: "stripe", display_name: "Stripe", category: "billing", auth_kind: "oauth_composio" });
    expect(screen.getByText(/Los cobros del negocio/)).toBeInTheDocument();
    expect(screen.queryByText("Conéctalo para que el agente pueda usarlo.")).toBeNull();
  });

  it("recomendado por la plantilla del sector lleva la insignia; sin ello, no (spec 023)", () => {
    const { container, unmount } = mount({ slug: "calendly", display_name: "Calendly", recommended: true });
    expect(screen.getByText("Recomendado para tu sector")).toBeInTheDocument();
    unmount();
    mount({ slug: "calendly", display_name: "Calendly", recommended: false });
    expect(screen.queryByText("Recomendado para tu sector")).toBeNull();
    expect(container.querySelector("[data-slot=status-badge]")).toBeNull();
  });

  it("sin logotipo, la inicial: un hueco gris no distingue una tarjeta de otra", () => {
    const { container } = mount();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("W")).toBeInTheDocument();
  });
});

describe("Tarjeta de conector · el estado no depende de una insignia", () => {
  it("sin conectar lo dice con palabras, y el icono no lleva punto", () => {
    const { container } = mount();
    expect(screen.getByText("Sin conectar")).toBeInTheDocument();
    // Un punto en la esquina del icono sobre algo que no se ha instalado
    // sería un estado inventado. En la línea de abajo sí hay uno: ahí
    // acompaña a la palabra, no la sustituye.
    const icono = container.querySelector("[data-slot=connector-icon]")!;
    expect(icono.querySelector("[data-slot=status-dot]")).toBeNull();
  });

  it("conectado: punto verde **y** la palabra; sin insignia que lo repita", () => {
    const { container } = mount({ installed: true, status: "connected" });
    const icono = container.querySelector("[data-slot=connector-icon]")!;
    expect(icono.querySelector("[data-slot=status-dot][data-tone=positive]")).not.toBeNull();
    expect(screen.getByText("Conectado")).toBeInTheDocument();
    // La insignia se reserva para lo que necesita explicación.
    expect(container.querySelector("[data-slot=status-badge]")).toBeNull();
  });

  it("pausado o roto sí llevan insignia: ahí hacen falta palabras", () => {
    const { container } = mount({ installed: true, status: "paused" });
    expect(container.querySelector("[data-slot=status-badge]")).not.toBeNull();
    expect(container.querySelector("[data-slot=status-dot][data-tone=warning]")).not.toBeNull();
  });
});

describe("Tarjeta de conector · una acción a la vista, ninguna perdida", () => {
  it("sin conectar, un «+» con el nombre del conector en su etiqueta", () => {
    mount();
    // Un icono solo no dice a qué conector pertenece; con seis tarjetas en
    // pantalla, «Conectar» a secas no es un nombre accesible.
    expect(screen.getByRole("button", { name: "Conectar WooCommerce" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Más opciones/ })).toBeNull();
  });

  it("conectado, todo lo demás vive en «Más» y sigue estando", async () => {
    const user = userEvent.setup();
    mount({ installed: true, status: "connected", auth_kind: "oauth" });
    await user.click(screen.getByRole("button", { name: "Más opciones de WooCommerce" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Sincronizar",
      "Pausar",
      "Desconectar",
    ]);
  });

  it("pausado ofrece reanudar, no pausar otra vez", async () => {
    const user = userEvent.setup();
    mount({ installed: true, status: "paused", auth_kind: "oauth" });
    await user.click(screen.getByRole("button", { name: "Más opciones de WooCommerce" }));
    const menu = await screen.findByRole("menu");
    const items = within(menu).getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toContain("Reanudar");
    expect(items).not.toContain("Pausar");
  });

  it("roto, la salida se lee: «Reconectar» es un botón con texto", () => {
    mount({ installed: true, status: "error" });
    // Un icono no basta para un error: la acción que lo arregla tiene que
    // poder leerse sin abrir un menú.
    expect(screen.getByRole("button", { name: "Reconectar" })).toBeInTheDocument();
  });

  it("quien no puede escribir no ve ni el «+» ni el menú", () => {
    mount({ installed: true, status: "connected" }, false);
    expect(screen.queryByRole("button")).toBeNull();
    // Pero el estado se lee igual.
    expect(screen.getByText("Conectado")).toBeInTheDocument();
  });
});
