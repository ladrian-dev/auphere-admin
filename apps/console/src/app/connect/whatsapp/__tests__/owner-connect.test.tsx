import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

const login = vi.hoisted(() => vi.fn(async () => ({ code: "c", waba_id: "w", phone_number_id: "p" })));
const connect = vi.hoisted(() => vi.fn(async () => ({ ok: true as const, phone: "+56 9 1234 5678" })));
vi.mock("@/lib/meta-fb-sdk", async (orig) => ({ ...(await orig<typeof import("@/lib/meta-fb-sdk")>()), loginWithMeta: login }));
vi.mock("../actions", () => ({ ownerConnectAction: connect }));

const { OwnerConnect, sdkModeOf } = await import("../owner-connect");

/**
 * Spec 047 (requisito 31.5; T111) — la página del dueño con un enlace en la beta
 * «WhatsApp login»: lo dice («sin cuenta de Meta», con la verificación del
 * negocio después) y abre la ventana de Meta en Cloud API, que es lo que la API
 * registra. Los enlaces de siempre no cambian.
 */
function page(mode: "coexistence" | "cloud_api" | "whatsapp_login") {
  return render(
    <LocaleProvider locale="es">
      <OwnerConnect name="Barbería Cultor" mode={mode} appId="app" configId="cfg" version="v22.0" />
    </LocaleProvider>,
  );
}

describe("la página del dueño con «WhatsApp login»", () => {
  it("ofrece conectar sin cuenta de Meta y explica que la verificación llega después", async () => {
    const user = userEvent.setup();
    const { container } = page("whatsapp_login");
    expect(screen.getByText(/Vas a conectar tu número con WhatsApp, sin cuenta de Meta/)).toBeVisible();
    expect(screen.getByText(/La verificación del negocio llega después/)).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Conectar con WhatsApp, sin cuenta de Meta" }));
    expect(login).toHaveBeenCalledWith(expect.objectContaining({ mode: "cloud_api" }));
    expect(await screen.findByText(/Tu WhatsApp está conectado/)).toBeVisible();
  });

  it("los enlaces de siempre no prometen nada nuevo", () => {
    page("coexistence");
    expect(screen.getByRole("button", { name: "Conectar mi WhatsApp" })).toBeVisible();
    expect(screen.queryByText(/sin cuenta de Meta/)).toBeNull();
    expect(sdkModeOf("coexistence")).toBe("coexistence");
    expect(sdkModeOf("cloud_api")).toBe("cloud_api");
    expect(sdkModeOf("whatsapp_login")).toBe("cloud_api");
  });
});
