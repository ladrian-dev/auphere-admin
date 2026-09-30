import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";

import { connectChoice, metaIsConfigured, metaSignupConfig, type ConnectChoice } from "../connect-choice";
import { MetaWindowVeil, WhatsAppConnect, signupFailureKey, type MetaSignupConfig } from "../whatsapp-connect";
import { WhatsAppConnectByAuphere } from "../whatsapp-connect-by-auphere";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({ whatsappSignupAction: vi.fn(), listCatalogsAction: vi.fn() }));
vi.mock("@/lib/meta-fb-sdk", () => ({ loginWithMeta: vi.fn(), SignupError: class extends Error {} }));

const configured: MetaSignupConfig = { appId: "123", graphVersion: "v22.0", configIdCloudApi: "cfg-cloud", configIdCoexistence: null };

describe("connect WhatsApp — which control the page shows (spec 016, R1.1/R1.3)", () => {
  it("decides by permission first, then by whether Meta is configured", () => {
    const cases: Array<[boolean, MetaSignupConfig, ConnectChoice]> = [
      [false, configured, "none"],
      [true, configured, "connect"],
      [true, { ...configured, appId: null }, "by_auphere"],
      [true, { ...configured, configIdCloudApi: null }, "by_auphere"],
      [true, { ...configured, configIdCloudApi: null, configIdCoexistence: "cfg-coex" }, "connect"],
    ];
    for (const [manage, meta, expected] of cases) expect(connectChoice({ manage, meta })).toBe(expected);
    expect(metaIsConfigured({ appId: "1", graphVersion: "v22.0", configIdCloudApi: null, configIdCoexistence: null })).toBe(false);
  });
  it("reads the environment names the console actually uses", () => {
    expect(
      metaSignupConfig({ NEXUS_META_APP_ID: "123", NEXUS_META_GRAPH_API_VERSION: "v22.0", NEXUS_META_CONFIG_ID_WA_CLOUD_API: "c1" }),
    ).toEqual({ appId: "123", graphVersion: "v22.0", configIdCloudApi: "c1", configIdCoexistence: null });
    expect(metaSignupConfig({ NEXUS_META_GRAPH_API_VERSION: "v22.0" }).appId).toBeNull();
  });
  it("with Meta configured renders the real «Conectar WhatsApp» button, enabled", () => {
    render(
      <LocaleProvider locale="es">
        <WhatsAppConnect refId="demo" meta={configured} canConnect used={0} max={1} />
      </LocaleProvider>,
    );
    const button = screen.getByRole("button", { name: /Conectar WhatsApp/ });
    expect(button).toBeEnabled();
  });
  it("with the channel quota full the button is disabled and says why", () => {
    render(
      <LocaleProvider locale="es">
        <WhatsAppConnect refId="demo" meta={configured} canConnect={false} used={1} max={1} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("button", { name: /Conectar otro número/ })).toBeDisabled();
    expect(screen.getByText(/Cuota de canales completa/)).toBeInTheDocument();
  });
  it("without Meta the note has no button and says who connects it", () => {
    render(
      <LocaleProvider locale="es">
        <WhatsAppConnectByAuphere />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("El número lo conecta Auphere");
    expect(screen.getByRole("status")).toHaveTextContent("Escribe a soporte");
  });
});

describe("un número que su dueño anterior aún retiene en Meta (spec 021, R4.2)", () => {
  it("tiene su frase, y no se presenta como un fallo de la consola", () => {
    // Meta es el árbitro del traspaso: B no puede registrar lo que A no
    // soltó en su Business Manager. La consola no falló; lo dice así.
    expect(signupFailureKey("number_held_by_previous_owner")).toBe("ch.connect.heldByPreviousOwner");
    expect(signupFailureKey("number_in_use")).toBe("ch.connect.numberInUse");
    expect(signupFailureKey("validation_error")).toBeNull();
    expect(signupFailureKey(undefined)).toBeNull();
    expect(signupFailureKey(null)).toBeNull();
    for (const lang of ["es", "en"] as const) {
      const texto = messages["ch.connect.heldByPreviousOwner"][lang];
      expect(texto).toMatch(/Business Manager/);
      expect(texto).not.toMatch(/error|fallo|failed/i);
    }
    // Y sigue sin decir **de quién** es el número (R1.5).
    expect(messages["ch.connect.heldByPreviousOwner"].es).not.toMatch(/partner|cliente/i);
  });
});

describe("mientras la ventana de Meta está abierta (2026-09-30)", () => {
  it("la consola se apaga en verde oscuro y dice dónde estamos", () => {
    render(
      <LocaleProvider locale="es">
        <MetaWindowVeil open />
      </LocaleProvider>,
    );
    const veil = screen.getByRole("status");
    expect(veil).toHaveTextContent("Estamos en la ventana de Meta");
    expect(veil.className).toContain("bg-dark-green");
  });

  it("y desaparece en cuanto Meta devuelve", () => {
    render(
      <LocaleProvider locale="es">
        <MetaWindowVeil open={false} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
