/**
 * Spec 085 (requisito 1): «Enviar enlace al cliente» es el mismo panel en
 * WhatsApp, Instagram y Messenger. Solo WhatsApp pregunta el modo; el dueño
 * elige cómo entra a Meta en su página. Copiar, enviar por WhatsApp, enviar por
 * correo con el asunto de su canal y la caducidad son los mismos. Sin el canal
 * para el partner, no hay botón (§V).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { MetaSocialOffer } from "@/lib/backend/channels";

const actions = vi.hoisted(() => ({ signupLinkAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => actions);
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { ShareLink } = await import("../whatsapp-share-link");

const OFFER: MetaSocialOffer = {
  app_id: "app",
  graph_version: "v26.0",
  channels: [
    { kind: "instagram", config_id: "1" },
    { kind: "messenger", config_id: "2" },
  ],
};
const URL = "https://console.auphere.com/connect/instagram/tok-123";

/** The share buttons are anchors rendered by `Button` (`nativeButton={false}`). */
function href(name: string): string {
  return decodeURIComponent(screen.getByText(name).closest("a")?.getAttribute("href") ?? "");
}

function paint(ui: React.ReactElement) {
  return render(<LocaleProvider locale="es">{ui}</LocaleProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  actions.signupLinkAction.mockResolvedValue({
    ok: true,
    data: { url: URL, channel: "instagram", expires_at: "2026-12-04T10:00:00Z" },
  });
});

describe("el enlace de Instagram para el cliente", () => {
  it("no pregunta el modo y comparte con el asunto de Instagram", async () => {
    const user = userEvent.setup();
    paint(<ShareLink refId="flor" channel="instagram" offer={OFFER} />);
    await user.click(screen.getByRole("button", { name: "Enviar enlace de Instagram al cliente" }));
    expect(screen.queryByLabelText("Modo de conexión")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(actions.signupLinkAction).toHaveBeenCalledWith({ ref: "flor", channel: "instagram" });

    expect(await screen.findByDisplayValue(URL)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar enlace" })).toBeInTheDocument();
    expect(href("Enviar por WhatsApp")).toContain("tu Instagram");
    expect(href("Enviar por WhatsApp")).toContain(URL);
    expect(href("Enviar por correo")).toContain("subject=Conecta el Instagram de tu negocio");
    expect(screen.getByText(/^Caduca el /)).toBeInTheDocument();
  });

  it("Messenger lleva su propio asunto", async () => {
    const user = userEvent.setup();
    actions.signupLinkAction.mockResolvedValue({
      ok: true,
      data: { url: URL.replace("instagram", "messenger"), channel: "messenger", expires_at: "2026-12-04T10:00:00Z" },
    });
    paint(<ShareLink refId="flor" channel="messenger" offer={OFFER} />);
    await user.click(screen.getByRole("button", { name: "Enviar enlace de Messenger al cliente" }));
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(actions.signupLinkAction).toHaveBeenCalledWith({ ref: "flor", channel: "messenger" });
    expect(await screen.findByText("Enviar por correo")).toBeInTheDocument();
    expect(href("Enviar por correo")).toContain("subject=Conecta el Messenger de tu negocio");
  });

  it("sin Instagram para el partner no hay botón ni explicación", () => {
    const { container } = paint(
      <ShareLink refId="flor" channel="instagram" offer={{ ...OFFER, channels: [{ kind: "messenger", config_id: "2" }] }} />,
    );
    expect(container).toBeEmptyDOMElement();
    const none = paint(<ShareLink refId="flor" channel="messenger" offer={null} />);
    expect(none.container).toBeEmptyDOMElement();
  });
});

describe("el enlace de WhatsApp sigue igual", () => {
  it("pregunta el modo y lo manda", async () => {
    const user = userEvent.setup();
    actions.signupLinkAction.mockResolvedValue({
      ok: true,
      data: { url: URL.replace("instagram", "whatsapp"), channel: "whatsapp", mode: "cloud_api", expires_at: "2026-12-04T10:00:00Z" },
    });
    paint(<ShareLink refId="flor" channel="whatsapp" modes={["coexistence", "cloud_api"]} />);
    await user.click(screen.getByRole("button", { name: "Enviar enlace al cliente" }));
    await user.selectOptions(screen.getByLabelText("Modo de conexión"), "cloud_api");
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(actions.signupLinkAction).toHaveBeenCalledWith({ ref: "flor", channel: "whatsapp", mode: "cloud_api" });
    expect(await screen.findByText("Enviar por correo")).toBeInTheDocument();
    expect(href("Enviar por correo")).toContain("subject=Conecta el WhatsApp de tu negocio");
  });
});
