import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentChannels, ChannelPage } from "@/lib/backend/channel-config-types";
import type { ChannelDetail } from "@/lib/backend/channels";

import { CH, CH2, LINK, RECEPCION, REF, VENTAS, channels, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({}));

const { AgentChannelsPanel } = await import("../agent-channels");
const { OwnerLinkPanel } = await import("../owner-link-panel");
type Actions = NonNullable<React.ComponentProps<typeof AgentChannelsPanel>["actions"]>;
type LinkActions = NonNullable<React.ComponentProps<typeof OwnerLinkPanel>["actions"]>;

/**
 * Spec 047 (historias 10 y 11; requisitos 29, 31 y 34; T111 y T115) — la
 * sección Canales del agente: cada número con su estado visible y su ⋯ (solo lo
 * permitido), pasar a otro agente, pausar, desconectar con confirmación y
 * «Reintentar» si Meta no confirma; y el enlace del dueño: se copia mientras se
 * ve, «Revocar y crear», «WhatsApp login» solo si la API lo acepta y la frase
 * «desde su teléfono» solo con la bandera.
 */

const detail = (pending: string[] = []) => ({ unlink_pending: pending }) as unknown as ChannelDetail;

function panel(data: AgentChannels | null = channels(), over: Partial<Actions["menu"] & object> = {}, { canWrite = true, pages = undefined as Record<string, ChannelPage | null> | undefined } = {}) {
  const actions: Actions = {
    reload: vi.fn(async () => ok(channels())),
    menu: {
      move: vi.fn(async () => ok(page({ agent: { id: VENTAS, name: "Ventas" } }))),
      pause: vi.fn(async () => ok(page({ status: "paused", visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["configure", "move", "resume", "disconnect"] }))),
      resume: vi.fn(async () => ok(page())),
      disconnect: vi.fn(async () => ok(detail())),
      ...over,
    },
    ownerLink: { create: vi.fn(), revoke: vi.fn() },
  };
  const view = render(
    <LocaleProvider locale="es">
      <AgentChannelsPanel
        refId={REF}
        agentId={RECEPCION}
        channels={data}
        pages={pages ?? { [CH]: page(), [CH2]: null }}
        canWrite={canWrite}
        actions={actions}
      />
    </LocaleProvider>,
  );
  return { ...view, actions };
}

async function openMenu(user: ReturnType<typeof userEvent.setup>, number = "+34 611 20 48 93") {
  await user.click(screen.getByRole("button", { name: `Más acciones de ${number}` }));
  return screen.findByRole("menu");
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  toast.warning.mockClear();
});

describe("la sección Canales del agente", () => {
  it("cada número con su estado visible y el camino a su página", async () => {
    const { container } = panel();
    const list = screen.getByRole("list", { name: "Números de este agente" });
    const items = within(list).getAllByRole("listitem");
    expect(within(items[0]!).getByText("Solo mi equipo")).toBeVisible();
    expect(within(items[1]!).getByText("Con problemas · la app lleva días sin abrirse")).toBeVisible();
    expect(within(items[0]!).getByRole("link", { name: "Configurar +34 611 20 48 93" })).toHaveAttribute(
      "href",
      `/clients/${REF}/agents/${RECEPCION}?canal=${CH}`,
    );
    // Sin su página, el número se ve igual, sin ⋯.
    expect(screen.queryByRole("button", { name: "Más acciones de +34 611 20 48 94" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("el ⋯ ofrece solo lo permitido, en el orden de 34.1", async () => {
    const user = userEvent.setup();
    panel();
    const menu = await openMenu(user);
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Configuración", "Pasar a otro agente", "Pausar este canal", "Desconectar"]);
  });

  it("sin nada permitido, ni el ⋯ (§V)", () => {
    panel(channels(), {}, { canWrite: false, pages: { [CH]: page({ allowed: [] }) } });
    expect(screen.queryByRole("button", { name: /Más acciones/ })).toBeNull();
  });

  it("pausar cambia su estado y el ⋯ pasa a «Reanudar»", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(within(await openMenu(user)).getByRole("menuitem", { name: "Pausar este canal" }));
    expect(actions.menu!.pause).toHaveBeenCalledWith({ ref: REF, channel: CH });
    expect(await screen.findByText("En pausa")).toBeVisible();
    expect(within(await openMenu(user)).getByRole("menuitem", { name: "Reanudar este canal" })).toBeVisible();
  });

  it("pasar a otro agente: lista los que no son borradores y el número sale de aquí", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(within(await openMenu(user)).getByRole("menuitem", { name: "Pasar a otro agente" }));
    const dialog = await screen.findByRole("dialog", { name: "Pasar +34 611 20 48 93 a otro agente" });
    expect(within(dialog).getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual(["Ventas"]);
    await user.click(within(dialog).getByRole("button", { name: "Pasar el número" }));
    expect(actions.menu!.move).toHaveBeenCalledWith({ ref: REF, channel: CH, to: VENTAS });
    expect(toast.success).toHaveBeenCalledWith("+34 611 20 48 93 ya lo atiende Ventas.");
    await waitFor(() => expect(screen.queryByText("+34 611 20 48 93")).toBeNull());
  });

  it("desconectar pide confirmación y, si Meta no confirma, ofrece «Reintentar» (34.3)", async () => {
    const user = userEvent.setup();
    const disconnect = vi.fn().mockResolvedValueOnce(ok(detail(["deregister"]))).mockResolvedValueOnce(ok(detail()));
    const { baseElement } = panel(channels(), { disconnect });
    await user.click(within(await openMenu(user)).getByRole("menuitem", { name: "Desconectar" }));
    const confirm = await screen.findByRole("dialog", { name: "¿Desconectar +34 611 20 48 93?" });
    expect(within(confirm).getByText(/Las conversaciones se conservan/)).toBeVisible();
    expect(await axeViolations(baseElement)).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Desconectar" }));
    expect(disconnect).toHaveBeenCalledWith({ ref: REF, channelId: CH });
    expect(await screen.findByText("Falta terminar en Meta")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(disconnect).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByText("Falta terminar en Meta")).toBeNull());
    expect(toast.success).toHaveBeenCalledWith("Terminado también en Meta.");
  });

  it("si no se pudieron leer los números, lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const { actions } = panel(null);
    expect(screen.getByText(/No pudimos cargar los números de este agente/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(actions.reload).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION });
    expect(await screen.findByRole("list", { name: "Números de este agente" })).toBeVisible();
  });
});

function linkPanel(pending: AgentChannels["pending_link"] = null, over: Partial<LinkActions> = {}, { canWrite = true, fromPhone = false } = {}) {
  const actions: LinkActions = {
    create: vi.fn(async ({ mode }) => ok({ id: LINK, url: "https://consola.auphere.com/connect/whatsapp/tok_abcdefghijklmnop", mode, expires_at: "2026-11-03T10:00:00Z" })),
    revoke: vi.fn(async () => ok(null)),
    ...over,
  };
  const view = render(
    <LocaleProvider locale="es">
      <OwnerLinkPanel refId={REF} agentId={RECEPCION} pending={pending} canWrite={canWrite} fromPhone={fromPhone} actions={actions} />
    </LocaleProvider>,
  );
  return { ...view, actions };
}

describe("el enlace del dueño (31)", () => {
  it("crea el enlace en el modo elegido y lo enseña una sola vez para copiarlo", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { actions, container } = linkPanel();
    expect(screen.getByRole("radio", { name: /Ya usa la app WhatsApp Business/ })).toBeChecked();
    expect(screen.getByText(/abre el enlace en su navegador/)).toBeVisible();
    expect(screen.queryByText(/desde su teléfono/)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("radio", { name: /Es un número que no usa la app/ }));
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(actions.create).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, mode: "cloud_api" });
    expect(screen.getByText(/Cópialo ahora: por seguridad no se vuelve a enseñar/)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Enlace para el dueño" })).toHaveValue("https://consola.auphere.com/connect/whatsapp/tok_abcdefghijklmnop");
    await user.click(screen.getByRole("button", { name: "Copiar enlace" }));
    expect(writeText).toHaveBeenCalledWith("https://consola.auphere.com/connect/whatsapp/tok_abcdefghijklmnop");
    await user.click(screen.getByRole("button", { name: "Hecho" }));
    // Se fue de la pantalla: queda el pendiente, sin el enlace.
    expect(screen.queryByRole("textbox", { name: "Enlace para el dueño" })).toBeNull();
    expect(screen.getByText("Enlace pendiente · número sin la app")).toBeVisible();
  });

  it("con uno pendiente, crear otro ofrece «Revocar y crear» (31.2)", async () => {
    const user = userEvent.setup();
    const create = vi.fn().mockResolvedValueOnce(fail(409, "link_pending_exists", { link_id: LINK })).mockResolvedValueOnce(
      ok({ id: LINK, url: "https://x/connect/whatsapp/t", mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" }),
    );
    linkPanel(null, { create });
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(await screen.findByText(/Ya hay un enlace pendiente para este agente/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Revocar y crear" }));
    expect(create).toHaveBeenLastCalledWith({ ref: REF, agent: RECEPCION, mode: "coexistence", replace: true });
  });

  it("el pendiente dice su modo y su caducidad, y se revoca con confirmación (31.7)", async () => {
    const user = userEvent.setup();
    const { actions } = linkPanel({ id: LINK, mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" });
    expect(screen.getByText("Enlace pendiente · app WhatsApp Business")).toBeVisible();
    expect(screen.getByText(/no se puede volver a enseñar/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Revocar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Revocar el enlace?" });
    await user.click(within(dialog).getByRole("button", { name: "Revocar" }));
    expect(actions.revoke).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, link: LINK });
    expect(await screen.findByRole("button", { name: "Crear enlace" })).toBeVisible();
  });

  it("«Crear otro enlace» con uno pendiente manda «replace»", async () => {
    const user = userEvent.setup();
    const { actions } = linkPanel({ id: LINK, mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" });
    await user.click(screen.getByRole("button", { name: "Crear otro enlace" }));
    expect(screen.getByText(/el anterior deja de funcionar/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Revocar y crear" }));
    expect(actions.create).toHaveBeenCalledWith(expect.objectContaining({ replace: true }));
  });

  it("«WhatsApp login» solo si la API lo acepta: si no, lo dice y la opción desaparece (31.5, 31.6)", async () => {
    const user = userEvent.setup();
    const { actions } = linkPanel(null, { create: vi.fn(async () => fail(409, "whatsapp_login_unavailable")) });
    await user.click(screen.getByRole("radio", { name: /WhatsApp login \(beta\)/ }));
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(actions.create).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, mode: "whatsapp_login" });
    expect(await screen.findByText(/WhatsApp login no está disponible para el país de este negocio/)).toBeVisible();
    expect(screen.queryByRole("radio", { name: /WhatsApp login/ })).toBeNull();
    expect(screen.getByRole("radio", { name: /Ya usa la app WhatsApp Business/ })).toBeChecked();
    expect(document.body.textContent).not.toMatch(/sin Facebook/i);
  });

  it("«desde su teléfono» solo con la bandera (31.3)", () => {
    linkPanel(null, {}, { fromPhone: true });
    expect(screen.getByText(/abre el enlace desde su teléfono/)).toBeVisible();
  });

  it("quien solo lee ve el pendiente, sin botones, y nada si no hay", () => {
    const { unmount } = linkPanel({ id: LINK, mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" }, {}, { canWrite: false });
    expect(screen.getByText("Enlace pendiente · app WhatsApp Business")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    const { container } = linkPanel(null, {}, { canWrite: false });
    expect(container).toBeEmptyDOMElement();
  });
});
