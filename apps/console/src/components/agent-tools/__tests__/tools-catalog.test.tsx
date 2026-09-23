import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";
import type { ConnectorOut, ToolCatalogOut } from "@/lib/backend/agent-tools-types";

import { credentialFieldLabel, lastSyncKey } from "../lib";
import { ToolsCatalog } from "../tools-catalog";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/tools/actions", () => ({
  connectApiKeyAction: vi.fn(),
  connectorStatusAction: vi.fn(),
  resetToolModeAction: vi.fn(),
  saveToolsAction: vi.fn(),
  setAgendaProUrlAction: vi.fn(),
  setToolModeAction: vi.fn(),
  startConsentAction: vi.fn(),
  syncConnectorAction: vi.fn(),
}));

// One native tool: an empty catalogue short-circuits to the empty state.
const tool = { name: "booking.check_availability", description: "x", capability_tags: [], read_only: true, destructive: false, status: "active", enabled: true, enabled_in_active: false, connector_slug: null, connector_display_name: null, connector_status: null, connector_required: false, usable: true, default_mode: "always" as const, override_mode: null, effective_mode: "always" as const };
const catalog: ToolCatalogOut = { version: 1, version_status: "staged", active_version: null, has_draft: true, tools: [tool] };
const base = { vendor: "x", category: "x", logo_url: null, capabilities: [], installed: false, status: null, scopes_granted: [], connected_at: null, last_synced_at: null, last_health_check_at: null, consent_expires_at: null, tools_total: 0, tools_enabled: 0 };
const agendapro: ConnectorOut = { ...base, slug: "agendapro", display_name: "AgendaPro", auth_kind: "public_url", credentials_form: [], public_url: null };
const woo: ConnectorOut = {
  ...base,
  slug: "woocommerce",
  display_name: "WooCommerce",
  auth_kind: "api_key",
  credentials_form: [
    { field: "store_url", label: "Store URL", secret: false, required: true },
    { field: "consumer_key", label: "Consumer Key", secret: true, required: true },
    { field: "made_up", label: "Seed label", secret: true, required: false },
  ],
};

function mount(connectors: ConnectorOut[], canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <ToolsCatalog refId="demo" catalog={catalog} connectors={connectors} connectorsError={null} canWrite={canWrite} />
    </LocaleProvider>,
  );
}

describe("ToolsCatalog connectors (spec 016, US5)", () => {
  it("AgendaPro is linked by its public page: «Enlazar la agenda», a URL field, no credentials", () => {
    mount([agendapro]);
    fireEvent.click(screen.getByRole("button", { name: "Enlazar la agenda" }));
    expect(screen.getByLabelText("Dirección pública de la agenda")).toHaveAttribute("type", "url");
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByText(/contraseña/i)).not.toBeNull(); // the help says never to ask for it
    expect(screen.queryByRole("button", { name: "Sincronizar" })).toBeNull();
  });
  it("a linked AgendaPro shows the page, «Cambiar» and «Desenlazar»", () => {
    mount([{ ...agendapro, public_url: "https://x.site.agendapro.com/cl/s", status: "connected", installed: true }]);
    expect(screen.getByRole("link", { name: /x\.site\.agendapro\.com/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambiar la agenda" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desenlazar" })).toBeInTheDocument();
    expect(screen.getByText("Conectado")).toBeInTheDocument();
  });
  it("an API-key connector has no permanent «Sincronizar» and its fields are translated", () => {
    const { unmount } = mount([{ ...woo, installed: true, status: "connected" }]);
    expect(screen.queryByRole("button", { name: "Sincronizar" })).toBeNull();
    unmount();
    // A rejected key: «Reconectar» opens the same form, with the labels in Spanish.
    mount([{ ...woo, installed: true, status: "needs_reauth" }]);
    fireEvent.click(screen.getByRole("button", { name: "Reconectar" }));
    expect(screen.getByLabelText("Dirección de la tienda")).toBeInTheDocument();
    expect(screen.getByLabelText("Clave de consumidor (consumer key)")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Seed label")).toBeInTheDocument();
  });
  it("credentialFieldLabel falls back to the seed label, then the field name", () => {
    const t = (k: string) => messages[k as keyof typeof messages].es;
    expect(credentialFieldLabel("woocommerce", { field: "store_url", label: "Store URL" }, messages, t)).toBe("Dirección de la tienda");
    expect(credentialFieldLabel("woocommerce", { field: "made_up", label: "Seed label" }, messages, t)).toBe("Seed label");
    expect(credentialFieldLabel("woocommerce", { field: "made_up" }, messages, t)).toBe("made_up");
  });
  it("lastSyncKey names the three outcomes", () => {
    const at = "2026-09-23T00:00:00Z";
    expect(lastSyncKey(null)).toBeNull();
    expect(lastSyncKey({ status: "ok", added: 2, deprecated: 0, reason: null, at })).toBe("connectors.lastSync.ok");
    expect(lastSyncKey({ status: "error", added: 0, deprecated: 0, reason: "provider_unavailable", at })).toBe("connectors.lastSync.provider_unavailable");
    expect(lastSyncKey({ status: "error", added: 0, deprecated: 0, reason: "auth_rejected", at })).toBe("connectors.lastSync.auth_rejected");
  });
  it("without agents:write there is nothing to click", () => {
    mount([agendapro, woo], false);
    expect(screen.queryByRole("button", { name: /Enlazar|Conectar|Reconectar/ })).toBeNull();
  });
});
