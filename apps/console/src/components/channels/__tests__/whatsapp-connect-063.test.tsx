import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { WhatsAppConnect, type MetaSignupConfig } from "../whatsapp-connect";

/**
 * Spec 063 (requisito 2.1; 047, 30.6): al terminar de conectar un número desde la
 * página Canales del cliente, la consola abre su configuración, como al conectarlo
 * desde el agente. En prod (2026-11-18) se quedaba en la misma página, y el número
 * nacía «Sin configurar»: no respondía a nadie y nadie lo veía.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));
const whatsappSignupAction = vi.fn();
const listCatalogsAction = vi.fn();
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  whatsappSignupAction: (...args: unknown[]) => whatsappSignupAction(...args),
  listCatalogsAction: (...args: unknown[]) => listCatalogsAction(...args),
  setCatalogAction: vi.fn(),
}));
vi.mock("@/lib/meta-fb-sdk", () => ({
  loginWithMeta: vi.fn().mockResolvedValue({ code: "code", waba_id: "waba", phone_number_id: "phone" }),
  SignupError: class extends Error {},
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const META: MetaSignupConfig = { appId: "123", graphVersion: "v22.0", configIdCloudApi: "cfg-cloud", configIdCoexistence: null };
const CONFIG = "/clients/demo/channels/c-1";

beforeEach(() => {
  push.mockReset();
  whatsappSignupAction.mockResolvedValue({
    ok: true,
    data: { status: "connected", channel_id: "c-1", display_phone_number: "+34653321693", mode: "cloud_api", client_status: "active" },
  });
});

async function connect() {
  const user = userEvent.setup();
  render(
    <LocaleProvider locale="es">
      <WhatsAppConnect refId="demo" meta={META} canConnect used={0} max={1} />
    </LocaleProvider>,
  );
  await user.click(screen.getByRole("button", { name: /Conectar WhatsApp/ }));
  await user.click(screen.getByRole("button", { name: "Abrir Meta" }));
  return user;
}

describe("al conectar desde Canales del cliente (spec 063)", () => {
  it("abre la configuración del número nuevo", async () => {
    listCatalogsAction.mockResolvedValue({ ok: true, data: { items: [], linked_id: null } });
    await connect();
    await waitFor(() => expect(push).toHaveBeenCalledWith(CONFIG));
  });

  it("con catálogo, la abre al cerrar la oferta, sin saltársela", async () => {
    listCatalogsAction.mockResolvedValue({
      ok: true,
      data: { items: [{ id: "cat-1", name: "Catálogo", product_count: 3 }], linked_id: null },
    });
    const user = await connect();
    await screen.findByRole("button", { name: "Ahora no" });
    expect(push).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Ahora no" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(CONFIG));
  });
});
