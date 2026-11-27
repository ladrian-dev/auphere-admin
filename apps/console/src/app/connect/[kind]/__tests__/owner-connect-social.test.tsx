import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { MetaSocialOffer } from "@/lib/backend/channels";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }));
const link = vi.hoisted(() => ({ ownerSocialConnectAction: vi.fn(), ownerSocialCompleteAction: vi.fn() }));
const login = vi.hoisted(() => vi.fn(async () => "CODE"));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({}));
vi.mock("../actions", () => link);
vi.mock("@/lib/meta-fb-sdk", async (orig) => ({ ...(await orig<object>()), loginForCode: login }));

const { OwnerConnectSocial } = await import("../owner-connect-social");

const WITH_PAGE: MetaSocialOffer = {
  app_id: "app",
  graph_version: "v26.0",
  channels: [{ kind: "instagram", config_id: "IG-CFG", page_config_id: "IG-PAGE-CFG" }],
};
const WITHOUT_PAGE: MetaSocialOffer = { app_id: "app", graph_version: "v26.0", channels: [{ kind: "instagram", config_id: "IG-CFG" }] };
const MESSENGER: MetaSocialOffer = { app_id: "app", graph_version: "v26.0", channels: [{ kind: "messenger", config_id: "MS-CFG" }] };

function connected(name: string) {
  return { ok: true as const, data: { status: "connected" as const, channel: null, nonce: null, accounts: [], display_name: name } };
}

function page(kind: "instagram" | "messenger", offer: MetaSocialOffer) {
  return render(
    <LocaleProvider locale="es">
      <OwnerConnectSocial kind={kind} name="Barbería Cultor" offer={offer} />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

/**
 * Spec 085, historia 1 (requisitos 2 y 5): la página del dueño para
 * Instagram. Es la conexión de la consola (spec 049 y 081) con las acciones
 * del enlace: la misma pregunta, la misma ventana y los mismos motivos.
 */
describe("la página del dueño para Instagram", () => {
  it("pregunta cómo entra a Meta y abre la ventana con la configuración de cada opción", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(connected("@demo.store"));
    const { container } = page("instagram", WITH_PAGE);
    expect(screen.getByRole("heading", { name: "Conecta el Instagram de Barbería Cultor" })).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    expect(await screen.findByText("¿Cómo entras a Meta?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /^Con Facebook y tu Página/ }));
    expect(login).toHaveBeenLastCalledWith({ appId: "app", version: "v26.0", configId: "IG-PAGE-CFG" });
    expect(link.ownerSocialConnectAction).toHaveBeenCalledWith({ kind: "instagram", code: "CODE" });
    expect(await screen.findByRole("heading", { name: "¡Listo! Tu Instagram está conectado" })).toBeVisible();
    expect(screen.getByText(/@demo\.store ya está con tu agente\. Puedes cerrar esta página\./)).toBeVisible();
  });

  it("«Con Instagram» abre la configuración de siempre, con la pantalla de entrar", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(connected("@demo.store"));
    page("instagram", WITH_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    await user.click(await screen.findByRole("button", { name: /^Con Instagram/ }));
    expect(login).toHaveBeenLastCalledWith({ appId: "app", version: "v26.0", configId: "IG-CFG", prompt: "login" });
  });

  it("sin la configuración con Página abre directamente, sin preguntar", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(connected("@demo.store"));
    page("instagram", WITHOUT_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    expect(screen.queryByText("¿Cómo entras a Meta?")).toBeNull();
    expect(login).toHaveBeenCalledWith(expect.objectContaining({ configId: "IG-CFG" }));
    expect(await screen.findByRole("heading", { name: "¡Listo! Tu Instagram está conectado" })).toBeVisible();
  });

  it("un motivo de Meta se dice con el texto de la consola, y reintentar repite la forma elegida", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValueOnce({ ok: false, status: 409, message: "x", code: "already_connected_elsewhere" });
    link.ownerSocialConnectAction.mockResolvedValueOnce(connected("@demo.store"));
    page("instagram", WITH_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    await user.click(await screen.findByRole("button", { name: /^Con Facebook y tu Página/ }));
    expect(await screen.findByText("No se pudo conectar")).toBeVisible();
    expect(screen.getByText("Esa cuenta ya está conectada a otro cliente.")).toBeVisible();
    expect(screen.getByText("Si no puedes arreglarlo tú, avisa a quien te envió el enlace.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
    expect(login).toHaveBeenCalledTimes(2);
    expect(login).toHaveBeenLastCalledWith({ appId: "app", version: "v26.0", configId: "IG-PAGE-CFG" });
    expect(await screen.findByRole("heading", { name: "¡Listo! Tu Instagram está conectado" })).toBeVisible();
  });

  it.each([
    ["link_used", 410, "Este enlace ya se usó"],
    ["link_expired", 410, "Este enlace caducó"],
    ["link_revoked", 410, "Este enlace ya no es válido"],
    ["link_unknown", 404, "Este enlace no existe"],
  ])("un enlace que ya no sirve (%s) lo dice como el de WhatsApp", async (code, status, title) => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue({ ok: false, status, message: "x", code });
    page("instagram", WITHOUT_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    expect(await screen.findByText(title)).toBeVisible();
    expect(screen.getByText("Pide uno nuevo a quien te lo envió.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Intentar de nuevo" })).toBeNull();
  });
});

/** Spec 085, historia 2 (requisito 3): Messenger entra con Facebook, sin pregunta. */
describe("la página del dueño para Messenger", () => {
  it("dice qué conecta, entra con Facebook sin preguntar y termina con la Página", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(connected("Barbería Cultor Centro"));
    page("messenger", MESSENGER);
    expect(screen.getByRole("heading", { name: "Conecta el Messenger de Barbería Cultor" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Entrar con Facebook" }));
    expect(screen.queryByText("¿Cómo entras a Meta?")).toBeNull();
    expect(login).toHaveBeenCalledWith({ appId: "app", version: "v26.0", configId: "MS-CFG" });
    expect(link.ownerSocialConnectAction).toHaveBeenCalledWith({ kind: "messenger", code: "CODE" });
    expect(await screen.findByRole("heading", { name: "¡Listo! Tu Messenger está conectado" })).toBeVisible();
    expect(screen.getByText(/Barbería Cultor Centro ya está con tu agente/)).toBeVisible();
  });
});

/** Spec 085, historia 3 (requisito 4): elegir entre varias cuentas o Páginas. */
describe("elegir la cuenta o la Página", () => {
  const two = {
    ok: true as const,
    data: {
      status: "choose" as const,
      channel: null,
      nonce: "nonce-0001",
      accounts: [
        { id: "a", name: "Uno", username: "uno.store", picture_url: null },
        { id: "b", name: "Dos", username: "dos.store", picture_url: null },
      ],
    },
  };

  it("pregunta con el diálogo de la consola y conecta la elegida con el mismo enlace", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(two);
    link.ownerSocialCompleteAction.mockResolvedValue(connected("@dos.store"));
    page("instagram", WITHOUT_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    expect(await screen.findByText("¿Qué cuenta de Instagram conectas?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /@dos\.store/ }));
    expect(link.ownerSocialCompleteAction).toHaveBeenCalledWith({ kind: "instagram", nonce: "nonce-0001", accountId: "b" });
    expect(await screen.findByRole("heading", { name: "¡Listo! Tu Instagram está conectado" })).toBeVisible();
  });

  it("en Messenger pregunta por la Página", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(two);
    page("messenger", MESSENGER);
    await user.click(screen.getByRole("button", { name: "Entrar con Facebook" }));
    expect(await screen.findByText("¿Qué Página de Facebook conectas?")).toBeVisible();
  });

  it("cancelar no conecta nada y deja el enlace para volver a intentarlo", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(two);
    page("instagram", WITHOUT_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));
    expect(toast.info).toHaveBeenCalledWith("No se conectó nada.");
    expect(link.ownerSocialCompleteAction).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Conectar mi Instagram" })).toBeEnabled();
  });

  it("una elección caducada lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    link.ownerSocialConnectAction.mockResolvedValue(two);
    link.ownerSocialCompleteAction.mockResolvedValue({ ok: false, status: 409, message: "x", code: "pending_expired" });
    page("instagram", WITHOUT_PAGE);
    await user.click(screen.getByRole("button", { name: "Conectar mi Instagram" }));
    await user.click(await screen.findByRole("button", { name: /@uno\.store/ }));
    expect(await screen.findByText("La elección caducó. Vuelve a conectar.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
    expect(login).toHaveBeenCalledTimes(2);
  });
});
